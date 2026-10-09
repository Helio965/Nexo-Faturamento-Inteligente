import {bundle} from '@remotion/bundler';
import {selectComposition,renderMedia,renderStill} from '@remotion/renderer';
import {existsSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {exportAssets} from './export.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.resolve(root,'../../static/video');
const temp=path.join(root,'out');
mkdirSync(output,{recursive:true});mkdirSync(temp,{recursive:true});
if(!existsSync(path.join(root,'public/audio.wav'))) throw Error('Run python3 scripts/audio.py first.');
const browserExecutable=process.env.CHROME_PATH || ['/usr/bin/chromium','/usr/bin/google-chrome'].find(existsSync);
const serveUrl=await bundle({entryPoint:path.join(root,'src/index.tsx'),publicDir:path.join(root,'public')});
const options={serveUrl,browserExecutable,chromiumOptions:{gl:'swangle'}};
const composition=await selectComposition({...options,id:'NexoFilm'});
for(const frame of [100,290,530,780,870,955,1125]){
 await renderStill({...options,composition,frame,output:path.join(temp,`frame-${frame}.png`),imageFormat:'png'});
 console.log(`Still ${frame}/1200`);
}
await renderStill({...options,composition,frame:1125,output:path.join(output,'nexo_demo_poster.png'),imageFormat:'png'});
if(process.argv.includes('--stills')) process.exit(0);
let last=-1;
await renderMedia({...options,composition,codec:'h264',pixelFormat:'yuv420p',crf:21,audioCodec:'aac',audioBitrate:'160k',outputLocation:path.join(temp,'film.mp4'),concurrency:4,onProgress:({progress})=>{
 const percent=Math.floor(progress*100/10)*10;if(percent!==last){last=percent;console.log(`Rendering ${percent}%`);}
}});
exportAssets();
console.log('Exported MP4, animated GIF and poster to static/video.');
