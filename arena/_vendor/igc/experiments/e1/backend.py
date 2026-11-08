#!/usr/bin/env python3
"""Compile validated molecular ASTs to Modelica instantiations/connections only.

The compiler receives a registry and completed AST; it does NOT choose graph
topologies or emit derivative/rate equations. Numerical mechanisms belong to
the pinned SystemDynamics/MSL packages.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import composer

HERE=Path(__file__).resolve().parent
IDENT=re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CLASS=re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$")


def trusted_name(s,regex=IDENT):
    if not regex.fullmatch(str(s)):
        raise ValueError("UNTRUSTED_MODEL_IDENTIFIER:"+str(s))
    return str(s)


def number(n):
    if type(n) not in (float,int):
        raise ValueError("UNTRUSTED_MODEL_PARAM")
    return str(n)


def render_model(name,graph,cfg,classes):
    composer.check_graph(graph,cfg,classes)
    name=trusted_name(name)
    insts=graph["instances"]
    instances={x["id"]:x for x in insts}
    by_role={}
    for x in insts:
        by_role.setdefault(x["role"],[]).append(x)
    def instance_for(role):
        opts=by_role.get(role,[])
        if len(opts)!=1:
            raise ValueError("EXPECTED_ONE_ROLE:"+role)
        return opts[0]
    source=instance_for(cfg["endpoints"]["source"]["role"])
    receipt=instance_for(cfg["endpoints"]["receipt"]["role"])
    dispatch=instance_for(cfg["endpoints"]["dispatch_observation"]["role"])
    receipt_port=cfg["endpoints"]["receipt"]["input"]
    delivery_links=[x for x in graph["links"] if x["to"]==receipt["id"]+"."+receipt_port
                    and x["adapter"] is None]
    if len(delivery_links)!=1:
        raise ValueError("BAD_RECEIPT")
    delivered_by=delivery_links[0]["from"]
    src_in=cfg["endpoints"]["source"]["stimulus_input"]
    source_out=cfg["endpoints"]["source"]["output"]
    if not any(p["name"]==src_in and p["direction"]=="in" for p in composer.ports(
           classes[source["class_id"]],source["role"])):
        raise ValueError("SOURCE_STIMULUS_PORT_NOT_FOUND")
    lines=[
        "  model "+name,
        "    parameter Integer probe(min=1,max=4)=1;",
        "    Modelica.Blocks.Sources.Pulse pulse(amplitude=6,period=4,width=40,startTime=1);",
        "    Modelica.Blocks.Sources.Step step(height=6,startTime=1);",
        "    Modelica.Blocks.Sources.Ramp ramp(height=6,duration=3,startTime=1);",
        "    Modelica.Blocks.Sources.Pulse highPulse(amplitude=14,period=4,width=40,startTime=1);",
        "    Modelica.Blocks.Sources.RealExpression stimulus(",
        "      y=if probe==1 then pulse.y else if probe==2 then step.y else",
        "        if probe==3 then ramp.y else highPulse.y);"
    ]
    for ins in insts:
        trusted_name(ins["id"])
        cl=classes[ins["class_id"]]
        full=trusted_name(cl["modelica"],CLASS)
        params=ins["parameters"]
        for key,value in params.items():
            trusted_name(key)
            bounds=cl["parameters"][key]
            if not bounds["min"]<=value<=bounds["max"]:
                raise ValueError("PARAMETER_NOT_ADMISSIBLE")
        kw=("("+",".join(trusted_name(k)+"="+number(v) for k,v in sorted(params.items()))+")") if params else ""
        lines.append("    "+full+" "+ins["id"]+kw+";")
    lines.extend([
        "    Real dispatchRate;",
        "    Real deliveryRate;",
        "    Real inTransit;",
        "    Real reportedDeliveryRate;",
        "    Real deliveredTotal;",
        "  equation",
        "    connect(stimulus.y,"+source["id"]+"."+src_in+");"
    ])
    for edge in graph["links"]:
        lines.append("    connect("+edge["from"]+","+edge["to"]+");")
    lines.append("    dispatchRate="+dispatch["id"]+"."+
                 cfg["endpoints"]["dispatch_observation"]["output"]+";")
    lines.append("    deliveryRate="+delivered_by+";")
    lines.append("    deliveredTotal="+receipt["id"]+"."+
                 cfg["endpoints"]["receipt"]["total_output"]+";")
    # All state outputs labeled STATE<Shipment> are summed automatically, based on ports.
    stock_terms=[]
    for ins in insts:
        for p in composer.ports(classes[ins["class_id"]],ins["role"]):
            if p["direction"]=="out" and p["type"]=="STATE<Shipment>":
                stock_terms.append(ins["id"]+"."+p["name"])
    lines.append("    inTransit="+(" + ".join(stock_terms) if stock_terms else "0")+";")
    signal_instances=[x for x in insts if any(
        p["direction"]=="in" and p["type"]=="SIGNAL<DeliveryRate>"
        for p in composer.ports(classes[x["class_id"]],x["role"]))]
    if signal_instances:
        end_nodes={x["id"] for x in signal_instances}
        for link in graph["links"]:
            if link["adapter"] is None and link["from"].split(".")[0] in end_nodes:
                end_nodes.discard(link["from"].split(".")[0])
        if len(end_nodes)!=1:
            raise ValueError("SIGNAL_TERMINAL_NOT_UNIQUE")
        last=next(x for x in signal_instances if x["id"] in end_nodes)
        out_ports=[p for p in composer.ports(classes[last["class_id"]],last["role"])
                   if p["direction"]=="out" and p["type"]=="SIGNAL<DeliveryRate>"]
        if len(out_ports)!=1:
            raise ValueError("BAD_INFORMATION_OUTPUT")
        lines.append("    reportedDeliveryRate="+last["id"]+"."+out_ports[0]["name"]+";")
    else:
        lines.append("    reportedDeliveryRate=deliveryRate;")
    lines.append("  end "+name+";")
    return "\n".join(lines)


def build(cfg,classes,graphs,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/"results").mkdir(parents=True,exist_ok=True)
    prefix="B" if not cfg.get("new_classes") else "X"
    models=[]
    rows=[]
    for i,(hash_value,graph) in enumerate(graphs):
        model_name="Composition"+prefix+str(i).zfill(3)
        models.append(render_model(model_name,graph,cfg,classes))
        roles=Counter(x["role"] for x in graph["instances"])
        rows.append({"model":model_name,"hash":hash_value,
                     "roles":dict(sorted(roles.items())),
                     "instances":graph["instances"],"links":graph["links"]})
    modelica="within;\npackage IGCE1Generated\n"+"\n\n".join(models)+(
        '\n  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));\n'
        "end IGCE1Generated;\n")
    if "der(" in modelica or "when " in modelica:
        raise ValueError("DYNAMIC_EQUATION_FROM_COMPOSER")
    (out/"IGCE1Generated.mo").write_text(modelica,encoding="utf-8")
    script=['getVersion();','loadModel(Modelica, {"4.0.0"});',
            'loadModel(SystemDynamics, {"2.1.2"});',
            'loadFile("../../src/modelica/IGCMolecules.mo");',
            'loadFile("../../src/modelica/IGCInformationMolecules.mo");',
            'loadFile("generated/'+out.name+'/IGCE1Generated.mo");']
    for x in rows:
        name=x["model"]
        script.append("checkModel(IGCE1Generated."+name+");")
        script.append(
            "simulate(IGCE1Generated."+name+
            ',startTime=0,stopTime=8,numberOfIntervals=64,method="dassl",'+
            'tolerance=1e-8,outputFormat="csv",fileNamePrefix="generated/'+out.name+'/results/'+
            name+'");')
    script.append("getErrorString();")
    (out/"run.mos").write_text("\n".join(script)+"\n",encoding="utf-8")
    (out/"models.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
    print("E1_MODELICA_BACKEND",json.dumps({
        "registry_variant":prefix,"graphs":len(rows),"mechanism":"original_library_classes_only",
        "verdict":"ENGINEERING_ONLY"}))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    cfg,cl,_=composer.load_registry(args.registry)
    build(cfg,cl,composer.enumerate_graphs(cfg,cl),args.out)


if __name__=="__main__":
    main()
