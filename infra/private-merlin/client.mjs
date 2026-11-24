// Local Wrangler adapter. The remote target is a named private service binding.
export default {
  async fetch(request,env){
    const url=new URL(request.url);
    const operation=url.pathname.slice(1);
    if(url.hostname!=='127.0.0.1' || request.method!=='POST' || request.headers.has('origin') ||
       request.headers.get('x-arena-client')!=='private-merlin-v1' || url.search ||
       !['submit','read'].includes(operation))return new Response(null,{status:404});
    try{
      const reader=request.body.getReader();
      const parts=[];
      let bytes=0;
      try{
        for(;;){
          const {done,value}=await reader.read();
          if(done)break;
          bytes+=value.byteLength;
          if(bytes>131072)return new Response(null,{status:413});
          parts.push(value);
        }
      }finally{await reader.cancel();}
      const input=JSON.parse(await new Blob(parts).text());
      const result=operation==='submit'?await env.MERLIN.submit(input):await env.MERLIN.read(input);
      return result ? Response.json(result) : new Response(null,{status:404});
    }catch{return new Response(null,{status:409});}
  }
};
