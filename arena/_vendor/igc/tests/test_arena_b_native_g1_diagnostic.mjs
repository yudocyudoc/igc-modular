import test from "node:test";
import assert from "node:assert/strict";
import {diagnose} from "../scripts/arena_b_native_g1_diagnostic.mjs";
const base=()=>({model:{variables:[
{name:"Backlog",type:"stock",units:"items",equation:"0",inflows:["Arrivals"],outflows:["Completions"]},
{name:"Arrivals",type:"flow",units:"items/hour",equation:"1"},
{name:"Completions",type:"flow",units:"items/hour",equation:"MIN(2, Backlog / 1)"}],
relationships:[{from:"Arrivals",to:"Backlog",polarity:"+"}]}});
test("clean fixture is not certified G1",()=>{
 const original=base(),before=JSON.stringify(original),r=diagnose(original);
 assert.equal(r.issues.length,0);assert.equal(r.g1_certified,false);
 assert.equal(r.status,"PREFLIGHT_NO_OBVIOUS_ISSUES_NOT_G1_PASS");
 assert.equal(JSON.stringify(original),before);
});
test("native prose and ambiguous division remain unchanged and are diagnosed",()=>{
 const m=base();m.model.variables[1].equation="PULSE profile over time";
 m.model.variables[2].equation="Backlog // processing_signal";
 const r=diagnose(m);const codes=r.issues.map(i=>i.code);
 assert(codes.includes("PROSE_OR_PLACEHOLDER"));
 assert(codes.includes("ZERO_SAFE_DIVISION_REQUIRES_ADAPTER"));
 assert(codes.includes("PROSE_OR_PLACEHOLDER"));
 assert(!codes.includes("AMBIGUOUS_COMMENT_OR_OPERATOR"));
 assert(codes.includes("UNRESOLVED_SYMBOL"));
 assert.equal(m.model.variables[2].equation,"Backlog // processing_signal");
});
test("missing connections and dimensional mismatch are recorded",()=>{
 const m=base();m.model.variables[0].outflows=["Missing"];
 m.model.variables[1].units="hour";
 const r=diagnose(m);
 assert(r.issues.some(i=>i.code==="UNRESOLVED_FLOW_PORT"));
 assert(r.issues.some(i=>i.code==="STOCK_FLOW_UNIT_MISMATCH"));
});
test("invalid provider output cannot be declared successful",()=>{
 const r=diagnose({err:"ResponseFormatError"});
 assert.equal(r.status,"G1_ISSUES_FOUND");
 assert(r.issues.some(i=>i.code==="VARIABLES_MISSING"));
 assert.equal(r.g2_executed,false);
});

test("Buffalo zero-safe division is a translation limitation, not an invalid equation",()=>{
 const m=base();m.model.variables.push({name:"Reference",type:"variable",units:"items",equation:"1"});
 m.model.variables.push({name:"Ratio",type:"variable",units:"dimensionless",equation:"Backlog // Reference"});
 const r=diagnose(m);
 assert(r.issues.some(x=>x.code==="ZERO_SAFE_DIVISION_REQUIRES_ADAPTER"&&x.category==="ADAPTER"));
 assert(!r.issues.some(x=>x.code==="AMBIGUOUS_COMMENT_OR_OPERATOR"));
 assert.equal(r.g1_certified,false);
});
test("detects unit product contradiction in the real style",()=>{
 const m=base();m.model.variables.push({name:"processing signal",type:"variable",units:"items",equation:"Backlog"});
 m.model.variables.push({name:"completion capacity",type:"variable",units:"items per hour",equation:"1"});
 m.model.variables[2].equation="completion_capacity * processing_signal";
 const r=diagnose(m);
 assert(r.issues.some(x=>x.code==="DIMENSIONAL_PRODUCT_MISMATCH"));
});

test("graphical function is adapter-obligation, not ignored or auto G1-pass",()=>{
 const m=base();
 m.model.variables.push({name:"pulse shape",type:"variable",units:"dimensionless",
   equation:"TIME",graphicalFunction:{points:[{x:0,y:0},{x:0.001,y:1},{x:2,y:1}]}});
 const r=diagnose(m);
 assert(r.issues.some(x=>x.code==="GRAPHICAL_LOOKUP_NEEDS_ADAPTER"&&x.category==="ADAPTER"));
 assert(!r.issues.some(x=>x.code==="MALFORMED_GRAPHICAL_FUNCTION"));
 const bad=base();
 bad.model.variables.push({name:"Lookup",type:"variable",equation:"TIME",
   graphicalFunction:{points:[{x:0,y:1},{x:0,y:0}]}});
 assert(diagnose(bad).issues.some(x=>x.code==="MALFORMED_GRAPHICAL_FUNCTION"));
});

test("pinned Buffalo one-point placeholders are not malformed curves",()=>{
 const m=base();m.model.variables[1].graphicalFunction={points:[{x:0,y:0}]};
 const before=JSON.stringify(m),r=diagnose(m);
 assert.equal(r.one_point_graphical_markers.length,1);
 assert(!r.issues.some(x=>x.code==="MALFORMED_GRAPHICAL_FUNCTION"));
 assert(!r.issues.some(x=>x.code==="GRAPHICAL_LOOKUP_NEEDS_ADAPTER"));
 assert.equal(JSON.stringify(m),before);
});
test("native upstream ignores graphical functions on flows",()=>{
 const m=base();m.model.variables[1].graphicalFunction={points:[{x:0,y:0},{x:1,y:1}]};
 const r=diagnose(m);
 assert(r.issues.some(x=>x.code==="UPSTREAM_FLOW_LOOKUP_IGNORED"&&x.category==="G1"));
});
test("normalized upstream variable references do not become callable functions",()=>{
 const m=base();m.model.variables.push({name:"Arrival Input by Time",type:"variable",
   equation:"0",graphicalFunction:{points:[]}});
 m.model.variables[1].equation="arrival_input_by_time";
 assert(!diagnose(m).issues.some(x=>x.code==="UNRESOLVED_SYMBOL"));
 m.model.variables[1].equation="arrival_input_by_time(TIME)";
 assert(diagnose(m).issues.some(x=>x.code==="VARIABLE_CALLED_AS_FUNCTION"));
 m.model.variables[1].equation="unwritten_kernel(TIME)";
 assert(diagnose(m).issues.some(x=>x.code==="UNDECLARED_FUNCTION_CALL"));
});
test("colliding upstream-folded names are rejected, not arbitrarily resolved",()=>{
 const m=base();m.model.variables.push({name:"Arrival Rate",type:"variable",equation:"0"});
 m.model.variables.push({name:"arrival_rate",type:"variable",equation:"0"});
 assert(diagnose(m).issues.some(x=>x.code==="AMBIGUOUS_UPSTREAM_NORMALIZED_NAME"));
});
