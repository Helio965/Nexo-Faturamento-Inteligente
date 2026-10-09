import {spawnSync} from 'node:child_process';
import {mkdirSync,renameSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.resolve(root,'../../static/video');
const temp=path.join(root,'out');
const run=(args)=>{const r=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-y',...args],{stdio:'inherit'});if(r.status!==0)throw Error('FFmpeg export failed');};

export const exportAssets = () => {
 mkdirSync(output,{recursive:true});
 // Chromium intermediates can carry full-range flags. Convert actual levels
 // to limited/TV range, then explicitly signal yuv420p for browser playback.
 // Never relabel full-range samples without converting them.
 const mp4=path.join(temp,'web.mp4');
 run(['-i',path.join(temp,'film.mp4'),'-vf','scale=in_range=pc:out_range=tv,format=yuv420p',
 '-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p','-color_range','tv',
 '-c:a','copy','-movflags','+faststart',mp4]);
 renameSync(mp4,path.join(output,'nexo_demo_motion.mp4'));
 const gif=path.join(temp,'preview.gif');
 run(['-i',path.join(output,'nexo_demo_motion.mp4'),'-filter_complex',
 "[0:v]split=3[a][b][c];[a]trim=start=2:end=4,setpts=PTS-STARTPTS[a1];[b]trim=start=17:end=19,setpts=PTS-STARTPTS[b1];[c]trim=start=36:end=38,setpts=PTS-STARTPTS[c1];[a1][b1][c1]concat=n=3:v=1:a=0,fps=12,scale=640:-1:flags=lanczos,split[g][p];[p]palettegen=max_colors=128:stats_mode=diff[pal];[g][pal]paletteuse=dither=sierra2_4a:diff_mode=rectangle",
 '-loop','0',gif]);
 renameSync(gif,path.join(output,'nexo_demo_preview.gif'));
 console.log('Exported browser-compatible MP4 and animated GIF.');
};
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) exportAssets();
