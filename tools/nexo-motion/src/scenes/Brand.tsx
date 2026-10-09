import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, Logo, Label, Reveal, panel, ease, enter, clamp} from '../visual';

export const Opening = () => {
 const f=useCurrentFrame(),p=enter(f,12);
 return <>
 <svg width="1920" height="1080" style={{position:'absolute'}}>
 {Array.from({length:68},(_,i)=>{const a=i*2.39996, r=420+170*Math.sin(i*31), q=1-ease(f,0,100),x=960+Math.cos(a)*r*q,y=355+Math.sin(a)*r*q;return <circle key={i} cx={x} cy={y} r={2+(i%3)} fill={i%3?C.orange:C.purple} opacity={(1-ease(f,88,25))*.75}/>;})}
 </svg>
 <div style={{position:'absolute',top:178,left:0,width:'100%',textAlign:'center',transform:`translateY(${(1-p)*50}px) scale(${.8+p*.2})`}}>
 <div style={{filter:'drop-shadow(0 0 25px #a855f730)'}}><Logo size={170} progress={ease(f,8,65)}/></div>
 <Reveal delay={12} style={{marginTop:10}}><div style={{fontSize:224,fontWeight:900,letterSpacing:-15,lineHeight:1}}>NEXO<span style={{color:C.orange}}>.</span></div></Reveal>
 <Reveal delay={48} style={{marginTop:24}}><div style={{fontSize:40,fontWeight:800,letterSpacing:7}}>FATURAMENTO <span style={{color:C.orange}}>INTELIGENTE</span></div></Reveal>
 <Reveal delay={74} style={{marginTop:40}}><div style={{fontSize:29,color:'#bdbdbd',letterSpacing:.5}}>Transforme dados em decisões.</div></Reveal>
 </div>
 <div style={{position:'absolute',left:400,right:400,bottom:154,height:1,background:'linear-gradient(90deg,transparent,#ff5500,transparent)',transform:`scaleX(${ease(f,55,40)})`}}/>
 </>;
};
const Sheet:React.FC<{name:string,top:number,left:number,delay:number}> = ({name,top,left,delay}) => {
 const f=useCurrentFrame(),p=enter(f,delay), sink=ease(f,80+delay,95);
 return <div style={{...panel,position:'absolute',width:325,height:225,left:left+sink*(790-left),top:top+Math.sin(f/28+delay)*8+sink*(450-top),padding:25,opacity:clamp((f-delay)/12)*(1-sink*.85),transform:`perspective(1000px) rotateY(${-12+sink*35}deg) rotateZ(${-4+sink*12}deg) scale(${p*(1-sink*.7)})`}}>
 <div style={{display:'flex',alignItems:'center',gap:12}}><span style={{color:C.orange,fontSize:27}}>▤</span><Label style={{fontSize:15,letterSpacing:1}} color={C.white}>{name}</Label></div>
 <div style={{marginTop:18,display:'grid',gridTemplateColumns:'2fr 1fr 1fr',gap:8}}>{Array.from({length:12},(_,i)=><div key={i} style={{height:12,borderRadius:3,background:i<3?'#ff550080':'#ffffff17',width:i%3===0?'100%':'85%'}}/>)}</div>
 <div style={{fontSize:12,letterSpacing:2,color:'#777',marginTop:17}}>RELATÓRIO COMERCIAL</div>
 </div>;
};
export const Pipeline = () => {
 const f=useCurrentFrame(),second=f>90;
 return <>
 <div style={{position:'absolute',left:94,top:135}}>
 <Reveal><Label color={C.orange}>01 / PROCESSAMENTO ETL</Label></Reveal>
 <Reveal delay={8}><div style={{fontSize:75,fontWeight:900,lineHeight:1.04,letterSpacing:-3,marginTop:22}}>{second?'INTELIGÊNCIA':'DADOS BRUTOS.'}<br/>{second?<span style={{color:C.orange}}>GERENCIAL.</span>:<span style={{color:'#575757'}}>NOVAS POSSIBILIDADES.</span>}</div></Reveal>
 </div>
 <Sheet name="VENDAS.CSV" top={426} left={115} delay={5}/><Sheet name="COMPRAS.XLSX" top={610} left={285} delay={18}/>
 <svg style={{position:'absolute',inset:0}} width="1920" height="1080">
 <defs><linearGradient id="flow"><stop stopColor="#ff550010"/><stop offset=".5" stopColor="#ff5500"/><stop offset="1" stopColor="#a855f7"/></linearGradient></defs>
 {[0,1,2].map(i=><path key={i} d={`M440 ${510+i*65} C700 ${510+i*65},720 590,990 590 S1220 ${530+i*65},1430 ${530+i*65}`} fill="none" stroke="url(#flow)" strokeWidth="2" strokeDasharray="10 12" strokeDashoffset={-f*5} opacity={ease(f,25,25)}/>)}
 </svg>
 <div style={{position:'absolute',left:715,top:340,width:545,height:545,transform:`perspective(900px) rotateX(16deg) scale(${.9+ease(f,15,50)*.1})`}}>
 <svg width="545" height="545" viewBox="-272 -272 544 544">
 {[190,225,255].map((r,i)=><circle key={r} r={r} fill="none" stroke={i===1?C.purple:C.orange} strokeWidth={i===1?1:2} strokeDasharray={i===1?'3 10':'230 60 15 80'} transform={`rotate(${f*(i%2?-1:1)*(i+1)*.32})`} opacity={.25+i*.15}/>)}
 {Array.from({length:16},(_,i)=><line key={i} x1={Math.cos(i*Math.PI/8)*245} y1={Math.sin(i*Math.PI/8)*245} x2={Math.cos(i*Math.PI/8)*253} y2={Math.sin(i*Math.PI/8)*253} stroke={C.orange}/>)}
 <circle r="137" fill="#17100dee" stroke="#ff550050" strokeWidth="1"/>
 <circle r={120+Math.sin(f/10)*3} fill="none" stroke={C.orange} opacity=".2"/>
 </svg>
 <div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',flexDirection:'column'}}>
 <Logo size={115}/><div style={{fontSize:28,fontWeight:900,letterSpacing:7,marginTop:16}}>ETL</div><div style={{fontSize:13,color:C.muted,letterSpacing:2,marginTop:10}}>DADOS DO PDV</div>
 </div>
 </div>
 <div style={{...panel,position:'absolute',left:1395,top:443,width:397,height:287,padding:29,transform:`translateY(${(1-enter(f,90))*100}px) rotateY(-8deg)`,opacity:clamp((f-85)/25)}}>
 <Label style={{fontSize:16,letterSpacing:1}} color={C.orange}>INDICADORES CONSOLIDADOS</Label>
 <div style={{height:133,display:'flex',gap:15,alignItems:'end',marginTop:29}}>{[.36,.55,.46,.73,.92,.82].map((v,i)=><div key={i} style={{width:38,height:130*v*ease(f,100+i*7,50),background:i===4?C.orange:'#a855f790',borderRadius:'6px 6px 0 0'}}/>)}</div>
 <div style={{fontSize:16,color:C.muted,marginTop:20}}>Organização que revela padrões.</div>
 </div>
 <div style={{position:'absolute',left:95,bottom:126}}><div style={{fontSize:24,color:'#cccccc'}}>Importação, organização e processamento de dados.</div><div style={{fontSize:18,color:C.orange,marginTop:13}}>Processamento acionado pelo administrador.</div></div>
 </>;
};
export const Closing = () => {
 const f=useCurrentFrame();
 return <>
 <div style={{position:'absolute',inset:'155px 280px 125px',border:'1px solid #ff550025',borderRadius:40,transform:`scale(${1.08-ease(f,0,150)*.08})`}}/>
 <svg width="1920" height="1080" style={{position:'absolute'}}>{Array.from({length:46},(_,i)=>{const a=i*2.39996,r=(1-ease(f,0,70))*600+200;return <circle key={i} cx={960+Math.cos(a)*r} cy={335+Math.sin(a)*r*.7} r="2" fill={i%3?C.orange:C.purple} opacity={(1-ease(f,70,20))*.6}/>;})}</svg>
 <div style={{position:'absolute',top:204,width:'100%',textAlign:'center',transform:`scale(${1.03-ease(f,0,180)*.03})`}}>
 <Reveal delay={5}><Logo size={164}/></Reveal>
 <Reveal delay={12}><div style={{fontWeight:900,fontSize:180,letterSpacing:-12,lineHeight:1.05,marginTop:4}}>NEXO<span style={{color:C.orange}}>.</span></div></Reveal>
 <Reveal delay={25}><div style={{fontSize:34,fontWeight:800,letterSpacing:6,marginTop:17}}>FATURAMENTO INTELIGENTE</div></Reveal>
 <Reveal delay={42}><div style={{fontSize:29,color:'#c6c6c6',marginTop:50}}>Automação e Inteligência para a sua Empresa.</div></Reveal>
 <Reveal delay={59}><div style={{color:C.orange,fontWeight:700,fontSize:23,letterSpacing:8,marginTop:30}}>DADOS. ANÁLISE. DECISÃO.</div></Reveal>
 </div>
 </>;
};
