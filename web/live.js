const $=id=>document.getElementById(id),post=(p,b={})=>fetch(p,{method:'POST',body:JSON.stringify(b)}).then(r=>r.json());
const fmt=x=>x>=1000?(x/1000).toFixed(2)+'s':Math.round(x)+'ms',DETECT=15;let timer,populated=false;
function spark(pts,key,hotAt){if(!pts||pts.length<2)return'';const v=pts.map(p=>p[key]),mx=Math.max(...v,1),w=90,h=22;
 const d=v.map((y,i)=>`${i?'L':'M'}${(i/(v.length-1)*w).toFixed(1)},${(h-1-y/mx*(h-3)).toFixed(1)}`).join(' ');
 return`<svg class="spark" viewBox="0 0 ${w} ${h}"><path d="${d}" fill="none" stroke="${hotAt?'#F45031':'#7aa5ff'}" stroke-width="1.6"/></svg>`}
function populate(h){if(populated)return;populated=true;$('svc').innerHTML=Object.keys(h).filter(n=>n!=='frontend').map(n=>`<option ${n==='payment'?'selected':''}>${n}</option>`).join('')}
function paint(d){const L=d.live,rank=d.ranking||[],top=rank[0],incident=top&&top.score>=DETECT;
 $('status').textContent=L.running?`● LIVE · ${L.spans} SPANS`:'● CLUSTER STOPPED';$('elapsed').textContent=L.running?`${L.elapsed_s}s elapsed`:'—';$('win').textContent=L.window_s;
 $('start').disabled=L.running;$('stop').disabled=!L.running;$('inject').disabled=!L.running;$('clear').disabled=!L.running;
 if(Object.keys(L.health).length)populate(L.health);
 const v=$('verdict');v.className='verdict card '+(!L.running||!L.spans?'':incident?'bad':'good');
 if(!L.running){$('v-title').textContent='Start the cluster to begin';$('v-sub').textContent='The analyzer reads only raw spans emitted by the services. It is never told what you injected.'}
 else if(L.spans<400){$('v-title').textContent='Collecting baseline…';$('v-sub').textContent=`${L.spans} spans so far. Let it run ~20s before injecting a fault so there is a healthy baseline to compare against.`}
 else if(incident){$('v-title').textContent=`Root cause: ${top.suspected_component}`;$('v-sub').textContent=`Edge ${top.edge} · p99 ${fmt(top.evidence.p99_ms)} · errors ${(top.evidence.error_rate*100).toFixed(1)}% · retries/call ${top.evidence.retry_mean.toFixed(2)} · onset in window ${top.onset_window}`}
 else{$('v-title').textContent='All services healthy';$('v-sub').textContent=`No edge crossed the detection threshold (top score ${top?top.score.toFixed(1):'0'} < ${DETECT}).`}
 const inj=L.injected;$('v-truth').innerHTML=inj?(()=>{const hit=incident&&top.suspected_component===inj.service;return`<span class="${hit?'ok':'miss'}">GROUND TRUTH (not seen by analyzer): ${inj.mode} injected into ${inj.service} at ${inj.at_s}s — ${hit?'✓ correctly localized':incident?'✗ analyzer disagrees':'… not detected yet'}</span>`})():'';
 $('nodes').innerHTML=Object.entries(L.health).map(([n,up])=>{const f=inj&&inj.service===n,cls=!up?'dead':f?'fault':'',lbl=!up?'DOWN':f?inj.mode.toUpperCase():'UP';return`<div class="node ${cls} ${incident&&top.suspected_component===n?'root':''}">${n}<i>${lbl}</i></div>`}).join('')||'<p class="empty">No services running.</p>';
 const edges=Object.keys(d.edge_metrics||{}).sort((a,b)=>d.edge_metrics[b].p99_ms-d.edge_metrics[a].p99_ms);
 $('edges').querySelector('tbody').innerHTML=edges.map(k=>{const m=d.edge_metrics[k],hot=incident&&k===top.edge;return`<tr class="${hot?'hot':''}"><td>${k.replace('->',' → ')}</td><td>${m.calls}</td><td>${(m.error_rate*100).toFixed(1)}%</td><td>${fmt(m.p50_ms)}</td><td>${fmt(m.p99_ms)}</td><td>${spark(d.series[k],'p99',hot)}</td></tr>`}).join('');
 $('ranks').innerHTML=incident?rank.filter(r=>r.score>=DETECT).slice(0,5).map((r,i)=>`<div class="rank"><span>${i+1}. ${r.edge.replace('->',' → ')}<small>p99 ×${(1+r.evidence.p99_lift).toFixed(1)} · err ${(r.evidence.error_rate*100).toFixed(0)}%</small></span><b>${r.score.toFixed(0)}</b></div>`).join(''):'<p class="empty">Nothing above threshold.</p>';
 $('blast').innerHTML=incident&&d.blast_radius.length?d.blast_radius.map(b=>`<div><span>${b.application}</span><span>${b.hops} hop${b.hops>1?'s':''} · ${(b.traffic_weight*100).toFixed(0)}% traffic</span></div>`).join(''):'<p class="empty">—</p>';
 $('traces').innerHTML=(L.traces||[]).map(t=>`<div class="trace"><code>${t.trace_id}</code>${t.spans.map(s=>`<span class="sp ${s.status!=='OK'?'err':s.ms>400?'slow':''}">${s.edge.replace('->','→')} ${fmt(s.ms)}${s.retries?` ↻${s.retries}`:''}</span>`).join('')}</div>`).join('')||'<p class="empty">No traffic yet.</p>'}
async function poll(){try{paint(await(await fetch('/api/live/report?window=2')).json())}catch(e){$('status').textContent='● SERVER UNREACHABLE'}}
$('start').onclick=async()=>{$('start').disabled=true;$('status').textContent='● STARTING 9 SERVICES…';populated=false;await post('/api/live/start',{rps:25});poll()};
$('stop').onclick=async()=>{await post('/api/live/stop');poll()};
$('inject').onclick=async()=>{const r=await post('/api/live/fault',{service:$('svc').value,mode:$('mode').value});poll()};
$('clear').onclick=async()=>{await post('/api/live/clear');poll()};
poll();timer=setInterval(poll,2000);
