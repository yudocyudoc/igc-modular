"""G1 admission for BF03/BF04: Buffalo proposes the mechanism; public input is fixed.

Only the public exogenous input is required to match a conservative exact
equation template. This is not an invented Buffalo model or an optimizer.
Mathematically equivalent forms outside the proven subset are BLOCKED and
reported, not silently re-authored. XMILE/PySD equivalence is not claimed.
"""
import ast
from fractions import Fraction
from .capabilities import exact_pulse_equation, eval_fixture_equation, normalize_units_only
from .validation import diagnose
from arena._vendor.igc.scripts.arena_b_native_to_modelica import generate, TranslationBlocked
from arena._vendor.igc.scripts.arena_cafe.ct03_b_physical_prepare import operator


class CandidateBlocked(ValueError):
    pass


def _expand(node, variables, seen=frozenset()):
    if isinstance(node, ast.Name) and node.id in variables:
        variable=variables[node.id]
        if variable.get("type")!="variable" or node.id in seen:
            return node
        try:
            nested=ast.parse(str(variable["equation"]).replace("^","**"),mode="eval").body
        except SyntaxError:
            return node
        # A graphical function is not merely the scalar equation; never ignore it.
        if variable.get("graphicalFunction",{}).get("points"):
            return node
        return _expand(nested,variables,seen | {node.id})
    for key, value in ast.iter_fields(node):
        if isinstance(value,list):
            setattr(node,key,[_expand(x,variables,seen) if isinstance(x,ast.AST)
                              else x for x in value])
        elif isinstance(value,ast.AST):
            setattr(node,key,_expand(value,variables,seen))
    return node


def _signature(node):
    """AST comparison with exact rational numeric normalization."""
    if isinstance(node,ast.Constant) and type(node.value) in (int,float):
        return ("num",str(Fraction(str(node.value))))
    if isinstance(node,ast.Name):
        return ("name",node.id)
    if isinstance(node,ast.BinOp):
        return ("binary",type(node.op).__name__,
                _signature(node.left),_signature(node.right))
    if isinstance(node,ast.UnaryOp):
        return ("unary",type(node.op).__name__,_signature(node.operand))
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
        return ("call",node.func.id.upper(),tuple(map(_signature,node.args)))
    raise CandidateBlocked("PUBLIC_SOURCE_EXPRESSION_OUTSIDE_EXACT_WITNESS")


def validate_candidate(native):
    diag=diagnose(native)
    if not diag["admissible"]:
        raise CandidateBlocked("BF_G1_SEMANTIC_INVALID:"+
            ",".join(x["code"] for x in diag["diagnostics"] if x["severity"]=="ERROR"))
    normalized,view=normalize_units_only(native)
    try:
        modelname,code,translation=generate(view)
        port=operator(view)
    except (TranslationBlocked, ValueError, KeyError, TypeError) as exc:
        raise CandidateBlocked("BF_G1_TRANSLATION_OR_OBSERVABLE_BLOCKED:"+str(exc)) from exc
    variables={v["name"].replace(" ","_"):v for v in view["model"]["variables"]}
    stocks=[v for v in view["model"]["variables"] if v["type"]=="stock"]
    flows=[v for v in view["model"]["variables"] if v["type"]=="flow"]
    inbound={x for v in stocks for x in v["inflows"]}
    outbound={x for v in stocks for x in v["outflows"]}
    external=[v for v in flows if v["name"] in inbound and v["name"] not in outbound]
    if len(external)!=1:
        raise CandidateBlocked("BF_G1_REQUIRE_UNAMBIGUOUS_PUBLIC_SOURCE_FLOW")
    flow=external[0]
    try:
        actual=_expand(ast.parse(flow["equation"].replace("^","**"),mode="eval").body,
                       variables)
        expected=ast.parse(exact_pulse_equation("1.7","0","2"),mode="eval").body
        if _signature(actual)!=_signature(expected):
            raise CandidateBlocked("BF_G1_PUBLIC_PULSE_NOT_EXACT_TEMPLATE_WITNESS")
        for sample in ("-1","0","1/2","1","39/20","1999/1000","2","2001/1000","8"):
            x=Fraction(sample)
            value=eval_fixture_equation(ast.unparse(actual),time=x)
            wanted=Fraction("1.7") if 0<=x<2 else Fraction(0)
            if value!=wanted:
                raise CandidateBlocked("BF_G1_PUBLIC_PULSE_EDGE_MISMATCH")
    except (SyntaxError,ValueError,ZeroDivisionError) as exc:
        raise CandidateBlocked("BF_G1_PUBLIC_PULSE_UNCERTIFIED:"+str(exc)) from exc
    if any(float(v["equation"])!=0 for v in stocks):
        raise CandidateBlocked("BF_G1_INITIAL_MATERIAL_STOCKS_NOT_ZERO")
    return {"schema":"buffalo-adjust-v1/g1/1",
            "status":"ADMISSIBLE_IN_PINNED_MODELICA_SUBSET_NOT_YET_SIMULATED",
            "semantic_diagnostics":diag,
            "unit_view_manifest":normalized,
            "translated_model_name":modelname,
            "translated_modelica_text":code,
            "translated_scope":translation,
            "observation_operator":port,
            "public_input_flow_name":flow["name"],
            "input_certificate":"EXACT_SAFE_DIVISION_TEMPLATE_AFTER_SCALAR_ALIAS_EXPANSION",
            "input_mass_analytic":3.4,
            "xmile_pysd_parity":"NOT_ESTABLISHED",
            "unknown_equivalent_form":"FAIL_CLOSED_NOT_REPAIRED",
            "parent_or_rival_model_injected":False}
