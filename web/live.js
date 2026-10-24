const $=id=>document.getElementById(id),post=(p,b={})=>fetch(p,{method:'POST',body:JSON.stringify(b)}).then(r=>r.json());
const fmt=x=>x>=1000?(x/1000).toFixed(2)+'s':Math.round(x)+'ms',DETECT=15,NS='http://www.w3.org/2000/svg';
const COLORS=['#1B69FF','#8D2DD8','#7aa5ff','#c79bff','#4fd1c5'],ROOT='#F45031';
let data=null,metric='p99',populated=false,detectedAt=null,chartModel=null;
const set=(h,em)=>{$('h-main').innerHTML=h+(em?` <em>${em}</em>`:'')};

/* ---------- time-series chart ---------- */
function buildChart(d){
 const L=d.live,rank=d.ranking||[],top=rank[0],incident=top&&top.score>=DETECT,keys=Object.keys(d.series||{});
 if(!keys.length)return null;
 const last=k=>d.series[k][d.series[k].length-1]||{p99:0},
  order=keys.sort((a,b)=>last(b).p99-last(a).p99),show=order.slice(0,5);
 if(incident&&!show.includes(top.edge))show.push(top.edge);
 const lines=show.map((k,i)=>({k,color:incident&&k===top.edge?ROOT:COLORS[i%COLORS.length],root:incident&&k===top.edge,pts:d.series[k]}));
 const all=lines.flatMap(l=>l.pts),t0=Math.min(...all.map(p=>p.t)),t1=Math.max(...all.map(p=>p.t),t0+10);
 return{lines,t0,t1,injected:L.injected?L.injected.at_s:null,detected:detectedAt,root:incident?top.edge:null};
}
function draw(){
 const svg=$('plot'),m=chartModel;svg.innerHTML='';if(!m){$('legend').innerHTML='<span>Start the cluster to see edges appear here.</span>';return}
 const W=900,H=300,pad={l:46,r:12,t:12,b:24},iw=W-pad.l-pad.r,ih=H-pad.t-pad.b,err=metric==='err';
 const val=p=>err?p.err*100:p.p99,vmax=Math.max(...m.lines.flatMap(l=>l.pts.map(val)),err?5:100);
 const lo=err?0:Math.log10(5),hi=err?Math.ceil(vmax/10)*10||10:Math.log10(vmax*1.15);
 const X=t=>pad.l+(t-m.t0)/(m.t1-m.t0)*iw,Y=v=>pad.t+ih-((err?v:Math.log10(Math.max(v,5)))-lo)/(hi-lo)*ih;
 const el=(n,a,t)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);if(t)e.textContent=t;svg.appendChild(e);return e};
 const ticks=err?[0,.25,.5,.75,1].map(f=>f*hi):[10,25,50,100,250,500,1000,2500].filter(v=>Math.log10(v)>=lo&&Math.log10(v)<=hi);
 ticks.forEach(v=>{el('line',{x1:pad.l,x2:W-pad.r,y1:Y(v),y2:Y(v),stroke:'#ffffff1c','stroke-dasharray':'3 5'});el('text',{x:pad.l-8,y:Y(v)+3,'text-anchor':'end',fill:'#ffffff80','font-size':10},err?v.toFixed(0)+'%':fmt(v))});
 const step=Math.max(10,Math.ceil((m.t1-m.t0)/6/10)*10);for(let t=Math.ceil(m.t0/step)*step;t<=m.t1;t+=step)el('text',{x:X(t),y:H-6,'text-anchor':'middle',fill:'#ffffff80','font-size':10},t+'s');
 const mark=(t,color,label,row,end)=>{if(t==null||t<m.t0||t>m.t1)return;el('line',{x1:X(t),x2:X(t),y1:pad.t,y2:pad.t+ih,stroke:color,'stroke-dasharray':'4 4'});el('text',{x:X(t)+(end?-5:5),y:pad.t+10+row*12,'text-anchor':end?'end':'start',fill:color,'font-size':10},label)};
 mark(m.injected,ROOT,'fault injected',0);mark(m.detected,'#7aa5ff','diagnosed',1,true);
 m.lines.slice().sort((a,b)=>a.root-b.root).forEach(l=>{const d=l.pts.map((p,i)=>`${i?'L':'M'}${X(p.t).toFixed(1)},${Y(val(p)).toFixed(1)}`).join(' ');
  el('path',{d:d+` L${X(l.pts[l.pts.length-1].t)},${pad.t+ih} L${X(l.pts[0].t)},${pad.t+ih}Z`,fill:l.color,opacity:l.root?.14:.04});
  el('path',{d,fill:'none',stroke:l.color,'stroke-width':l.root?2.4:1.5,'stroke-linejoin':'round',opacity:l.root||!m.root?1:.75})});
 m.cursor=el('line',{x1:0,x2:0,y1:pad.t,y2:pad.t+ih,stroke:'#fff','stroke-opacity':.4,visibility:'hidden'});m.X=X;m.Y=Y;m.val=val;m.pad=pad;m.W=W;
 $('legend').innerHTML=m.lines.map(l=>`<span><i style="background:${l.color}"></i>${l.k.replace('->',' → ')}${l.root?' (suspected root)':''}</span>`).join('');
}
$('chart').addEventListener('mousemove',e=>{const m=chartModel;if(!m||!m.X)return;const r=$('plot').getBoundingClientRect(),x=(e.clientX-r.left)/r.width*m.W,t=m.t0+(x-m.pad.l)/(m.W-m.pad.l-m.pad.r)*(m.t1-m.t0);
 if(t<m.t0||t>m.t1){hideTip();return}
 const rows=m.lines.map(l=>{let b=l.pts[0];l.pts.forEach(p=>{if(Math.abs(p.t-t)<Math.abs(b.t-t))b=p});return{l,b}}),tt=rows[0].b.t;
 m.cursor.setAttribute('x1',m.X(tt));m.cursor.setAttribute('x2',m.X(tt));m.cursor.setAttribute('visibility','visible');
 const tip=$('tip');tip.style.display='block';tip.innerHTML=`<div style="color:#ffffff80">t = ${tt.toFixed(0)}s</div>`+rows.map(({l,b})=>`<div><i style="background:${l.color}"></i>${l.k.replace('->','→')} <b style="font-weight:400;margin-left:auto;padding-left:12px">${metric==='err'?(b.err*100).toFixed(1)+'%':fmt(b.p99)}</b></div>`).join('');
 const cx=e.clientX-$('chart').getBoundingClientRect().left;tip.style.left=Math.min(cx+14,$('chart').clientWidth-tip.offsetWidth-4)+'px';tip.style.top='8px'});
