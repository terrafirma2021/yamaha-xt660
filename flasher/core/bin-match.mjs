import {featureStates,matchesFeatureVariant} from './tools-features.mjs';
import {speedState} from './tools-speed.mjs';
import {cellOffset,baseAddress} from './tools-core.mjs';
export function matchesMapVariant(bytes,reference,identity,maps){
  // Custom map-backed feature cells remain legitimate map edits. Normalizing
  // map bodies below still leaves every instruction/header guard to be checked.
  if(bytes.length!==reference.length||!maps.length||!speedState(bytes,identity).editable||featureStates(bytes,identity).some(f=>f.bytes&&!f.editable&&!f.mapBacked))return false;
  try{const base=baseAddress(bytes),normal=bytes.slice();for(const m of maps){const start=cellOffset(bytes,base,m,0),end=cellOffset(bytes,base,m,m.rows*m.columns-1)+m.element_bytes;normal.set(reference.subarray(start,end),start)}return matchesFeatureVariant(normal,reference,identity)}catch{return false}
}
