// Run the exact native functional suite inside WebAssembly, with no browser UI.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {writeFileSync} from 'node:fs';
const [bundleArg,reportArg]=process.argv.slice(2);
if(!bundleArg||!reportArg)throw Error('Usage: node emulator/test_wasm.mjs BUNDLE REPORT');
const bundle=resolve(bundleArg),report=resolve(reportArg);
const create=(await import(pathToFileURL(bundle+'/check.mjs'))).default;
const core=await create({locateFile:name=>bundle+'/'+name,print:console.log,printErr:console.error});
const exit=core.callMain(['/data','/wasm-full.json','optimized','full']);
if(exit)throw Error('WebAssembly checks failed: '+exit);
writeFileSync(report,core.FS.readFile('/wasm-full.json'));
