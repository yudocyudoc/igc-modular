#!/usr/bin/env python3
"""E1: bounded, typed molecular graph derivation from a swappable registry.
No world ID, no gold, no signatures, no graph-name switch, no handwritten ODE.
The first experiment measures engineering composition, NOT causal identification.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODEL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def load_registry(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    # Resolve foundational classes from the E0 source specified in the registry.
    e0 = (path.parent / cfg["extends_e0_catalog"]).resolve()
    # E1 is permitted to use the immutable E0 molecular catalog, not an external gold.
    if e0 != (ROOT / "experiments/e0/catalog.json").resolve():
        raise ValueError("FOREIGN_CATALOG_PATH")
    catalog = json.loads(e0.read_text(encoding="utf-8"))
    classes = {c["id"]:copy.deepcopy(c) for c in catalog["classes"]}
    for cl in cfg.get("new_classes", []):
        if cl["id"] in classes:
            raise ValueError("DUPLICATE_CLASS")
        classes[cl["id"]] = cl
    roles=cfg["roles"]
    if any(v["class_id"] not in classes for v in roles.values()):
        raise ValueError("UNREGISTERED_ROLE_CLASS")
    for role, spec in roles.items():
        cl=classes[spec["class_id"]]
        if role not in cl["roles"]:
            raise ValueError("ROLE_NOT_SUPPORTED:"+role)
        if spec["max_instances"] < 0 or spec["max_instances"]>4:
            raise ValueError("BOUNDS_INVALID")
        if set(spec["parameters"]) != set(cl["parameters"]):
            raise ValueError("PARAMETER_BINDINGS_INVALID:"+role)
        for key, value in spec["parameters"].items():
            p=cl["parameters"][key]
            if not isinstance(value,(float,int)) or not p["min"]<=value<=p["max"]:
                raise ValueError("PARAMETER_OUT_OF_BOUNDS:"+role+"."+key)
        if not MODEL_NAME.fullmatch(role):
            raise ValueError("ROLE_NOT_IDENTIFIER:"+role)
    for role in cfg["mandatory_roles"]:
        if role not in roles or roles[role]["max_instances"]!=1:
            raise ValueError("BAD_MANDATORY_ROLE")
    if cfg["max_candidates"]>256 or cfg["max_candidates"]<1:
        raise ValueError("INVALID_SEARCH_BUDGET")
    ep=cfg["endpoints"]
    if any(x["role"] not in roles for x in (
            ep["source"],ep["receipt"],ep["dispatch_observation"])):
        raise ValueError("ENDPOINT_NOT_REGISTERED")
    if ep["receipt_rate_tap"]["id"] not in {x["id"] for x in catalog["adapters"]}:
        raise ValueError("UNREGISTERED_TAP")
    return cfg,classes,catalog


def ports(cl,role):
    bindings=cl.get("role_bindings",{}).get(role,{})
    out=[]
    for item in cl["ports"]:
        p=copy.deepcopy(item)
        for k,v in bindings.items():
            p["type"]=p["type"].replace("<"+k+">","<"+v+">")
        if p["type"] in ("FLOW<T>","FLOW<U>","STATE<T>"):
            raise ValueError("UNBOUND_ROLE_TYPE:"+role)
        out.append(p)
    return out


def bound_ports(cl,role,kind,direction):
    return sorted((p for p in ports(cl,role) if p["direction"]==direction
                   and p["type"].startswith(kind+"<")),key=lambda x:x["name"])


def enumerate_material(cfg,classes):
    """Connect from a declared source to a terminal through typed open ports.
    No semantic list of topology names or number-of-stages loop.
    """
    ep=cfg["endpoints"]
    source_role=ep["source"]["role"]
    sink_role=ep["receipt"]["role"]
    src=next((x for x in bound_ports(classes[cfg["roles"][source_role]["class_id"]],
                                     source_role,"FLOW","out")
              if x["name"]==ep["source"]["output"]),None)
    if src is None:
        raise ValueError("SOURCE_OUTPUT_INVALID")
    # Candidate interior nodes are determined by types and ports alone.
    interior=[]
    for role,spec in sorted(cfg["roles"].items()):
        if role in (source_role,sink_role):
            continue
        cl=classes[spec["class_id"]]
        inbound=bound_ports(cl,role,"FLOW","in")
        outbound=bound_ports(cl,role,"FLOW","out")
        if inbound and outbound:
            for ip in inbound:
                for op in outbound:
                    interior.append((role,ip,op))
    sink=next((x for x in bound_ports(classes[cfg["roles"][sink_role]["class_id"]],
                                      sink_role,"FLOW","in")
               if x["name"]==ep["receipt"]["input"]),None)
    if sink is None:
        raise ValueError("TERMINAL_INPUT_INVALID")
    initial=[{"id":source_role+"0","role":source_role,
              "class_id":cfg["roles"][source_role]["class_id"],
              "parameters":copy.deepcopy(cfg["roles"][source_role]["parameters"])}]
    mandatory=set(cfg["mandatory_roles"])
    results=[]
    max_depth=sum(v["max_instances"] for k,v in cfg["roles"].items()
                  if k not in (source_role,sink_role))

    def walk(previous,previous_port,current_type,instances,links,counts,depth):
        if len(results)>cfg["max_candidates"]:
            raise ValueError("SEARCH_BUDGET_EXCEEDED")
        if current_type==sink["type"] and mandatory.issubset(
                set(x["role"] for x in instances)|{sink_role}):
            end={"id":sink_role+"0","role":sink_role,
                 "class_id":cfg["roles"][sink_role]["class_id"],
                 "parameters":copy.deepcopy(cfg["roles"][sink_role]["parameters"])}
            results.append({"instances":instances+[end],
                "links":links+[{"from":previous+"."+previous_port,
                                "to":end["id"]+"."+sink["name"],"adapter":None}]})
        if depth>=max_depth:
            return
        for role,inp,outp in interior:
            if counts[role]>=cfg["roles"][role]["max_instances"] or inp["type"]!=current_type:
                continue
            idx=counts[role]
            ident=role+str(idx)
            instance={"id":ident,"role":role,
                      "class_id":cfg["roles"][role]["class_id"],
                      "parameters":copy.deepcopy(cfg["roles"][role]["parameters"])}
            updated=counts.copy()
            updated[role]+=1
            new_link={"from":previous+"."+previous_port,
                      "to":ident+"."+inp["name"],"adapter":None}
            walk(ident,outp["name"],outp["type"],instances+[instance],
                 links+[new_link],updated,depth+1)

    walk(initial[0]["id"],src["name"],src["type"],initial,[],
         Counter({source_role:1}),0)
    return results


def enumerate_signal(cfg,classes,physical):
    """Connect the physical receipt input's source to a signal pathway.
    Empty pathway is permitted: physical receipt is directly displayed.
    """
    terminal_role=cfg["endpoints"]["receipt"]["role"]
    terminal=next(x for x in physical["instances"] if x["role"]==terminal_role)
    into=terminal["id"]+"."+cfg["endpoints"]["receipt"]["input"]
    prior=[x for x in physical["links"] if x["to"]==into and x["adapter"] is None]
    if len(prior)!=1:
        raise ValueError("NO_UNIQUE_RECEIPT_RATE")
    prev_port=prior[0]["from"]
    desired=cfg["endpoints"]["receipt_rate_tap"]["observable"]
    adapter=cfg["endpoints"]["receipt_rate_tap"]["id"]
    source_role=cfg["endpoints"]["source"]["role"]
    sink_role=terminal_role
    options=[]
    for role,spec in sorted(cfg["roles"].items()):
        if role in (source_role,sink_role):
            continue
        cl=classes[spec["class_id"]]
        for inp in bound_ports(cl,role,"SIGNAL","in"):
            for outp in bound_ports(cl,role,"SIGNAL","out"):
                if inp["type"]==desired and outp["type"]==desired:
                    options.append((role,inp,outp))
    result=[copy.deepcopy(physical)] # Identity reporting, with no extra information module.
    max_depth=sum(cfg["roles"][r]["max_instances"] for r,_,_ in options)

    def walk(chosen,links,counts,former,first,depth):
        if depth>0:
            result.append({"instances":physical["instances"]+copy.deepcopy(chosen),
                           "links":physical["links"]+copy.deepcopy(links)})
        if depth>=max_depth:
            return
        for role,inp,outp in options:
            if counts[role]>=cfg["roles"][role]["max_instances"]:
                continue
            ident=role+str(counts[role])
            obj={"id":ident,"role":role,
                 "class_id":cfg["roles"][role]["class_id"],
                 "parameters":copy.deepcopy(cfg["roles"][role]["parameters"])}
            edge={"from":former,"to":ident+"."+inp["name"],
                  "adapter":adapter if first else None}
            newcounts=counts.copy()
            newcounts[role]+=1
            walk(chosen+[obj],links+[edge],newcounts,
                 ident+"."+outp["name"],False,depth+1)
    walk([],[],Counter(),prev_port,True,0)
    return result


def canonical(graph):
    """Permutation-invariant for repeated same-role nodes; ignores mutable IDs.
    The bounded search is intentionally small and auditable.
    """
    import itertools
    groups=defaultdict(list)
    for x in graph["instances"]:
        groups[(x["class_id"],x["role"])].append(x["id"])
    types=sorted(groups)
    choices=[list(itertools.permutations(groups[t])) for t in types]
    hashes=[]
    for picks in itertools.product(*choices):
        mapping={}
        for label,perm in enumerate(picks):
            for idx,ident in enumerate(perm):
                mapping[ident]=f"{label}_{idx}"
        edges=sorted([[
            mapping[e["from"].split(".")[0]],e["from"].split(".")[1],
            mapping[e["to"].split(".")[0]],e["to"].split(".")[1],
            e["adapter"] or ""
        ] for e in graph["links"]])
        serial=json.dumps({"nodes":types,"edges":edges},sort_keys=True)
        hashes.append(serial)
    return hashlib.sha256(min(hashes).encode()).hexdigest()


def enumerate_graphs(cfg,classes):
    graphs=[]
    for physical in enumerate_material(cfg,classes):
        graphs.extend(enumerate_signal(cfg,classes,physical))
        if len(graphs)>cfg["max_candidates"]:
            raise ValueError("SEARCH_BUDGET_EXCEEDED")
    unique={}
    for graph in graphs:
        check_graph(graph,cfg,classes)
        key=canonical(graph)
        if key in unique:
            raise ValueError("DUPLICATE_CANONICAL_GRAPH")
        unique[key]=graph
    return [(key,unique[key]) for key in sorted(unique)]


def check_graph(graph,cfg,classes):
    roles=Counter(x["role"] for x in graph["instances"])
    for k in cfg["mandatory_roles"]:
        if roles[k]!=1:
            raise ValueError("MISSING_REQUIRED_ROLE:"+k)
    for role,spec in cfg["roles"].items():
        if roles[role]>spec["max_instances"]:
            raise ValueError("INSTANCE_LIMIT:"+role)
    inst={x["id"]:x for x in graph["instances"]}
    if len(inst)!=len(graph["instances"]):
        raise ValueError("DUPLICATE_INSTANCE")
    links=set()
    receiver_count=Counter()
    mat_next={}
    tap_count=0
    for edge in graph["links"]:
        a,ap=edge["from"].split(".")
        b,bp=edge["to"].split(".")
        if a not in inst or b not in inst:
            raise ValueError("UNKNOWN_ENDPOINT")
        ca=classes[inst[a]["class_id"]]
        cb=classes[inst[b]["class_id"]]
        outputs=[p for p in ports(ca,inst[a]["role"])
                 if p["direction"]=="out" and p["name"]==ap]
        inputs=[p for p in ports(cb,inst[b]["role"])
                if p["direction"]=="in" and p["name"]==bp]
        if len(outputs)!=1 or len(inputs)!=1:
            raise ValueError("UNKNOWN_PORT")
        pa,pb=outputs[0],inputs[0]
        typ=pa["type"]
        if edge["adapter"] is None and typ!=pb["type"]:
            raise ValueError("TYPE_MISMATCH")
        if edge["adapter"] is not None:
            adapter_id=cfg["endpoints"]["receipt_rate_tap"]["id"]
            if edge["adapter"]!=adapter_id or typ!="FLOW<Shipment>" or (
                    pb["type"]!=cfg["endpoints"]["receipt_rate_tap"]["observable"]):
                raise ValueError("INVALID_ADAPTER")
            tap_count+=1
        if pa["unit"]!=pb["unit"]:
            raise ValueError("UNIT_MISMATCH")
        key=(edge["from"],edge["to"],edge["adapter"])
        if key in links:
            raise ValueError("DUPLICATE_LINK")
        links.add(key)
        receiver_count[edge["to"]]+=1
        if typ.startswith("FLOW<") and edge["adapter"] is None:
            if a in mat_next:
                raise ValueError("MATERIAL_MULTICAST")
            mat_next[a]=b
    if max(receiver_count.values(),default=0)>1:
        raise ValueError("MULTIPLE_INCOMING")
    # One connected material path, not disconnected typed components/cycles.
    source=next(x["id"] for x in graph["instances"]
                if x["role"]==cfg["endpoints"]["source"]["role"])
    receipt=next(x["id"] for x in graph["instances"]
                 if x["role"]==cfg["endpoints"]["receipt"]["role"])
    seen=set()
    cursor=source
    while cursor is not None and cursor not in seen:
        seen.add(cursor)
        cursor=mat_next.get(cursor)
    expected={x["id"] for x in graph["instances"]
              if bound_ports(classes[x["class_id"]],x["role"],"FLOW","in")
              or x["id"]==source}
    if seen!=expected or receipt not in seen or cursor is not None:
        raise ValueError("DISCONNECTED_MATERIAL")
    # Remaining information modules form a single rooted signal path, if any.
    remaining={x["id"] for x in graph["instances"] if x["id"] not in seen}
    if bool(remaining)!=bool(tap_count) or tap_count>1:
        raise ValueError("MISSING_OR_EXTRA_TAP")
    if remaining:
        first=next((e["to"].split(".")[0] for e in graph["links"] if e["adapter"] is not None),None)
        traversed=set()
        while first is not None and first not in traversed:
            traversed.add(first)
            subsequent=[e["to"].split(".")[0] for e in graph["links"]
                        if e["adapter"] is None and e["from"].split(".")[0]==first]
            if len(subsequent)>1:
                raise ValueError("SIGNAL_MULTICAST")
            first=subsequent[0] if subsequent else None
        if traversed!=remaining or first is not None:
            raise ValueError("DISCONNECTED_INFORMATION")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--registry",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    args=ap.parse_args()
    cfg,classes,_=load_registry(args.registry)
    results=enumerate_graphs(cfg,classes)
    report={"engineering":"PASS","methodology":"ENGINEERING_ONLY",
            "registry":args.registry.name,"valid_count":len(results),
            "canonical_count":len(results),
            "graphs":[{"canonical_sha256":key,"ast":graph} for key,graph in results]}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("E1_TYPED_COMPOSITION",
          json.dumps({"registry":args.registry.name,
                      "valid":len(results),"canonical":len(results),
                      "methodology":"ENGINEERING_ONLY"}))


if __name__=="__main__":
    main()
