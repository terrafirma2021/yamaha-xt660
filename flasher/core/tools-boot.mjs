// Offline XT read transactions. No serial access, session entry or flash commands.
import {bootReadPreview, decodeBootFrame} from './tools-core.mjs';

export const XT_BOOT_PROFILE = Object.freeze({baudRate:9600, dataBits:8, parity:'none', stopBits:1,
  start:0x1800, endExclusive:0x10000, blockSize:512, mode:2, hardwareValidated:false});

function checkAddress(address){
  if(!Number.isInteger(address)||address<0x1800||address>=0x10000||(address-0x1800)%512)
    throw Error('Address must identify a 512-byte XT read block from 1800 to FE00');
}

export function xtReadPlan(){
  return Array.from({length:116},(_,i)=>{
    const address=0x1800+i*512;
    return {address,length:512,request:bootReadPreview(address,2)};
  });
}

// One outstanding request only: the response does not repeat its address.
// Echo mode must be explicit; never guess it from a coincidental matching byte.
export class BootReadTransaction {
  #request; #received; #count=0; #payload=null; #failed=false; #address; #echo;
  constructor(address,{echo=true}={}){
    checkAddress(address);
    if(typeof echo!=='boolean')throw Error('Echo must be true or false');
    this.#address=address;this.#echo=echo;this.#request=bootReadPreview(address,2);
    this.#received=new Uint8Array((echo?7:0)+517);
  }
  get address(){return this.#address}
  get request(){return this.#request.slice()}
  get complete(){return this.#payload!==null&&!this.#failed}
  feed(chunk){
    if(!(chunk instanceof Uint8Array))throw Error('Received bytes must be a Uint8Array');
    if(this.#failed)throw Error('Transaction failed; discard it');
    try{
      if(this.complete||this.#count+chunk.length>this.#received.length)throw Error('Unexpected extra bytes in read transaction');
      this.#received.set(chunk,this.#count);this.#count+=chunk.length;
      const offset=this.#echo?7:0;
      for(let i=0;i<Math.min(offset,this.#count);i++)
        if(this.#received[i]!==this.#request[i])throw Error('Cable echo differs from request');
      if(this.#count>=offset+4){
        const h=this.#received.subarray(offset,offset+4);
        if(h[0]!==3||h[1]!==0)throw Error('ECU reply has wrong command or nonzero status');
        if((h[2]<<8|h[3])!==517)throw Error('ECU reply is not a 512-byte read');
      }
      if(this.#count===this.#received.length){
        const frame=this.#received.subarray(offset);decodeBootFrame(frame);
        this.#payload=frame.slice(4,-1);
      }
      return this.complete;
    }catch(error){this.#failed=true;this.#payload=null;throw error}
  }
  finish(){
    if(!this.complete)throw Error('Read transaction incomplete or failed');
    return this.#payload.slice();
  }
}

export class XtReadAssembly {
  #bytes=new Uint8Array(0xE800); #coverage=new Set();
  add(transaction){
    if(!(transaction instanceof BootReadTransaction))throw Error('A checked read transaction is required');
    const address=transaction.address;
    if(this.#coverage.has(address))throw Error('Duplicate read block');
    const payload=transaction.finish();
    this.#bytes.set(payload,address-0x1800);this.#coverage.add(address);
  }
  get blocksReceived(){return this.#coverage.size}
  finish(){
    if(this.#coverage.size!==116)throw Error('Read coverage incomplete');
    // Preserve source bytes, including a failing startup checksum. Correction belongs to an editable copy.
    return this.#bytes.slice();
  }
}
