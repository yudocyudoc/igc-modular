"""Strict Buffalo SD-AI native sd-json -> OpenModelica translator (NO D/M).

Graphical lookup interpolation and extrapolation are explicit, provisional adapter
assumptions; successful compilation is G2 only, not proof of G0 exact equivalence
to Buffalo's own simulator, G1 completeness, or G3 causal validity.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

VERSION = "igc-b-native-modelica-conditional/0.2"
# Exact fields observed in the original native Buffalo scalar-output contract.
# New fields are NOT assumed to be cosmetic: subType=conveyor, delay state,
# or arrays may change dynamics even when type='stock'.
SUPPORTED_NATIVE_FIELDS = frozenset({
    "name", "type", "equation", "units", "inflows", "outflows",
    "uniflow", "graphicalFunction", "documentation",
})
SUPPORTED_SPEC_FIELDS = frozenset({
    "startTime", "stopTime", "dt", "timeUnits", "integrationMethod",
})
SUPPORTED_NATIVE_KEYS = frozenset({
    "variables", "relationships", "modules", "specs",
})
SUPPORTED_ENVELOPE_KEYS = frozenset({"model", "supportingInfo"})

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{0,59}$")
FUNCS = {"MIN": "min", "MAX": "max", "ABS": "abs"}


class TranslationBlocked(ValueError):
    pass


def require(test, code):
    if not test:
        raise TranslationBlocked(code)


def ident(value):
    require(isinstance(value, str) and NAME.fullmatch(value) is not None, "INVALID_VARIABLE_NAME")
    return value.replace(" ", "_")


def num(value):
    require(isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value), "INVALID_FINITE_NUMBER")
    return format(float(value), ".15g")


def expression(raw, declared):
    require(isinstance(raw, str) and 0 < len(raw) <= 400, "MISSING_EQUATION")
    try:
        root = ast.parse(raw.replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise TranslationBlocked("UNSUPPORTED_EXPRESSION_SYNTAX") from exc

    def emit(node):
        if isinstance(node, ast.Constant):
            return num(node.value)
        if isinstance(node, ast.Name):
            if node.id == "TIME":
                return "time"
            require(node.id in declared, "UNKNOWN_SYMBOL:" + node.id)
            return node.id
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return ("+" if isinstance(node.op, ast.UAdd) else "-") + "(" + emit(node.operand) + ")"
        if isinstance(node, ast.BinOp):
            a, b = emit(node.left), emit(node.right)
            if isinstance(node.op, ast.FloorDiv):  # Buffalo // is SAFE DIVISION, NOT floor division.
                return "(if (" + b + ") == 0 then 0 else ((" + a + ") / (" + b + ")))"
            ops = {ast.Add:"+", ast.Sub:"-", ast.Mult:"*", ast.Div:"/", ast.Pow:"^"}
            require(type(node.op) in ops, "UNSUPPORTED_OPERATOR")
            return "(" + a + " " + ops[type(node.op)] + " " + b + ")"
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and not node.keywords and node.func.id.upper() in FUNCS):
            fn = node.func.id.upper()
            require(len(node.args) == (1 if fn == "ABS" else 2), "BAD_FUNCTION_ARITY")
            return FUNCS[fn] + "(" + ", ".join(emit(a) for a in node.args) + ")"
        raise TranslationBlocked("UNSUPPORTED_EQUATION_NODE")
    return emit(root.body)


def table_function(name, points):
    require(isinstance(points, list) and len(points) >= 2, "BAD_GRAPHICAL_TABLE")
    pairs = []
    for point in points:
        require(isinstance(point, dict) and set(point) == {"x", "y"}, "BAD_GRAPHICAL_POINT")
        x = float(point["x"]); y = float(point["y"])
        require(math.isfinite(x) and math.isfinite(y), "NONFINITE_TABLE_POINT")
        require(not pairs or x > pairs[-1][0], "NON_MONOTONIC_GRAPHICAL_X")
        pairs.append((x, y))
    fn = "lookup_" + name
    lines = [f"  function {fn}", "    input Real x;", "    output Real y;", "  algorithm"]
    lines.append(f"    if x <= {num(pairs[0][0])} then")
    lines.append(f"      y := {num(pairs[0][1])};")
    for (xa, ya), (xb, yb) in zip(pairs[:-1], pairs[1:]):
        lines.append(f"    elseif x < {num(xb)} then")
        slope = (yb - ya) / (xb - xa)
        lines.append(f"      y := {num(ya)} + (x - {num(xa)}) * ({num(slope)});")
    lines.extend(["    else", f"      y := {num(pairs[-1][1])};",
                  "    end if;", f"  end {fn};"])
    return fn, lines


def generate(document):
    require(isinstance(document, dict) and isinstance(document.get("model"), dict),
            "NOT_NATIVE_BUFFALO_ENVELOPE")
    native = document["model"]
    require(not (set(document) - SUPPORTED_ENVELOPE_KEYS), "UNSUPPORTED_NATIVE_ENVELOPE_FIELD")
    require(not (set(native) - SUPPORTED_NATIVE_KEYS), "UNSUPPORTED_NATIVE_MODEL_FIELD")
    require(isinstance(native.get("modules", []), list) and not native.get("modules"), "MODULES_UNSUPPORTED")
    specs = native.get("specs")
    require(isinstance(specs, dict), "MISSING_NATIVE_SIMULATION_SPECS")
    require(not (set(specs) - SUPPORTED_SPEC_FIELDS), "UNSUPPORTED_NATIVE_SIMULATION_SPEC")
    require(set(specs) == SUPPORTED_SPEC_FIELDS, "INCOMPLETE_NATIVE_SIMULATION_SPECS")
    # Until solver parity is proved, the pinned G2 replay cannot silently
    # simulate a different step, integration method, time unit or horizon.
    require(
        specs["startTime"] == 0 and specs["stopTime"] == 8
        and specs["dt"] == 0.125 and specs["timeUnits"] == "hour"
        and specs["integrationMethod"] == "Euler",
        "NATIVE_SPECS_OUTSIDE_PINNED_G2_SCOPE"
    )
    vs, rs = native.get("variables"), native.get("relationships")
    require(isinstance(vs, list) and 1 <= len(vs) <= 64, "BAD_VARIABLES")
    require(isinstance(rs, list), "BAD_RELATIONSHIPS")
    units, by_name, by_id = {}, {}, {}
    stocks, flows = [], []
    for v in vs:
        require(isinstance(v, dict), "BAD_VARIABLE")
        # Fail closed on Buffalo subtypes and extra state semantics. In
        # particular conveyor is NOT equivalent to an ordinary integrator.
        require(not (set(v) - SUPPORTED_NATIVE_FIELDS), "UNSUPPORTED_NATIVE_VARIABLE_FIELD")
        gf = v.get("graphicalFunction", {"points": []})
        require(isinstance(gf, dict) and set(gf) == {"points"}
                and isinstance(gf["points"], list), "UNSUPPORTED_GRAPHICAL_FUNCTION_FORMAT")
        raw = v.get("name"); key = ident(raw)
        require(key not in by_id and key != "time", "DUPLICATE_OR_RESERVED_IDENTIFIER")
        require(v.get("type") in ("stock", "flow", "variable"), "BAD_VARIABLE_TYPE")
        if v["type"] == "stock":
            require(not gf["points"], "GRAPHICAL_FUNCTION_ON_STOCK_UNSUPPORTED")
        if v["type"] != "stock":
            require(not v.get("inflows") and not v.get("outflows"),
                    "MATERIAL_PORTS_ON_NONSTOCK")
        require(type(v.get("uniflow", False)) is bool, "BAD_UNIFLOW_FLAG")
        by_name[raw], by_id[key], units[raw] = v, v, v.get("units", "")
        if v["type"] == "stock":
            stocks.append(v)
        elif v["type"] == "flow":
            flows.append(v)
    require(stocks and flows, "STOCK_AND_FLOW_REQUIRED")
    # A conservative flow membership check (one inflow and one outflow at most).
    usage = {}
    for stock in stocks:
        for port in ("inflows", "outflows"):
            names = stock.get(port, [])
            require(isinstance(names, list) and len(set(names)) == len(names), "BAD_PORT_LIST")
            require(not set(stock.get("inflows", [])).intersection(stock.get("outflows", [])),
                    "SAME_FLOW_BOTH_STOCK_PORTS")
            for f in names:
                require(f in by_name and by_name[f]["type"] == "flow", "UNKNOWN_MATERIAL_FLOW")
                usage.setdefault(f, []).append(port)
                stock_u = units[stock["name"]].replace(" per ", "/").replace(" ", "").lower()
                flow_u = units[f].replace(" per ", "/").replace(" ", "").lower()
                require(not stock_u or not flow_u or flow_u == stock_u + "/hour",
                        "STOCK_FLOW_UNIT_MISMATCH")
    for f in flows:
        ports = usage.get(f["name"], [])
        require(1 <= len(ports) <= 2, "FLOW_WITHOUT_STOCK_OR_DUPLICATED")
        require(len(ports) == 1 or set(ports) == {"inflows", "outflows"}, "DUPLICATED_MATERIAL_FLOW")
    for edge in rs:
        require(isinstance(edge, dict) and edge.get("from") in by_name
                and edge.get("to") in by_name, "DANGLING_CAUSAL_EDGE")

    sig = hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest()[:12]
    modelname = "BuffaloNative_" + sig
    decl, eq, funcs, gf_vars = [], [], [], []
    declared = set(by_id)
    for v in vs:
        name = ident(v["name"])
        if v["type"] == "stock":
            initial = float(v.get("equation", "nan"))
            require(math.isfinite(initial) and initial >= 0, "BAD_STOCK_INITIAL")
            decl.append(f"  Real {name}(start={num(initial)}, fixed=true);")
            continue
        expr = expression(v.get("equation"), declared)
        points = v.get("graphicalFunction", {}).get("points", [])
        if points:
            fn, definition = table_function(name, points)
            funcs.extend(definition)
            expr = fn + "(" + expr + ")"
            gf_vars.append(v["name"])
        uniflow = v.get("uniflow")
        if v["type"] == "flow" and uniflow is True:
            expr = "max(0, " + expr + ")"
        decl.append(f"  Real {name};")
        eq.append(f"  {name} = {expr};")

    for stock in stocks:
        inc = [ident(x) for x in stock.get("inflows", [])]
        out = [ident(x) for x in stock.get("outflows", [])]
        eq.append(f"  der({ident(stock['name'])}) = ({' + '.join(inc) or '0'}) - ({' + '.join(out) or '0'});")
    code = "\n".join([f"model {modelname}",
                       "  // Direct translation of Buffalo native quantities, not D or molecules.",
                       "  // G0 conditional: graphical lookup uses piecewise-linear interpolation and endpoint clamping.",
                       *funcs, *decl, "equation", *eq, f"end {modelname};", ""])
    report = {"schema":VERSION,"status":"TRANSLATED_WITH_EXPLICIT_LOOKUP_ASSUMPTIONS",
              "native_sha256":"sha256:"+hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest(),
              "model":modelname,"variables":len(vs),"stocks":len(stocks),
              "flows":len(flows),"lookup_variables":gf_vars,
              "native_simulation_specs":specs,
              "solver_scope":"PINNED_EULER_0_TO_8_HOURS_DT_0_125",
              "assumptions":["LINEAR_INTERPOLATION_BETWEEN_GRAPHICAL_POINTS",
                             "HOLD_ENDPOINT_VALUES_OUTSIDE_GRAPHICAL_RANGE",
                             "EXACT_ZERO_SAFE_DIVISION_FOR_BUFFALO_DOUBLE_SLASH"],
              "limits":["NOT_UPSTREAM_LOOKUP_EQUIVALENCE_PROOF","NOT_G1_GENERAL_UNIT_PROOF",
                        "G3_CONSTRUCTION_ADEQUACY_NOT_ESTABLISHED",
                        "HELDOUT_EVALUATION_SEPARATE_NOT_RUN",
                        "UNSUPPORTED_NATIVE_SUBTYPES_REJECTED"]}
    return modelname, code, report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("native",type=Path)
    ap.add_argument("out",type=Path)
    args=ap.parse_args()
    require(not args.out.exists(), "OUTPUT_DIRECTORY_EXISTS")
    source=json.loads(args.native.read_text())
    name, modelica, report=generate(source)
    args.out.mkdir(parents=True)
    (args.out/(name+".mo")).write_text(modelica)
    (args.out/"translation-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))

if __name__=="__main__":
    main()
