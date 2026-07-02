import json
data=json.load(open("/tmp/cosmo_data.json"))
HEAD="""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>The Matlala network — live</title><style>
:root{--bg:#0b0f18;--ink:#e9eef7;--mut:#8a96ad}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;overflow:hidden}
canvas{display:block}.panel{position:absolute;background:rgba(12,18,30,.9);backdrop-filter:blur(8px);
border:1px solid rgba(255,255,255,.09);border-radius:12px}
#head{top:14px;left:14px;max-width:430px;padding:14px 16px}#head h1{margin:0 0 5px;font-size:16px}
#head p{margin:0;font-size:12px;line-height:1.5;color:var(--mut)}#head b{color:var(--ink)}
#legend{bottom:14px;left:14px;padding:10px 13px;font-size:11.5px;color:var(--mut)}
#legend .r{display:flex;align-items:center;gap:8px;margin:3px 0}.dot{width:11px;height:11px;border-radius:50%}
.sq{width:11px;height:11px;border-radius:2px}
#tip{position:absolute;pointer-events:none;padding:7px 10px;font-size:12px;background:rgba(6,10,18,.96);
border:1px solid rgba(255,255,255,.15);border-radius:8px;display:none;max-width:240px;z-index:9}#tip b{color:#fff}
#tip .m{color:var(--mut);font-size:11px}
#ev{top:14px;right:14px;width:320px;max-height:calc(100% - 28px);overflow:auto;padding:14px 15px;display:none}
#ev h2{margin:0 0 4px;font-size:15px;color:#ffcf4a}#ev .sub{color:var(--mut);font-size:11.5px;margin-bottom:9px}
#ev .note{font-size:12.5px;line-height:1.5;border-left:2px solid rgba(255,207,74,.5);padding:4px 0 4px 10px;color:#dfe6f2}
#ev .close{float:right;cursor:pointer;color:var(--mut)}
#foot{position:absolute;bottom:14px;right:16px;font-size:11px;color:#5e6b82;text-align:right}
</style></head><body><canvas id=c></canvas>
<div id=head class=panel><h1>The web around Cat Matlala — <span id=nn></span> figures</h1>
<p>Madlanga Commission · drawn from <b>49,068 sworn claims</b> across 106 hearing days. Node size = how
often named; lines = how many claims name both; gold = Matlala &amp; his companies. <b>Colour is the
speaker's role</b> — grey advocates are always in the room; the story is who else clusters with him.
<b>Click a node</b> for detail.</p></div>
<div id=legend class=panel></div><div id=tip></div><div id=ev class=panel></div>
<div id=foot>Allegation in the public record, attributed to named speakers — not a finding of fact.<br>
Drag to pan · scroll to zoom · hover · click. Commission Transcript Intelligence · DRAFT</div>
<script>const G="""
JS=r"""
;
const COL={subject:'#ffcf4a',company:'#ffcf4a',witness:'#46c7a8',counsel:'#5b6b86',bench:'#34507f',political:'#ff5ad0',org:'#7fa8cc'};
const LABELS={subject:'Cat Matlala',company:"Matlala's companies",witness:'Witnesses / officials',political:'Police Minister',counsel:'Counsel (always present)',bench:'The bench',org:'Organisations'};
const MAT=G.MAT, N=G.nodes, L=G.links, byId={};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip'),evp=document.getElementById('ev');
document.getElementById('nn').textContent=N.length;
let W,H,DPR;function size(){DPR=Math.min(2,devicePixelRatio||1);W=innerWidth;H=innerHeight;cv.width=W*DPR;cv.height=H*DPR;cv.style.width=W+'px';cv.style.height=H+'px';ctx.setTransform(DPR,0,0,DPR,0,0);}size();addEventListener('resize',size);
N.forEach(n=>{n.x=W/2+(Math.random()-.5)*420;n.y=H/2+(Math.random()-.5)*420;n.vx=0;n.vy=0;
 n.r=Math.max(7,Math.min(40, n.id===MAT?40:5+Math.sqrt(n.ment)*1.5)); byId[n.id]=n;});
L.forEach(l=>{l.s=byId[l.s];l.t=byId[l.t];});
const maxW=Math.max.apply(null,L.map(l=>l.w));
let scale=1,ox=0,oy=0,alpha=1,tScale=1,tOx=0,tOy=0,easing=false;
const stars=Array.from({length:110},()=>({x:Math.random(),y:Math.random(),r:Math.random()*1.1,a:Math.random()*.4+.12}));
function clamp(v,m){return v>m?m:v<-m?-m:v;}
function step(){ if(alpha<0.004)return;
 for(let a=0;a<N.length;a++){const p=N[a]; p.vx+=(W/2-p.x)*0.0016*alpha; p.vy+=(H/2-p.y)*0.0016*alpha;
  for(let b=a+1;b<N.length;b++){const q=N[b];let dx=p.x-q.x,dy=p.y-q.y,d2=dx*dx+dy*dy+1;
   if(d2<160000){let f=Math.min(1.1,4200/d2)*alpha;let ux=dx/Math.sqrt(d2),uy=dy/Math.sqrt(d2);
   p.vx+=ux*f*26;p.vy+=uy*f*26;q.vx-=ux*f*26;q.vy-=uy*f*26;}}}
 for(const l of L){let dx=l.t.x-l.s.x,dy=l.t.y-l.s.y,d=Math.sqrt(dx*dx+dy*dy)||1,rest=70+120*(1-l.w/maxW);
  let f=(d-rest)*0.011*alpha*Math.min(2.2,Math.log1p(l.w));let ux=dx/d*f,uy=dy/d*f;
  l.s.vx+=ux;l.s.vy+=uy;l.t.vx-=ux;l.t.vy-=uy;}
 for(const p of N){p.vx=clamp(p.vx*0.84,8);p.vy=clamp(p.vy*0.84,8);p.x+=p.vx;p.y+=p.vy;} alpha*=0.986; }
let hot=null;
function draw(){ ctx.clearRect(0,0,W,H);
 for(const s of stars){ctx.globalAlpha=s.a;ctx.fillStyle='#9fb4d8';ctx.beginPath();ctx.arc(s.x*W,s.y*H,s.r,0,7);ctx.fill();}
 ctx.globalAlpha=1;ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);
 for(const l of L){const gold=l.s.id===MAT||l.t.id===MAT; const hl=hot&&(l.s===hot||l.t===hot);
  ctx.strokeStyle=gold?'rgba(255,207,74,'+(0.12+0.4*l.w/maxW)+')':(hl?'rgba(150,200,230,.5)':'rgba(140,165,200,.08)');
  ctx.lineWidth=Math.max(0.5,(gold?1.3:0.6)*Math.sqrt(l.w/3));
  ctx.beginPath();ctx.moveTo(l.s.x,l.s.y);ctx.lineTo(l.t.x,l.t.y);ctx.stroke();}
 for(const n of N){const c=COL[n.role]||'#8aa';const big=n.id===MAT;const sq=n.type==='org';
  ctx.shadowColor=(big||n.role==='political')?c:'transparent';ctx.shadowBlur=big?26:(n===hot?16:0);
  ctx.fillStyle=c;
  if(sq){ctx.fillRect(n.x-n.r,n.y-n.r,n.r*2,n.r*2);} else {ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,7);ctx.fill();}
  ctx.shadowBlur=0;
  if(big){const t=(Date.now()%2200)/2200;ctx.strokeStyle='rgba(255,207,74,'+(0.7-0.55*t)+')';ctx.lineWidth=2;
   ctx.beginPath();ctx.arc(n.x,n.y,n.r+7+t*13,0,7);ctx.stroke();}
  if(n.r>13||big||n===hot){ctx.fillStyle=big?'#fff':'#cdd7e8';ctx.font=(big?'700 ':'600 ')+Math.max(11,n.r*0.7)+'px -apple-system,sans-serif';
   ctx.textAlign='center';ctx.fillText(n.name,n.x,n.y-n.r-6);}}
 ctx.restore(); }
function loop(){step();
 if(easing){scale+=(tScale-scale)*0.1;ox+=(tOx-ox)*0.1;oy+=(tOy-oy)*0.1;
  if(Math.abs(tScale-scale)<.001){scale=tScale;ox=tOx;oy=tOy;easing=false;}}
 draw();requestAnimationFrame(loop);}loop();
function fit(){let mnx=1e9,mny=1e9,mxx=-1e9,mxy=-1e9;for(const n of N){mnx=Math.min(mnx,n.x-n.r-40);mxx=Math.max(mxx,n.x+n.r+40);mny=Math.min(mny,n.y-n.r-30);mxy=Math.max(mxy,n.y+n.r+30);}
 const bw=mxx-mnx,bh=mxy-mny;tScale=Math.min((W-360)/bw,(H-120)/bh,1.5);tOx=(W-360)/2+40-((mnx+mxx)/2)*tScale;tOy=H/2-((mny+mxy)/2)*tScale;easing=true;}
setTimeout(fit,3600);
function toW(mx,my){return[(mx-ox)/scale,(my-oy)/scale];}
function pick(mx,my){const[x,y]=toW(mx,my);let best=null,bd=1e9;for(const n of N){const d=(n.x-x)**2+(n.y-y)**2;if(d<Math.max(200,(n.r+8)**2)&&d<bd){bd=d;best=n;}}return best;}
let drag=false,moved=false,lx,ly;
cv.addEventListener('mousedown',e=>{drag=true;moved=false;easing=false;lx=e.clientX;ly=e.clientY;});
addEventListener('mouseup',e=>{if(drag&&!moved){const n=pick(e.clientX,e.clientY);if(n)showEv(n);}drag=false;});
addEventListener('mousemove',e=>{ if(drag){const dx=e.clientX-lx,dy=e.clientY-ly;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;ox+=dx;oy+=dy;lx=e.clientX;ly=e.clientY;tip.style.display='none';return;}
 const n=pick(e.clientX,e.clientY);hot=n;
 if(n){tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+12)+'px';
  tip.innerHTML='<b>'+n.name+'</b><br><span class=m>'+(LABELS[n.role]||n.role)+' · '+n.ment+' mentions'+(n.w?' · '+n.w+' claims with Matlala':'')+'</span>';
  cv.style.cursor='pointer';}else{tip.style.display='none';cv.style.cursor='default';}});
cv.addEventListener('wheel',e=>{e.preventDefault();easing=false;const f=e.deltaY<0?1.1:0.9;ox=e.clientX-(e.clientX-ox)*f;oy=e.clientY-(e.clientY-oy)*f;scale*=f;},{passive:false});
function showEv(n){evp.style.display='block';
 let h='<span class=close onclick="document.getElementById(\'ev\').style.display=\'none\'">✕</span><h2>'+n.name+'</h2>';
 h+='<div class=sub>'+(LABELS[n.role]||n.role)+' · '+n.ment+' mentions'+(n.w?' · '+n.w+' claims naming both Matlala &amp; them':'')+'</div>';
 if(n.note)h+='<div class=note>'+n.note+'</div>';
 else h+='<div class=note>Named alongside Matlala in '+(n.w||0)+' sworn claims across the corpus. Co-mention is association in the testimony — not proof of a relationship.</div>';
 h+='<div class=sub style="margin-top:10px;color:#5e6b82">Allegation in the public record, attributed to the named speaker. Not a finding of fact.</div>';
 evp.innerHTML=h;}
// legend
const order=['subject','company','witness','political','org','counsel','bench'];
document.getElementById('legend').innerHTML=order.map(k=>'<div class=r><span class="'+(k==='company'||k==='org'?'sq':'dot')+'" style="background:'+COL[k]+'"></span>'+LABELS[k]+'</div>').join('');
setTimeout(()=>{const m=byId[MAT];if(m)showEv(m);},4000);
</script></body></html>"""
html=HEAD+json.dumps({"nodes":data["nodes"],"links":data["links"],"MAT":data["MAT"]})+JS
open("linkedin/matlala_live_cosmograph.html","w").write(html)
print("wrote linkedin/matlala_live_cosmograph.html", len(html),"bytes")
