import {spawnSync} from 'node:child_process';
import {statSync,readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.resolve(root,'../../static/video');
const check=(ok,message)=>{if(!ok)throw Error(message);console.log('PASS: '+message);};
const probe=(file)=>{const r=spawnSync('ffprobe',['-v','error','-count_frames','-show_streams','-show_format','-of','json',file],{encoding:'utf8'});if(r.status!==0)throw Error(r.stderr);return JSON.parse(r.stdout);};
const mp4=path.join(dir,'nexo_demo_motion.mp4'),p=probe(mp4);
const v=p.streams.find(s=>s.codec_type==='video'),a=p.streams.find(s=>s.codec_type==='audio');
check(v.codec_name==='h264'&&v.pix_fmt==='yuv420p','H.264/yuv420p');
check(v.width===1920&&v.height===1080&&v.r_frame_rate==='30/1','1920x1080 at 30 fps');
check(Number(v.nb_read_frames)===1200&&Math.abs(Number(p.format.duration)-40)<.1,'1200 frames and 40 seconds');
check(a?.codec_name==='aac','AAC audio');
check(statSync(mp4).size<20*1024*1024,'MP4 below 20 MiB');
const data=readFileSync(mp4);
let offset=0,moov=-1,mdat=-1;
while(offset+8<=data.length){let size=data.readUInt32BE(offset);const name=data.toString('ascii',offset+4,offset+8);if(size===1)size=Number(data.readBigUInt64BE(offset+8));if(name==='moov')moov=offset;if(name==='mdat')mdat=offset;if(!size)break;offset+=size;}
check(moov>=0&&mdat>=0&&moov<mdat,'Faststart moov before mdat');
const d=spawnSync('ffmpeg',['-v','error','-i',mp4,'-f','null','-'],{encoding:'utf8'});
check(d.status===0&&!d.stderr.trim(),'Complete MP4 decoding without errors');
const gif=path.join(dir,'nexo_demo_preview.gif'),g=probe(gif).streams[0];
check(g.codec_name==='gif'&&Number(g.nb_read_frames)>1,'GIF is animated');
check(Math.abs(Number(g.duration)-6)<.2&&g.width===640,'GIF duration approximately 6 seconds and width 640');
check(statSync(gif).size<5*1024*1024,'GIF below 5 MiB');
check(readFileSync(gif).includes(Buffer.from('NETSCAPE2.0')),'GIF loop extension present');
const poster=probe(path.join(dir,'nexo_demo_poster.png')).streams[0];
check(poster.codec_name==='png'&&poster.width===1920&&poster.height===1080,'1080p PNG poster');
