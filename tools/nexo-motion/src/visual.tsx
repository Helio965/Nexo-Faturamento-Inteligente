import React, {CSSProperties} from 'react';
import {useCurrentFrame, spring, interpolate, Easing} from 'remotion';

export const C = {orange:'#ff5500', coral:'#ff4500', purple:'#a855f7', white:'#f7f7f7', muted:'#a0a0a0', dark:'#0d0d0d'};
export const clamp = (n:number) => Math.max(0,Math.min(1,n));
export const ease = (frame:number, start=0, duration=30) => Easing.bezier(.16,1,.3,1)(clamp((frame-start)/duration));
export const enter = (frame:number, delay=0) => spring({fps:30,frame:Math.max(0,frame-delay),config:{damping:19,stiffness:110,mass:1}});
export const panel:CSSProperties = {background:'linear-gradient(145deg,#242424ed,#111111f5)',border:'1px solid #ffffff24',borderRadius:26,boxShadow:'0 30px 90px #0009',overflow:'hidden'};
export const Label:React.FC<{children:React.ReactNode,color?:string,style?:CSSProperties}> = ({children,color=C.muted,style}) => <div style={{fontSize:20,fontWeight:700,letterSpacing:3,color,...style}}>{children}</div>;
export const Reveal:React.FC<{children:React.ReactNode,delay?:number,style?:CSSProperties}> = ({children,delay=0,style}) => {
 const f=useCurrentFrame(), p=enter(f,delay);
 return <div style={{overflow:'hidden',...style}}><div style={{opacity:clamp((f-delay)/12),transform:`translateY(${(1-p)*110}%)`}}>{children}</div></div>;
};
export const Logo:React.FC<{size?:number,progress?:number}> = ({size=100,progress=1}) => <svg width={size} height={size} viewBox="0 0 200 210" fill="none">
 <defs><linearGradient id="brand" x1="0" y1="0" x2="200" y2="210"><stop stopColor="#d891ff"/><stop offset="1" stopColor="#7c3aed"/></linearGradient></defs>
 <g stroke="url(#brand)" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" pathLength={1} style={{strokeDasharray:550,strokeDashoffset:(1-progress)*550}}>
 <path d="M100 12 185 61 100 111 15 61Z M15 61V153L100 202V111 M100 202 185 153V61"/>
 {[0,1,2,3].map(i=><g key={i}><path d={`M${34+i*17} ${72+i*10}V${145+i*10}l12 7V${94+i*10}`}/><path d={`M${117+i*17} ${101-i*10}V${190-i*10}l12-7V${90-i*10}`}/><path d={`M${32+i*17} ${61-i*10}L100 ${100-i*20}L${168-i*17} ${61-i*10}`}/></g>)}
 </g>
</svg>;
export const Background:React.FC = () => {
 const f=useCurrentFrame();
 return <div style={{position:'absolute',inset:0,background:C.dark,overflow:'hidden'}}>
 <div style={{position:'absolute',inset:0,background:`radial-gradient(ellipse at ${58+8*Math.sin(f/180)}% 70%,#ff450020,transparent 55%),radial-gradient(ellipse at 25% 25%,#a855f712,transparent 50%)`}}/>
 <svg width="1920" height="1080" style={{position:'absolute',opacity:.2}}>
 {Array.from({length:25},(_,i)=><line key={i} x1={960+(i-12)*45} y1={480} x2={960+(i-12)*250} y2={1180} stroke={C.orange} strokeWidth=".9"/>)}
 {Array.from({length:15},(_,i)=>{const y=510+((i*47+f*.8)%700); return <line key={i} x1="0" y1={y} x2="1920" y2={y} stroke={C.orange} strokeWidth=".6"/>;})}
 {Array.from({length:44},(_,i)=>{const x=(i*397+Math.sin(f/90+i)*35)%1920,y=(i*173-f*.6+2400)%1080;return <circle key={i} cx={x} cy={y} r={i%5===0?2.4:1.1} fill={i%4?C.orange:C.purple} opacity={.2+(i%7)/15}/>;})}
 </svg>
 <div style={{position:'absolute',inset:0,background:'radial-gradient(ellipse at center,transparent 30%,#05050590 100%)'}}/>
 </div>;
};
export const FrameChrome:React.FC<{section:number}> = ({section}) => <>
 <div style={{position:'absolute',top:48,left:64,display:'flex',alignItems:'center',gap:14}}><Logo size={44}/><span style={{fontSize:22,fontWeight:800,letterSpacing:2}}>NEXO</span><span style={{height:22,width:1,background:'#ffffff30',margin:'0 12px'}}/><Label style={{fontSize:13}}>FATURAMENTO INTELIGENTE</Label></div>
 <Label style={{position:'absolute',top:64,right:64,fontSize:13,color:'#cccccc'}}>FILME DE PRODUTO / 0{section}</Label>
 <div style={{position:'absolute',bottom:41,left:64,right:64,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
 <Label style={{fontSize:14,color:'#b0b0b0'}}>DADOS ILUSTRATIVOS</Label>
 <div style={{display:'flex',gap:8}}>{[1,2,3,4,5].map(x=><div key={x} style={{width:x===section?60:20,height:3,background:x===section?C.orange:'#ffffff35'}}/>)}</div>
 <Label style={{fontSize:14,color:'#b0b0b0'}}>DADOS. ANÁLISE. DECISÃO.</Label></div>
</>;
