"""BF-00: static semantic diagnostics on original Buffalo bytes; never repair.

The external translator is narrower than Buffalo's schema. G0 JSON validity is
not G1 semantic validity. An integrated stock breaks algebraic dependencies.
"""
import ast
from collections import defaultdict
import copy
import hashlib
import json
import math
import re

REPORT_VERSION = "buffalo-adjust-v1/bf00"
ERROR = "ERROR"
WARNING = "WARNING"
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{0,59}$")
SYMBOL = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
LITERALS = {"TIME", "MIN", "MAX", "ABS"}
PULSE_MASS = 3.4


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def item(code, severity, variable="", field="", evidence=None, scope="native", backend="Modelica"):
    return {"code":code, "severity":severity, "variable":variable, "field":field,
            "evidence":evidence, "scope":scope, "backend":backend}


def _numbers(points):
    if not isinstance(points, list):
        return None
    xy = []
    for p in points:
        if (not isinstance(p, dict) or set(p) != {"x", "y"}
            or any(type(p[k]) not in (int,float) or not math.isfinite(p[k])
                   for k in ("x","y"))):
            return None
        xy.append((float(p["x"]),float(p["y"])))
    if any(b[0] <= a[0] for a,b in zip(xy,xy[1:])):
        return None
    return xy


def linear_lookup(points, x):
    """Exactly the endpoint-clamping/linear assumption of pinned translator."""
    if not points:
        raise ValueError("Lookup has no points.")
    if x <= points[0][0]:
        return points[0][1]
    for (xa,ya),(xb,yb) in zip(points,points[1:]):
        if x < xb:
            return ya+(x-xa)*(yb-ya)/(xb-xa)
    return points[-1][1]


def _dependencies(equation, names):
    if not isinstance(equation,str):
        return set(),set()
    used = {s for s in SYMBOL.findall(equation) if s in names}
    unknown = {s for s in SYMBOL.findall(equation)
               if s not in names and s not in LITERALS and s.upper() not in LITERALS}
    return used,unknown


def _cycles(graph):
    """Simple deterministic circuit detection, omitting stock nodes/edges."""
    found = set()
    visiting = []
    visited = set()
    def visit(node):
        if node in visiting:
            path = visiting[visiting.index(node):]+[node]
            found.add(tuple(path))
            return
        if node in visited:
            return
        visiting.append(node)
        for edge in sorted(graph.get(node,())):
            visit(edge)
        visiting.pop()
        visited.add(node)
    for node in sorted(graph):
        visit(node)
    return sorted(found)


