import {test} from "node:test";
import assert from "node:assert/strict";
import {CF_MODEL,OR_SLUG,requestToCloudflare,responseToOpenRouter} from "../scripts/arena_b_cf_protocol_adapter.mjs";

const schema={type:"object",properties:{variables:{type:"array"},relationships:{type:"array"}},
 required:["variables","relationships"],additionalProperties:false};
const original={model:OR_SLUG,
  messages:[{role:"system",content:"U-Buffalo method unchanged"},{role:"user",content:"Situation A"}],
  response_format:{type:"json_schema",json_schema:{name:"sdai_schema",strict:true,schema}},
  max_completion_tokens:8000};

test("original Buffalo schema is forwarded unchanged, not a wrapper",()=>{
 const out=requestToCloudflare(original);
 assert.deepEqual(out.messages,original.messages);
 assert.deepEqual(out.response_format,{type:"json_schema",json_schema:schema});
 assert.equal(out.max_completion_tokens,3500);
 assert.equal(out.reasoning_effort,"low");
 assert.equal(out.stream,false);
 assert.equal(CF_MODEL,"@cf/zai-org/glm-5.3-flash");
});
test("model content from Cloudflare is serialized without changing structural semantics",()=>{
 const generated={variables:[{name:"A",type:"stock",equation:"0"}],relationships:[]};
 const out=responseToOpenRouter({success:true,result:{response:generated,
   usage:{prompt_tokens:12,completion_tokens:34}}},"sha256:"+"a".repeat(64));
 assert.deepEqual(JSON.parse(out.choices[0].message.content),generated);
 assert.equal(out.system_fingerprint,"igc-cloudflare-compat-v01");
 assert.equal(out.model,OR_SLUG);
 assert.equal(out.usage.completion_tokens,34);
});
test("non-JSON text is neither repaired nor completed",()=>{
 const out=responseToOpenRouter({success:true,result:{response:"text with no JSON"}},"sha256:"+"0".repeat(64));
 assert.equal(out.choices[0].message.content,"text with no JSON");
 assert.throws(()=>JSON.parse(out.choices[0].message.content));
});
test("fail closed for missing schema, incorrect route, corrupt server result",()=>{
 assert.throws(()=>requestToCloudflare({...original,model:"molecular"}),/OPENROUTER_MODEL_MISMATCH/);
 assert.throws(()=>requestToCloudflare({...original,response_format:{type:"json_object"}}),/BUFFALO_SCHEMA_NOT_REQUESTED/);
 assert.throws(()=>responseToOpenRouter({success:false,result:{response:"{}"}},"hash"),/WORKERS_AI_UNSUCCESSFUL/);
 assert.throws(()=>responseToOpenRouter({success:true,result:{response:""}},"hash"),/WORKERS_AI_NO_CONTENT/);
});
