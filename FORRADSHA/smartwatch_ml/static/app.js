const SIG={hr:{l:"Fréquence cardiaque",u:"bpm",s:["hr"]},spo2:{l:"SpO₂",u:"%",s:["spo2"]},temp:{l:"Température",u:"°C",s:["temp"]},hrv:{l:"HRV",u:"ms",s:["hrv"]},bp:{l:"Tension",u:"mmHg",s:["sys_bp","dia_bp"]}};
const ACT={OK:["Normal","ok"],REST:["Repos conseillé","warn"],CONSULT_DOCTOR:["Consulter un médecin","warn2"],ALERT_HOSPITAL:["Alerte hôpital","bad"]};
const fmt=t=>t?t.slice(8,10)+"/"+t.slice(5,7)+" "+t.slice(11,16):"en cours";
const chip=a=>`<span class="chip ${ACT[ACT[a]?a:"OK"][1]}">${ACT[ACT[a]?a:"OK"][0]}</span>`;
function chart(p){const keys=SIG[tab].s,W=760,H=260,m={l:46,r:12,t:12,b:28},pts=p.points,n=pts.length;
const vals=keys.flatMap(k=>pts.map(x=>x[k]).filter(v=>v!=null)),bl=keys.map(k=>p.baseline[k].med);
let lo=Math.min(...vals,...bl),hi=Math.max(...vals,...bl);const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;
const X=i=>m.l+i*(W-m.l-m.r)/(n-1),Y=v=>m.t+(hi-v)*(H-m.t-m.b)/(hi-lo),bw=(W-m.l-m.r)/(n-1),ph=H-m.t-m.b;
let s=`<svg viewBox="0 0 ${W} ${H}" id="svg">`;
pts.forEach((x,i)=>{if(x.state>0)s+=`<rect x="${X(i)-bw/2}" y="${m.t}" width="${bw}" height="${ph}" fill="var(${x.state==2?"--bad":"--warn"})" opacity=".2"/>`});
for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,y=Y(v);s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${m.l-6}" y="${y+4}" text-anchor="end" font-size="11" fill="var(--muted)">${v.toFixed(tab==="temp"||tab==="spo2"?1:0)}</text>`}
for(let i=0;i<n;i+=16){s+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" font-size="11" fill="var(--muted)">${fmt(pts[i].t).replace(" ","\u00a0")}</text>`}
bl.forEach(v=>s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--muted)" stroke-dasharray="5 4"/>`);
keys.forEach((k,j)=>{let d="";pts.forEach((x,i)=>{if(x[k]!=null)d+=(d?"L":"M")+X(i).toFixed(1)+" "+Y(x[k]).toFixed(1)});s+=`<path d="${d}" fill="none" stroke="var(${j?"--accent2":"--accent"})" stroke-width="1.8"/>`});
return s+`<rect id="ov" x="${m.l}" y="${m.t}" width="${W-m.l-m.r}" height="${ph}" fill="transparent"/></svg><div class="tip" id="tip"></div>`}
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let st={user:null,patients:[],cur:null,series:null,events:[],alerts:[]},tab="hr",timer=null;
async function api(path,body){const r=await fetch(path,{method:body?"POST":"GET",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
const d=await r.json().catch(()=>({}));if(!r.ok)throw Object.assign(new Error(d.error||"Erreur "+r.status),{status:r.status});return d}
function showLogin(msg){clearInterval(timer);$("#app").hidden=true;$("#login").hidden=false;$("#err").textContent=msg||""}
async function boot(){try{st.user=await api("/api/me")}catch(e){return showLogin()}
$("#login").hidden=true;$("#app").hidden=false;$("#who").textContent=st.user.username+" · "+st.user.role;await refresh(true);clearInterval(timer);timer=setInterval(()=>refresh(false),30000)}
async function refresh(first){try{st.patients=await api("/api/patients");if(first||!st.patients.some(p=>p.id===st.cur))st.cur=st.patients[0]?.id;await loadPatient();
$("#gen").textContent="Actualisé à "+new Date().toLocaleTimeString("fr-FR",{hour:"2-digit",minute:"2-digit"})}catch(e){if(e.status===401)showLogin("Session expirée")}}
async function loadPatient(){if(!st.cur){st.series=null;return render()}const id=encodeURIComponent(st.cur);
[st.series,st.events,st.alerts]=await Promise.all([api(`/api/patients/${id}/series?bucket=30`),api(`/api/patients/${id}/events`),api(`/api/alerts?patient_id=${id}`)]);render()}
function list(){$("#pl").innerHTML=st.patients.map(p=>`<button class="pi ${p.id===st.cur?"on":""}" data-id="${esc(p.id)}"><b>${esc(p.name)}</b><small>${esc(p.age)} ans · ${esc(p.n_alerts)} alerte(s)</small><div style="margin-top:6px">${chip(p.last_action)}</div></button>`).join("")||"<div class='sub'>Aucun patient</div>";
document.querySelectorAll(".pi").forEach(b=>b.onclick=()=>{st.cur=b.dataset.id;loadPatient()})}
function render(){list();const p=st.patients.find(x=>x.id===st.cur),s=st.series;
if(!p||!s||!s.points.length||!s.baseline){$("#main").innerHTML="<div class='card'>Pas encore de données analysées (calibration en cours : 6 h de mesures nécessaires).</div>";return}
const hosp=st.alerts.filter(a=>a.kind==="ALERTE_HOPITAL");
$("#main").innerHTML=`<div class="kpis"><div class="card kpi"><b>${chip(p.last_action)}</b><span>État actuel</span></div><div class="card kpi"><b>${st.events.length}</b><span>Épisodes détectés</span></div><div class="card kpi"><b>${hosp.length}</b><span>Alertes hôpital</span></div><div class="card kpi"><b>${s.baseline.hr.med.toFixed(0)} bpm</b><span>FC de base (calibration)</span></div></div>
<div class="card"><div class="tabs">${Object.keys(SIG).map(k=>`<button data-t="${k}" class="${k===tab?"on":""}">${SIG[k].l}</button>`).join("")}</div><div class="cw">${chart(s)}</div>
<div class="leg"><span><i style="background:var(--accent)"></i>${SIG[tab].l} (${SIG[tab].u})${tab==="bp"?" – systolique":""}</span>${tab==="bp"?`<span><i style="background:var(--accent2)"></i>diastolique</span>`:""}<span>- - ligne de base du patient</span><span><i style="background:var(--warn);opacity:.4"></i>à surveiller</span><span><i style="background:var(--bad);opacity:.4"></i>urgence</span></div></div>
<div class="card tw"><b>Quand les changements sont survenus</b><table><tr><th>Début</th><th>Fin</th><th>Décision</th><th>Raisons</th></tr>${st.events.map(e=>`<tr><td>${fmt(e.t_start)}</td><td>${fmt(e.t_end)}</td><td>${chip(e.action)}</td><td>${esc(e.reasons)||"–"}</td></tr>`).join("")||"<tr><td colspan=4>Aucun épisode</td></tr>"}</table></div>
<div class="card tw"><b>Alertes envoyées</b><table><tr><th>Heure</th><th>Type</th><th>Destinataire</th></tr>${st.alerts.map(a=>`<tr><td>${fmt(a.t)}</td><td>${a.kind==="SONNERIE_MONTRE"?"Sonnerie montre":"Alerte hôpital"}</td><td>${esc(a.hospital)} <small class="sub">(${esc(a.status)})</small></td></tr>`).join("")||"<tr><td colspan=3>Aucune alerte</td></tr>"}</table></div>`;
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{tab=b.dataset.t;render()});
const ov=$("#ov"),tip=$("#tip"),svg=$("#svg"),n=s.points.length;
ov.onmousemove=e=>{const r=svg.getBoundingClientRect(),i=Math.max(0,Math.min(n-1,Math.round(((e.clientX-r.left)/r.width*760-46)/(702/(n-1))))),x=s.points[i];
tip.style.display="block";tip.style.left=Math.min(e.clientX-r.left+12,r.width-150)+"px";tip.style.top="8px";tip.textContent=fmt(x.t)+" · "+SIG[tab].s.map(k=>x[k]).join(" / ")+" "+SIG[tab].u};
ov.onmouseleave=()=>tip.style.display="none"}
$("#lf").onsubmit=async e=>{e.preventDefault();try{await api("/api/login",{username:$("#u").value,password:$("#pw").value});$("#pw").value="";boot()}catch(err){$("#err").textContent=err.message}};
$("#out").onclick=async()=>{try{await api("/api/logout",{})}catch(e){}showLogin()};
boot();
