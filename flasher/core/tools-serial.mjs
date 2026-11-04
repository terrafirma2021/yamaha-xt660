// Receive-only adapter. Deliberately has no writer or command-dispatch API.
export class SerialCapture{
  constructor({onChunk=()=>{},onState=()=>{},limit=2*1024*1024}={}){this.onChunk=onChunk;this.onState=onState;this.limit=limit;this.port=null;this.reader=null;this.chunks=[];this.count=0;this.busy=false;this.stopping=false;this.task=null;this.error=null}
  async connect(port,baudRate){
    if(this.busy||this.port)throw Error('Disconnect the current port first');
    if(!Number.isInteger(baudRate)||baudRate<300||baudRate>1000000)throw Error('Enter the baud rate for your interface');
    this.busy=true;this.error=null;this.stopping=false;
    try{await port.open({baudRate,dataBits:8,stopBits:1,parity:'none',flowControl:'none'});this.port=port;this.chunks=[];this.count=0;this.started=new Date().toISOString();this.baudRate=baudRate;this.onState('Receiving — no bytes transmitted');this.task=this.receive()}
    finally{this.busy=false}
  }
  async receive(){
    const port=this.port;
    try{
      if(!port.readable)throw Error('Port has no readable stream');
      this.reader=port.readable.getReader();
      while(!this.stopping){const {value,done}=await this.reader.read();if(done)break;
        if(value){const bytes=value.slice(0,this.limit-this.count);if(bytes.length){const item={elapsed_ms:Date.now()-Date.parse(this.started),bytes:hex(bytes)};this.chunks.push(item);this.count+=bytes.length;this.onChunk(item,this.count)}
          if(this.count>=this.limit){this.error='Capture limit reached; disconnected. Save the capture before starting again.';break}}
      }
    }catch(e){if(!this.stopping)this.error=e.message}
    finally{this.reader?.releaseLock();this.reader=null;try{await port.close()}catch(e){this.error=this.error||e.message}this.port=null;this.onState(this.error||'Disconnected')}
  }
  async disconnect(){this.stopping=true;await this.reader?.cancel();await this.task}
  report(){return {schema_version:1,kind:'receive-only serial capture, not an ECU memory dump',started_utc:this.started,baud_rate:this.baudRate,data_bits:8,stop_bits:1,parity:'none',bytes_received:this.count,limit_bytes:this.limit,termination:this.error,frame_boundaries_known:false,chunks:this.chunks}}
}
function hex(bytes){return Array.from(bytes,b=>b.toString(16).toUpperCase().padStart(2,'0')).join(' ')}
