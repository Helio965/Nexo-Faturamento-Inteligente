import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C,Label,Reveal,Logo,panel,ease,enter,clamp} from '../visual';

const Network = () => {
 const f=useCurrentFrame();
 const nodes=Array.from({length:38},(_,i)=>{const a=i*2.39996,r=80+Math.sqrt(i/38)*290; return {x:370+Math.cos(a+f/850)*r,y:365+Math.sin(a+f/850)*r*.85};});
 return <svg width="740" height="730">
 {nodes.map((n,i)=>nodes.slice(i+1).filter((q,j)=>(i+j)%7===0&&Math.hypot(n.x-q.x,n.y-q.y)<300).map((q,j)=><line key={`${i}-${j}`} x1={n.x} y1={n.y} x2={q.x} y2={q.y} stroke={i%3?C.orange:C.purple} strokeWidth="1.3" opacity={.16+.25*Math.pow(Math.sin(f/25+i),2)}/>))}
 {nodes.map((n,i)=><g key={i}><circle cx={n.x} cy={n.y} r={7+2*Math.sin(f/20+i)} fill={i%4?C.orange:C.purple} opacity=".7"/><circle cx={n.x} cy={n.y} r={14+6*Math.sin(f/24+i)} fill="none" stroke={i%4?C.orange:C.purple} opacity=".13"/></g>)}
 <circle cx="370" cy="365" r="90" fill="#141414" stroke="#ff550066"/>
 <circle cx="370" cy="365" r="109" fill="none" stroke={C.orange} strokeDasharray="6 10" transform={`rotate(${f/2} 370 365)`} opacity=".4"/>
 <text x="370" y="381" fill={C.white} textAnchor="middle" fontSize="49" fontWeight="800">IA</text>
 </svg>;
};
export const Intelligence = () => {
 const f=useCurrentFrame(),pdf=ease(f,105,55),support=ease(f,216,26);
 return <>
 <div style={{position:'absolute',left:95,top:133}}>
 <Reveal><Label color={C.orange}>03 / INTELIGÊNCIA E ENTREGA</Label></Reveal>
 <Reveal delay={8}><div style={{fontSize:72,fontWeight:900,lineHeight:1.06,letterSpacing:-3,marginTop:19}}>
 {f<126?<>DADOS QUE ORIENTAM<br/><span style={{color:C.orange}}>DECISÕES.</span></>:f<222?<>RELATÓRIOS<br/><span style={{color:C.orange}}>EXECUTIVOS.</span></>:<>SUPORTE<br/><span style={{color:C.orange}}>CONECTADO.</span></>}
 </div></Reveal>
 </div>
 <div style={{position:'absolute',left:110,top:302,opacity:(1-pdf*.45)*(1-support*.9),transform:`translateX(${-pdf*45}px) scale(${1-pdf*.13})`}}><Network/></div>
 <div style={{...panel,position:'absolute',left:910-pdf*20+support*420,top:353-pdf*12,width:865-pdf*300,height:495+pdf*128,padding:39,transform:`perspective(1600px) rotateY(${-7+pdf*10}deg) translateY(${(1-enter(f,16))*80}px)`,background:pdf>.5?'linear-gradient(145deg,#faf8f5,#e8e5df)':'linear-gradient(145deg,#252525,#121212)',color:pdf>.5?'#171717':C.white}}>
 {pdf<.5?<>
 <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}><Label color={C.orange} style={{fontSize:14}}>DEVOLUTIVA ASSISTIDA POR IA</Label><div style={{width:8,height:8,borderRadius:10,background:C.purple}}/></div>
 <Reveal delay={28} style={{marginTop:38}}><div style={{fontSize:29,fontWeight:700,lineHeight:1.5}}>Identificamos concentração de faturamento nos produtos de maior participação.</div></Reveal>
 <div style={{height:1,background:'#ffffff18',marginTop:26}}/>
 <Reveal delay={57} style={{marginTop:26}}><div style={{fontSize:25,lineHeight:1.5,color:'#b8b8b8'}}>Recomenda-se acompanhar o equilíbrio entre compras e vendas.</div></Reveal>
 <div style={{display:'inline-flex',border:'1px solid #a855f760',color:'#d9b0ff',borderRadius:30,padding:'10px 17px',fontSize:14,marginTop:31}}>Revisão e publicação pelo consultor</div>
 </>:<>
 <div style={{display:'flex',gap:12,alignItems:'center'}}><Logo size={51}/><div><div style={{fontWeight:900,fontSize:22,letterSpacing:2}}>NEXO</div><Label style={{fontSize:9,letterSpacing:1,color:'#777'}}>RELATÓRIO EXECUTIVO</Label></div></div>
 <div style={{height:2,background:C.purple,marginTop:20}}/>
 <div style={{fontSize:24,fontWeight:800,marginTop:20}}>Dados que orientam decisões.</div>
 <Label style={{fontSize:10,letterSpacing:1,marginTop:10}}>EXEMPLO · DADOS ILUSTRATIVOS</Label>
 <div style={{display:'flex',gap:20,marginTop:24}}>{[['VENDAS','R$ 142.800'],['COMPRAS','R$ 96.400']].map(([l,v])=><div key={l} style={{flex:1,padding:15,background:'#ffffff',borderRadius:10,border:'1px solid #ddd'}}><Label style={{fontSize:9,letterSpacing:1}}>{l}</Label><div style={{fontSize:22,fontWeight:800,marginTop:8}}>{v}</div></div>)}</div>
 <div style={{display:'flex',gap:15,height:116,alignItems:'end',borderBottom:'1px solid #ccc',padding:'0 22px',marginTop:19}}>{[18000,21500,24800,23900,26100,28500].map((v,i)=><div key={i} style={{height:v/35000*110*ease(f,138+i*4,28),flex:1,background:i===5?C.orange:C.purple,borderRadius:'5px 5px 0 0'}}/>)}</div>
 <div style={{fontSize:15,fontWeight:800,marginTop:22}}>Resumo e recomendações</div>
 <div style={{fontSize:13,lineHeight:1.6,color:'#555',marginTop:8}}>Acompanhar a concentração de vendas e o equilíbrio entre compras e faturamento.</div>
 <div style={{position:'absolute',bottom:30,left:39,right:39,display:'flex',justifyContent:'space-between',borderTop:'1px solid #ccc',paddingTop:13,fontSize:10,color:'#666'}}><span>REVISADO PELO CONSULTOR</span><span>NEXO / 01</span></div>
 </>}
 </div>
 <div style={{position:'absolute',left:1470,top:425,opacity:ease(f,152,28)*(1-support),transform:`translateX(${(1-enter(f,154))*90}px)`}}>
 <div style={{background:C.orange,color:'#fff',borderRadius:17,padding:'24px 30px',boxShadow:'0 20px 60px #ff550025'}}><Label color="#fff" style={{fontSize:15,letterSpacing:2}}>↓ EXPORTAR PDF</Label><div style={{fontSize:13,marginTop:8,opacity:.8}}>Análise publicada</div></div>
 </div>
 <div style={{position:'absolute',left:100,top:786,opacity:support,transform:`translateY(${(1-enter(f,216))*60}px)`,display:'flex',gap:20}}>
 {[
 ['◉','NOTIFICAÇÕES','Comunicação em tempo real'],
 ['↗','CENTRAL DE TICKETS','Atendimento organizado'],
 ['✦','NEXOBOT','Assistente de suporte'],
 ].map(([icon,title,desc],i)=><div key={title} style={{...panel,width:340,padding:'23px 20px',display:'flex',alignItems:'center',gap:16,transform:`translateY(${(1-enter(f,216+i*6))*40}px)`}}><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke={i===2?C.purple:C.orange} strokeWidth="1.6" style={{flexShrink:0}}>{i===0?<><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z"/><path d="M10 20h4"/></>:i===1?<><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9h10M7 13h7M7 17h4"/></>:<><rect x="3" y="6" width="18" height="15" rx="5"/><path d="M12 2v4M8 12h1M15 12h1M8 16h8"/></>}</svg><div><Label color={C.white} style={{fontSize:13,letterSpacing:1}}>{title}</Label><div style={{fontSize:14,color:C.muted,marginTop:8}}>{desc}</div></div></div>)}
 </div>
 <div style={{position:'absolute',left:98,bottom:127,color:'#bcbcbc',fontSize:20,opacity:1-support}}>{f<126?'Devolutiva assistida por IA, sujeita à revisão do consultor.':'Informações organizadas para apoiar decisões.'}</div>
 </>;
};