def diagnose(document, *, raw_response=None):
    results = []
    variables = (document or {}).get("model",{}).get("variables",[])
    if not isinstance(variables,list) or not variables:
        return {"schema":REPORT_VERSION, "admissible":False,
                "diagnostics":[item("MISSING_NATIVE_MODEL",ERROR)]}
    by_name = {}
    ids = {}
    for v in variables:
        name=v.get("name")
        if not isinstance(name,str) or not NAME.fullmatch(name):
            results.append(item("INVALID_NATIVE_NAME",ERROR,str(name),"name",name))
            continue
        ident = name.replace(" ","_")
        if ident in ids:
            results.append(item("DUPLICATE_NORMALIZED_NAME",ERROR,name,"name",ident))
        ids[ident]=v
        by_name[name]=v
    graph={}
    ports=defaultdict(list)
    specs=(document or {}).get("model",{}).get("specs",{})
    if specs.get("timeUnits") == "hours":
        results.append(item("REPRESENTATIONAL_TIME_UNIT_ALIAS",WARNING,"","specs.timeUnits",
                            {"from":"hours","to":"hour","scale":1},backend="Adapter"))
    elif specs.get("timeUnits")!="hour":
        results.append(item("UNSUPPORTED_TIME_UNIT",ERROR,"","specs.timeUnits",
                            specs.get("timeUnits")))
    for v in variables:
        name=v.get("name","")
        typ=v.get("type")
        gf=v.get("graphicalFunction",{})
        points=gf.get("points",[]) if isinstance(gf,dict) else None
        xy=_numbers(points)
        if xy is None:
            results.append(item("BAD_LOOKUP_POINTS",ERROR,name,"graphicalFunction.points",
                                points))
            xy=[]
        if xy and typ in ("stock","flow"):
            results.append(item("LOOKUP_UNSUPPORTED_FOR_MATERIAL_TYPE",ERROR,name,
                                "graphicalFunction.points",{"type":typ,"count":len(xy)}))
        eq=v.get("equation","")
        if xy and typ=="variable":
            try:
                x=float(eq)
            except (TypeError,ValueError):
                x=None
            if x is not None:
                y=linear_lookup(xy,x)
                results.append(item("LOOKUP_APPLIED_TO_CONSTANT",ERROR,name,
                                    "graphicalFunction.points",
                                    {"equation":eq,"input":x,"effective_value":y,
                                     "not_decorative":True}))
            if "input" in name.lower() and "profile" in name.lower():
                area=sum((xb-xa)*(ya+yb)/2 for (xa,ya),(xb,yb) in zip(xy,xy[1:]))
                if abs(area-PULSE_MASS)>1e-12:
                    results.append(item("LINEAR_TABLE_NOT_EXACT_PUBLIC_PULSE",ERROR,name,
                                        "graphicalFunction.points",
                                        {"piecewise_linear_mass":round(area,12),
                                         "public_exact_mass":PULSE_MASS,
                                         "solver_grid_equivalence_insufficient":True}))
        if typ=="stock":
            if not isinstance(eq,(str,int,float)) or not str(eq).replace(".","",1).isdigit():
                results.append(item("INVALID_STOCK_INITIAL",ERROR,name,"equation",eq))
            for direction in ("inflows","outflows"):
                ports_list=v.get(direction,[])
                if not isinstance(ports_list,list):
                    results.append(item("BAD_MATERIAL_PORTS",ERROR,name,direction))
                    continue
                for flow in ports_list:
                    if flow not in by_name or by_name[flow].get("type")!="flow":
                        results.append(item("UNKNOWN_MATERIAL_FLOW",ERROR,name,direction,flow))
                    else:
                        ports[flow].append((direction,name))
        else:
            if v.get("inflows") or v.get("outflows"):
                results.append(item("MATERIAL_PORTS_ON_NONSTOCK",ERROR,name,"ports"))
            refs,unknown=_dependencies(eq,ids)
            graph[name.replace(" ","_")]={
                ref for ref in refs if ids[ref].get("type")!="stock"}
            for ref in sorted(unknown):
                results.append(item("UNKNOWN_EXPRESSION_SYMBOL",ERROR,name,"equation",ref))
        if v.get("units")=="hours":
            results.append(item("REPRESENTATIONAL_TIME_UNIT_ALIAS",WARNING,name,"units",
                                {"from":"hours","to":"hour","scale":1},backend="Adapter"))
    for flow,used in ports.items():
        if len(used)>2 or len({d for d,_ in used})!=len(used):
            results.append(item("MATERIAL_PORT_DUPLICATED",ERROR,flow,"ports",used))
    for name,v in by_name.items():
        if v.get("type")=="flow" and name not in ports:
            results.append(item("MATERIAL_FLOW_WITHOUT_STOCK",ERROR,name,"ports"))
    for circuit in _cycles(graph):
        results.append(item("ALGEBRAIC_CYCLE",ERROR,circuit[0],"equation",
                            {"path":list(circuit),"stocks_break_instantaneous_cycles":True}))
    info=(document or {}).get("supportingInfo",{})
    explanation=info.get("explanation","") if isinstance(info,dict) else ""
    if re.search(r"\bcalibrat(?:ed|ion|e)?\b",explanation,re.I):
        results.append(item("UNVERIFIED_CALIBRATION_CLAIM",WARNING,"",
                            "supportingInfo.explanation",
                            "No optimizer/solver execution receipt in native artifact.",
                            backend="Evidence"))
    if raw_response is not None:
        results.extend(classify_provider(raw_response))
    return {"schema":REPORT_VERSION, "admissible":not any(
        r["severity"]==ERROR for r in results),
        "variables_count":len(variables),
        "diagnostics":sorted(results,key=lambda r:(
            r["variable"],r["field"],r["code"]))}


def classify_provider(raw):
    """Classify budget exhaustion only when final content is actually absent."""
    payload=raw.get("result",raw) if isinstance(raw,dict) else {}
    choices=payload.get("choices",[])
    if not choices:
        return []
    first=choices[0]
    msg=first.get("message",{})
    content=msg.get("content") if isinstance(msg,dict) else None
    finish=first.get("finish_reason")
    usage=payload.get("usage",{})
    tokens=usage.get("completion_tokens")
    if finish=="length" and (content is None or content=="") and tokens==16000:
        return [item("OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT",ERROR,"",
                     "provider.choices[0]",
                     {"finish_reason":"length","completion_tokens":tokens,
                      "content_empty":True},backend="Cloudflare")]
    if finish=="length":
        return [item("OUTPUT_LIMIT_REACHED_CONTENT_MAY_EXIST",WARNING,"",
                     "provider.choices[0]",
                     {"finish_reason":finish,"completion_tokens":tokens,
                      "content_empty":not bool(content)},backend="Cloudflare")]
    return []


def diagnostic_packet(document, raw_response=None):
    return diagnose(document,raw_response=raw_response)
