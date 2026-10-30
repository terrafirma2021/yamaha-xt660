// CPU addresses; file-base subtraction is handled by the shared feature writer.
// Both lookup/consumer families are executed by test_co_override.py for every BIN.
export const coLayouts = {
  early:{descriptor:0x34B0,entry:0x800C,stop:0x8031,speed:0x0900,setting:0x09FC,gain:0x09A0,trim:0x095C,
    code:[
      [0x800C,'ce34b0fc090016c1f27a09a01e0a16020bf609fc1686237a095c2009f60a001686237a095d'],
      [0x8623,'c0802419cb8086801816f609a012c30080180e8680181624118600200db609a012c300808b80240286ff3d'],
      [0xD0F5,'b60aed7a09fc1c088f80']
    ]},
  late:{descriptor:0x3478,entry:0x768E,stop:0x76A3,speed:0x0920,setting:0x0A00,gain:0x099E,trim:0x0964,
    code:[
      [0x768E,'ce3478fc092016bbcf7a099ef60a00167a2b7a0964'],
      [0x7A2B,'c0802419cb8086801816f6099e12c30080180e8680181624118600200db6099e12c300808b80240286ff3d'],
      [0xC955,'b60b117a0a001c089080']
    ]}
};
const guards=(address,hex)=>hex.match(/../g).map((v,i)=>[address+i,parseInt(v,16)]);
export function coDefinition(identity){
  const f=coLayouts[identity?.code_family];
  return {id:'co-range',name:'CO full-range override',mapBacked:true,
    ...(f?{
      bytes:Array.from({length:15},(_,i)=>({address:f.descriptor+6+i,on:255,off:i<13?255:0})),
      guards:[...guards(f.descriptor,'14001c000080'),...f.code.flatMap(([a,hex])=>guards(a,hex))]
    }:{})};
}