$('chart').addEventListener('mouseleave',hideTip);function hideTip(){$('tip').style.display='none';if(chartModel&&chartModel.cursor)chartModel.cursor.setAttribute('visibility','hidden')}
$('metric').onclick=e=>{const b=e.target.closest('button');if(!b)return;metric=b.dataset.m;document.querySelectorAll('#metric button').forEach(x=>x.classList.toggle('on',x===b));draw()};

/* ---------- panels ---------- */
function populate(h){if(populated)return;populated=true;$('svc').innerHTML=Object.keys(h).filter(n=>n!=='frontend').map(n=>`<option ${n==='payment'?'selected':''}>${n}</option>`).join('')}
function paint(d){data=d;const L=d.live,rank=d.ranking||[],top=rank[0],incident=top&&top.score>=DETECT,inj=L.injected;
 $('status').textContent=!L.running?'stopped':incident?'incident':L.spans<400?'warming up':'healthy';$('spans').textContent=L.spans.toLocaleString();$('elapsed').textContent=Math.round(L.elapsed_s)+'s';$('win').textContent=L.window_s+'s windows';
 ['stop','clear','inject'].forEach(i=>$(i).disabled=!L.running);$('start').disabled=L.running;
 detectedAt=L.detected_at_s;
 if(Object.keys(L.health).length)populate(L.health);
 if(!L.running){set('Find the cause,','see the impact.');$('v-sub').textContent='Nine real services, real traffic, real spans. The analyzer is never told what you break.'}
 else if(L.spans<400){set('Learning what normal looks like,','hold on.');$('v-sub').innerHTML=`${L.spans} spans so far. Give it ~20 seconds before breaking something, so there is a baseline to compare against.`}
 else if(incident){const e=top.evidence;set(`<b>${top.suspected_component}</b> is the root cause,`,`start there.`);$('v-sub').innerHTML=`Edge <b>${top.edge.replace('->',' → ')}</b> · p99 <b>${fmt(e.p99_ms)}</b> · errors <b>${(e.error_rate*100).toFixed(1)}%</b> · ${e.retry_mean.toFixed(2)} retries per call.`}
 else{set('Everything looks normal,','for now.');$('v-sub').textContent=`No edge crossed the detection threshold (top score ${top?top.score.toFixed(1):'0'} of ${DETECT}).`}
 const t=$('v-truth');if(inj){const hit=incident&&top.suspected_component===inj.service;t.className='truth '+(hit?'ok':incident?'miss':'');t.textContent=`Ground truth (hidden from analyzer): ${inj.mode} in ${inj.service} at ${inj.at_s}s — ${hit?'✓ correctly localized':incident?'✗ analyzer disagrees':'not detected yet…'}`}else{t.className='truth';t.textContent=''}
 $('nodes').innerHTML=Object.entries(L.health).map(([n,up])=>{const f=inj&&inj.service===n,cls=!up?'dead':f?'fault':'',lbl=!up?'DOWN':f?inj.mode.toUpperCase():'UP';return`<div class="node ${cls} ${incident&&top.suspected_component===n?'root':''}">${n}<i>${lbl}</i></div>`}).join('')||'<p class="empty">No services running.</p>';
 const edges=Object.keys(d.edge_metrics||{}).sort((a,b)=>d.edge_metrics[b].p99_ms-d.edge_metrics[a].p99_ms);
 $('edges').querySelector('tbody').innerHTML=edges.map(k=>{const m=d.edge_metrics[k];return`<tr class="${incident&&k===top.edge?'hot':''}"><td>${k.replace('->',' → ')}</td><td>${m.calls}</td><td>${(m.error_rate*100).toFixed(1)}%</td><td>${fmt(m.p50_ms)}</td><td>${fmt(m.p99_ms)}</td></tr>`}).join('');
 $('ranks').innerHTML=incident?rank.filter(r=>r.score>=DETECT).slice(0,5).map((r,i)=>`<div class="rank"><span>${i+1}. ${r.edge.replace('->',' → ')}<small>p99 ×${(1+r.evidence.p99_lift).toFixed(1)} · err ${(r.evidence.error_rate*100).toFixed(0)}%</small></span><b>${r.score.toFixed(0)}</b></div>`).join(''):'<p class="empty">Nothing above threshold.</p>';
 $('blast').className='blast';$('blast').innerHTML=incident&&d.blast_radius.length?d.blast_radius.map(b=>`<div><span>${b.application}</span><span>${b.hops} hop${b.hops>1?'s':''} · ${(b.traffic_weight*100).toFixed(0)}%</span></div>`).join(''):'<p class="empty">—</p>';
 $('traces').innerHTML=(L.traces||[]).map(t=>`<div class="trace"><code>${t.trace_id}</code>${t.spans.map(s=>`<span class="sp ${s.status!=='OK'?'err':s.ms>400?'slow':''}">${s.edge.replace('->','→')} ${fmt(s.ms)}${s.retries?` ↻${s.retries}`:''}</span>`).join('')}</div>`).join('')||'<p class="empty">No traffic yet.</p>';
 chartModel=buildChart(d);draw()}
async function poll(){try{paint(await(await fetch('/api/live/report?window=2')).json())}catch(e){$('status').textContent='server offline'}}
$('start').onclick=async()=>{$('start').disabled=true;$('status').textContent='starting…';populated=false;await post('/api/live/start',{rps:25});poll()};
$('stop').onclick=async()=>{await post('/api/live/stop');poll()};
$('inject').onclick=async()=>{await post('/api/live/fault',{service:$('svc').value,mode:$('mode').value});detectedAt=null;poll()};
$('clear').onclick=async()=>{await post('/api/live/clear');detectedAt=null;poll()};
poll();setInterval(poll,2000);
