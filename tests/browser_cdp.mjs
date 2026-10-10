// Control only the disposable browser launched by the sandboxed Python probe.
// Node's built-in WebSocket avoids an additional browser automation dependency.
import assert from 'node:assert/strict';

const [socketURL, pageURL]=process.argv.slice(2);
assert.match(socketURL,/^ws:\/\/127\.0\.0\.1:\d+\//);
assert.match(pageURL,/^http:\/\/127\.0\.0\.1:\d+\//);
const socket=new WebSocket(socketURL);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let sequence=0;
const outstanding=new Map();
socket.addEventListener('message',event=>{
  const message=JSON.parse(event.data);
  if(message.id&&outstanding.has(message.id)){
    const {resolve,reject,timer}=outstanding.get(message.id);outstanding.delete(message.id);clearTimeout(timer);
    message.error?reject(new Error(message.error.message)):resolve(message.result);
  }
});
const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
  const id=++sequence;
  const timer=setTimeout(()=>{outstanding.delete(id);reject(new Error('Bounded DevTools request timed out: '+method));},5000);
  outstanding.set(id,{resolve,reject,timer});
  socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
});
try{
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  await send('Page.enable',{},sessionId);
  await send('Runtime.enable',{},sessionId);
  await send('Page.navigate',{url:pageURL},sessionId);
  const deadline=Date.now()+45000;
  let result;
  while(Date.now()<deadline){
    try{
      const current=await send('Runtime.evaluate',{expression:'document.querySelector("#browser-result")?.textContent||null',returnByValue:true},sessionId);
      if(current.result.value){result=JSON.parse(current.result.value);break;}
    }catch(error){if(!/context|navigation/i.test(error.message))throw error;}
    await new Promise(resolve=>setTimeout(resolve,75));
  }
  assert.ok(result,'The disposable browser did not complete its workflow within 45 seconds.');
  console.log(JSON.stringify(result));
  await send('Target.closeTarget',{targetId});
}finally{
  socket.close();
}
