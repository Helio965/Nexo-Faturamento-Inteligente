import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, Label, Reveal, panel, enter, ease, clamp} from '../visual';

const money=(n:number)=>Math.round(n).toLocaleString('pt-BR');
const revenues=[18000,21500,24800,23900,26100,28500]; // sum 142800
const purchases=[14000,15200,16000,17000,16500,17700]; // sum 96400
const Card:React.FC<{label:string,value:number,index:number,unit?:string,caption:string}> = ({label,value,index,unit='R$ ',caption}) => {
 const f=useCurrentFrame(),p=enter(f,15+index*9),q=ease(f,25+index*10,70);
 return <div style={{...panel,padding:'25px 28px',height:157,flex:1,transform:`translateY(${(1-p)*90}px)`,opacity:clamp((f-index*9)/14)}}>
 <Label style={{fontSize:13,letterSpacing:1.2}}>{label}</Label>
 <div style={{fontWeight:800,fontSize:index===2?44:47,letterSpacing:-2,marginTop:13,color:index===2?C.orange:C.white}}>{value<0?'−':''}{unit}{money(Math.abs(value)*q)}</div>
 <div style={{fontSize:13,color:'#999',marginTop:7}}>{caption}</div>
 </div>;
};
export const Dashboard = () => {
 const f=useCurrentFrame(),p=enter(f,4),pan=Math.sin(f/100)*7;
 const word=f<85?'VISUALIZE.':f<155?'COMPARE.':'DECIDA.';
 const points=revenues.map((v,i)=>`${68+i*101},${260-v/120}`).join(' ');
 return <>
 <div style={{position:'absolute',left:98,top:137}}>
 <Reveal><Label color={C.orange}>02 / DASHBOARDS E INDICADORES</Label></Reveal>
 <div style={{fontSize:88,fontWeight:900,letterSpacing:-4,marginTop:17,color:f>=155?C.orange:C.white}}>{word}</div>
 </div>
 <div style={{position:'absolute',right:98,top:182,fontSize:22,color:'#b3b3b3',textAlign:'right',lineHeight:1.5}}>Indicadores estratégicos<br/>em uma única plataforma.</div>
 <div style={{...panel,position:'absolute',left:116,top:325,width:1688,height:613,padding:28,transform:`perspective(2500px) rotateX(${3-ease(f,50,150)*2}deg) rotateY(${-3+ease(f,80,170)*4}deg) translateY(${(1-p)*120}px) translateX(${pan}px)`,background:'linear-gradient(140deg,#202020f5,#101010f7)'}}>
 <div style={{display:'flex',justifyContent:'space-between',height:34,alignItems:'center'}}><Label style={{fontSize:14,letterSpacing:2}} color={C.white}>NEXO / VISÃO GERENCIAL</Label><div style={{fontSize:13,color:C.muted}}>EXEMPLO CONSOLIDADO · JAN — JUN 2026</div></div>
 <div style={{display:'flex',gap:18,marginTop:18}}>
 <Card index={0} label="FATURAMENTO TOTAL" value={142800} caption="Soma das vendas do período"/>
 <Card index={1} label="COMPRAS NO PERÍODO" value={96400} caption="Soma dos relatórios de compras"/>
 <Card index={2} label="PRESSÃO DE ESTOQUE" value={-46400} caption="Compras − faturamento · saldo estimado"/>
 <Card index={3} label="PRODUTOS ANALISADOS" value={248} unit="" caption="Base ilustrativa consolidada"/>
 </div>
 <div style={{display:'flex',gap:18,marginTop:18}}>
 <div style={{...panel,width:800,height:317,padding:24,transform:`translateY(${(1-enter(f,55))*65}px)`}}>
 <Label style={{fontSize:14,letterSpacing:1}}>COMPRAS × VENDAS</Label>
 <svg width="750" height="234" viewBox="0 0 750 234">
 {[45,90,135,180].map(y=><line key={y} x1="40" x2="714" y1={y} y2={y} stroke="#ffffff0e"/>)}
 {revenues.map((v,i)=><g key={i}>
 <rect x={65+i*106} y={192-v/180*ease(f,55+i*5,50)} width="24" height={v/180*ease(f,55+i*5,50)} rx="4" fill={C.orange}/>
 <rect x={95+i*106} y={192-purchases[i]/180*ease(f,62+i*5,50)} width="24" height={purchases[i]/180*ease(f,62+i*5,50)} rx="4" fill={C.purple}/>
 <text x={91+i*106} y="222" textAnchor="middle" fill="#929292" fontSize="12">{['JAN','FEV','MAR','ABR','MAI','JUN'][i]}</text>
 </g>)}
 </svg>
 <div style={{display:'flex',gap:24,fontSize:12,color:C.muted,marginTop:-4}}><span style={{color:C.orange}}>● Vendas · R$ 142.800</span><span style={{color:C.purple}}>● Compras · R$ 96.400</span></div>
 </div>
 <div style={{...panel,width:470,height:317,padding:24,transform:`translateY(${(1-enter(f,68))*65}px)`}}>
 <Label style={{fontSize:14,letterSpacing:1}}>HISTÓRICO PUBLICADO</Label>
 <svg width="425" height="229" viewBox="0 0 660 330">
 {[80,140,200,260].map(y=><line key={y} x1="40" x2="620" y1={y} y2={y} stroke="#ffffff10"/>)}
 <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#ff550055"/><stop offset="1" stopColor="#ff550000"/></linearGradient></defs>
 <polygon points={`68,290 ${points} 573,290`} fill="url(#area)" opacity={ease(f,80,50)}/>
 <polyline points={points} pathLength="1" fill="none" stroke={C.orange} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1" strokeDashoffset={1-ease(f,78,65)}/>
 {revenues.map((v,i)=><circle key={i} cx={68+i*101} cy={260-v/120} r={5*ease(f,90+i*9,25)} fill={C.white}/>)}
 </svg>
 <div style={{fontSize:12,color:C.muted,marginTop:-3}}>Comparação entre análises publicadas.</div>
 </div>
 <div style={{...panel,flex:1,height:317,padding:24,transform:`translateY(${(1-enter(f,82))*65}px)`}}>
 <Label style={{fontSize:14,letterSpacing:1}}>CURVA ABC</Label>
 <div style={{position:'relative',width:174,height:174,margin:'18px auto'}}>
 <svg width="174" height="174" viewBox="0 0 174 174" style={{transform:'rotate(-90deg)'}}>
 <circle cx="87" cy="87" r="67" stroke="#ffffff10" strokeWidth="17" fill="none"/>
 <circle cx="87" cy="87" r="67" stroke={C.orange} strokeWidth="17" fill="none" pathLength="100" strokeDasharray={`${77*ease(f,94,65)} 100`}/>
 <circle cx="87" cy="87" r="67" stroke={C.purple} strokeWidth="17" fill="none" pathLength="100" strokeDasharray={`${16*ease(f,94,65)} 100`} strokeDashoffset="-77"/>
 </svg>
 <div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',flexDirection:'column'}}><strong style={{fontSize:39}}>{Math.round(77*ease(f,94,65))}%</strong><span style={{fontSize:12,color:C.muted}}>CLASSE A</span></div>
 </div>
 <div style={{fontSize:12,color:C.muted,textAlign:'center'}}>A 77% · B 16% · C 7%</div>
 <div style={{fontSize:11,color:'#777',textAlign:'center',marginTop:6}}>Participação no faturamento</div>
 </div>
 </div>
 </div>
 </>;
};
