import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Background, C, FrameChrome, clamp, ease} from './visual';
import {Opening, Pipeline, Closing} from './scenes/Brand';
import {Dashboard} from './scenes/Dashboard';
import {Intelligence} from './scenes/Intelligence';

const Shot:React.FC<{length:number,section:number,children:React.ReactNode}> = ({length,section,children}) => {
 const f=useCurrentFrame();
 const exit=ease(f,length-12,12);
 return <AbsoluteFill style={{opacity:Math.min(clamp((f+1)/9),1-exit),transform:`scale(${1+exit*.08})`}}>
 {children}<FrameChrome section={section}/>
 </AbsoluteFill>;
};
export const NexoFilm = () => <AbsoluteFill style={{fontFamily:'Inter, sans-serif',color:C.white,background:C.dark}}>
 <Background/>
 <Audio src={staticFile('audio.wav')} volume={.75}/>
 <Sequence from={0} durationInFrames={180}><Shot length={180} section={1}><Opening/></Shot></Sequence>
 <Sequence from={180} durationInFrames={210}><Shot length={210} section={2}><Pipeline/></Shot></Sequence>
 <Sequence from={390} durationInFrames={300}><Shot length={300} section={3}><Dashboard/></Shot></Sequence>
 <Sequence from={690} durationInFrames={300}><Shot length={300} section={4}><Intelligence/></Shot></Sequence>
 <Sequence from={990} durationInFrames={210}><Shot length={210} section={5}><Closing/></Shot></Sequence>
 </AbsoluteFill>;
