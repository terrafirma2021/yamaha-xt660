// Pure offline operations. No serial transport and no implicit checksum repair.
export const hex=(n,width=4)=>'0x'+n.toString(16).toUpperCase().padStart(width,'0');
export async function sha256(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')}
export function baseAddress(bytes){if(bytes.length===65536)return 0;if(bytes.length===59392)return 0x1800;throw Error('Expected a 65,536-byte or 59,392-byte BIN. No padding or truncation is performed.')}
export function wordSum(bytes,base,start=0x1800,end=0xF800){
  if(start<base||end>base+bytes.length||start%2||end%2||end<=start)throw Error('Checksum range is outside the file');
  let sum=0;for(let a=start-base;a<end-base;a+=2)sum=(sum+(bytes[a]<<8)+bytes[a+1])&65535;return sum;
}
export function inspect(bytes){const base=baseAddress(bytes);const boot=bytes.subarray(0xF800-base);return {bytes:bytes.length,base_address:base,end_address:base+bytes.length-1,application_word_sum:hex(wordSum(bytes,base)),boot:boot.every(b=>b===255)?'FF placeholder — boot not captured':'Populated — content identity requires matching',terminal_marker:hex((bytes[0xF7FE-base]<<8)|bytes[0xF7FF-base]),full_backup_verified:false}}
// These anchors cover the startup caller and the recovered summation/compare code.
// The compensation location is reviewed trailer padding, not a factory checksum field.
const CHECKSUM_PROFILES={
  early:{caller:0x5358,call:'ccf7ff16a489',routine:0xA489,code:'4df080165fa47c0ddece180087c7e3003431b7c6841f8c1000b7c62603165fa408082705be0dde23e5b7c6c6008daa552702c6ff'},
  late:{caller:0x4B65,call:'ccf7ff16971d',routine:0x971D,code:'4df0801656b17c0e62ce180087c7e3003431b7c6841f8c1000b7c626031656b108082705be0e6223e5b7c6c6008daa552702c6ff'}
};
export function verifyStartupChecksum(bytes,identity){
  const base=baseAddress(bytes),actual=wordSum(bytes,base),profile=CHECKSUM_PROFILES[identity?.code_family];
  const matches=(address,code)=>Array.from(bytes.slice(address-base,address-base+code.length/2),b=>b.toString(16).padStart(2,'0')).join('')===code;
  const supported=!!profile&&matches(profile.caller,profile.call)&&matches(profile.routine,profile.code)&&matches(0xF7FE,'5aa5');
  return {status:supported?(actual===0xAA55?'pass':'fail'):'unverified',actual:hex(actual),expected:supported?'0xAA55':null,range:'0x1800–0xF7FF',family:supported?identity.code_family:null,scope:'Application startup checksum only; hardware and flash readiness are not verified'};
}
export function correctStartupChecksum(bytes,identity){
  const check=verifyStartupChecksum(bytes,identity);
  if(check.status==='unverified')throw Error('No verified startup checksum profile for this BIN; automatic correction is unavailable');
  const base=baseAddress(bytes),offset=0xF7FC-base,before=(bytes[offset]<<8)|bytes[offset+1];
  const after=(before+0xAA55-Number(check.actual))&65535;
  bytes[offset]=after>>8;bytes[offset+1]=after&255;
  const verified=verifyStartupChecksum(bytes,identity);
  if(verified.status!=='pass')throw Error('Startup checksum correction failed verification');
  return {...verified,compensation_address:'0xF7FC',compensation_before:hex(before),compensation_after:hex(after),changed:before!==after,method:'Analyst-selected trailer compensation; not an identified factory checksum field'};
}
export function differences(a,b,base){if(a.length!==b.length)throw Error('BIN sizes differ. Compare like-for-like captures; files are not silently padded.');const out=[];for(let i=0;i<a.length;i++)if(a[i]!==b[i])out.push({address:base+i,file_offset:i,before:a[i],after:b[i]});return out}
export function cellOffset(bytes,base,map,index){
  if(!map||![1,2].includes(map.element_bytes)||(map.element_bytes===2&&map.byte_order!=='big')||!Number.isInteger(map.rows)||map.rows<1||!Number.isInteger(map.columns)||map.columns<1)throw Error('Invalid map layout');
  const start=Number(map.data_address),end=start+map.rows*map.columns*map.element_bytes;
  if(!Number.isInteger(start)||start<Math.max(base,0x1800)||end>Math.min(base+bytes.length,0xF800)||Number(map.end_exclusive)!==end)throw Error('Map is outside the calibration image');
  if(!Number.isInteger(index)||index<0||index>=map.rows*map.columns)throw Error('Cell is outside this map');
  return start-base+index*map.element_bytes;
}
export function readCell(bytes,base,map,index){const o=cellOffset(bytes,base,map,index);return map.element_bytes===2?(bytes[o]<<8)|bytes[o+1]:bytes[o]}
export function editCell(bytes,base,map,index,value){
  const offset=cellOffset(bytes,base,map,index),max=map.element_bytes===2?65535:255;
  if(!Number.isInteger(value)||value<0||value>max)throw Error('Enter a whole raw value from 0 to '+max);
  const before=readCell(bytes,base,map,index);if(map.element_bytes===2){bytes[offset]=value>>8;bytes[offset+1]=value&255}else bytes[offset]=value;
  return {map:map.id,index,address:offset+base,before,after:value};
}
export function parseHex(text){const s=text.trim().replace(/0x/gi,'').replace(/[\s,:-]/g,'');if(s.length%2||!/^[0-9a-f]*$/i.test(s))throw Error('Enter complete hexadecimal bytes');return Uint8Array.from(s.match(/../g)||[],b=>parseInt(b,16))}
export const hexBytes=bytes=>Array.from(bytes,b=>b.toString(16).toUpperCase().padStart(2,'0')).join(' ');
export const READ_LENGTHS=[2,16,512,2048,256,1024];
export function bootReadPreview(address,mode){
  if(!Number.isInteger(address)||address<0||address>65535||!Number.isInteger(mode)||mode<0||mode>=READ_LENGTHS.length||address+READ_LENGTHS[mode]>65536)throw Error('Invalid address or read range');
  const b=Uint8Array.of(3,mode,0,7,address>>8,address&255,0);b[6]=(-b.slice(0,6).reduce((a,v)=>a+v,0))&255;return b;
}
export function decodeBootFrame(bytes){
  if(bytes.length<5)throw Error('A complete boot frame needs at least five bytes');
  const length=(bytes[2]<<8)|bytes[3];
  if(bytes[0]>15||length!==bytes.length||length>0x805)throw Error('Not a complete frame in the recovered boot format');
  if(bytes.reduce((s,b)=>s+b,0)&255)throw Error('Boot checksum does not sum to zero');
  return {command:hex(bytes[0],2),parameter_or_status:hex(bytes[1],2),length,payload:hexBytes(bytes.slice(4,-1)),checksum:'Sum modulo 256 = 0',interpretation:'Framing match only; direction, session and hardware acceptance are not established'};
}
export function decodeApplicationFrame(bytes){if(bytes.length!==5)throw Error('The application reply is exactly five bytes');if((bytes.slice(0,4).reduce((a,b)=>a+b,0)&255)!==bytes[4])throw Error('Application checksum mismatch');return {rpm_code:bytes[0],speed_code:bytes[1],status:hex(bytes[2],2),selected_value:bytes[3],interpretation:'Raw application payload only; mode and engineering scales are not inferred'}}
