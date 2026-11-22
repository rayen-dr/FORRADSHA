const FOUNDER={name:"Rayen Karous",role:"Founder"}; // edit here
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const S=$$(".s");let cur=0;
$("#fname").textContent=FOUNDER.name;$("#frole").textContent=FOUNDER.role;
S.forEach((s,i)=>s.id="s"+(i+1));
$$(".txt>*,.s>*:not(.txt):not(#stage)").forEach((e,i)=>{e.classList.add("rv");e.style.transitionDelay=(i%6)*.08+"s"});
$("#dots").innerHTML=S.map((_,i)=>`<a href="#s${i+1}" title="Slide ${i+1}"></a>`).join("");
function go(i){cur=i;S.forEach((s,k)=>s.classList.toggle("on",k==i));$$("#dots a").forEach((a,k)=>a.classList.toggle("on",k==i));Watch.slide(i);if(i==5)count()}
new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting&&go(S.indexOf(e.target))),{threshold:.55}).observe&&S.forEach(s=>new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting&&go(S.indexOf(e.target))),{threshold:.55}).observe(s));
addEventListener("keydown",e=>{if(e.target.matches("button,input"))return;if(e.key=="t"||e.key=="T")return clock();const n={ArrowRight:1,ArrowDown:1,PageDown:1," ":1,ArrowLeft:-1,ArrowUp:-1,PageUp:-1}[e.key];if(n){e.preventDefault();S[Math.max(0,Math.min(S.length-1,cur+n))].scrollIntoView({behavior:"smooth"})}});
let t0=0,iv;function clock(){if(t0){t0=0;clearInterval(iv);$("#clock").textContent="▶ 0:00 / 4:00";$("#clock").classList.remove("late");return}t0=Date.now();iv=setInterval(tick,500);tick()}
function tick(){const s=Math.floor((Date.now()-t0)/1000);$("#clock").textContent=`⏸ ${Math.floor(s/60)}:${String(s%60).padStart(2,"0")} / 4:00 · slide ${cur+1}: ${S[cur].dataset.t}s`;$("#clock").classList.toggle("late",s>240)}
$("#clock").onclick=clock;
function count(){$$("[data-count]").forEach(el=>{const to=+el.dataset.count,d=+el.dataset.d,id=setInterval(()=>{el._t=Math.min(1,(el._t||0)+.04);el.textContent=(to*(1-Math.pow(1-el._t,3))).toFixed(d);if(el._t==1){clearInterval(id);el._t=0}},25)});$$(".m i").forEach(b=>b.style.width=b.dataset.w+"%")}
// Slide 3: components
const MT=[["Heart rate","ppg","Optical MAX30102 sensor on the back of the watch."],["SpO₂","ppg","Same optical sensor, red and infrared light."],["Temperature","temp","Skin temperature sensor touching the wrist."],["HRV","ppg","Computed from beat-to-beat timing of the optical signal."],["Blood pressure","ppg","Estimated at the wrist; needs hardware validation."],["Activity","imu","MPU6050 motion sensor: steps and intensity."],["Fall detection","imu","MPU6050 motion sensor detects sudden impact."]];
$("#metrics").innerHTML=MT.map((m,i)=>`<button class="chip" data-i="${i}">${m[0]}</button>`).join("");
$$("#metrics .chip").forEach(b=>b.onclick=()=>{const m=MT[b.dataset.i];$("#cap").textContent=m[2];Watch.focus(m[1]);if(!$("#exp").dataset.on)$("#exp").click();$$("#metrics .chip").forEach(x=>x.classList.toggle("on",x==b))});
$("#exp").onclick=e=>{const on=Watch.toggle();e.target.dataset.on=on?"1":"";e.target.textContent=on?"Assemble":"Exploded view";if(!on)Watch.focus(null)};
// Slide 5: context toggle
$$("[data-ctx]").forEach(b=>b.onclick=()=>{const r=b.dataset.ctx=="rest";$("#ctxout").innerHTML=r?'<b class="bad">Emergency flagged</b>HR 140 at rest is far above this patient’s normal.':'<b class="good">Normal</b>HR 140 is expected during exercise.';$$("[data-ctx]").forEach(x=>x.classList.toggle("on",x==b))});$("[data-ctx=rest]").click();
// Slide 8: levels
const PH={ok:["All good","Monitoring continues. Keep wearing your watch.",68,97],rest:["Please rest","Your values drift from your normal. Rest and measure again soon.",88,95],consult:["Contact your doctor","The change persists. Call your doctor today.",106,92.5],alert:["Emergency","Alert sent. Call 190 and go to the nearest emergency department.",128,88.5]};
function phone(k){const p=PH[k];$("#pst").textContent=p[0];$("#pst").className="pill "+k;$("#ptx").textContent=p[1];Watch.vitals(p[2],p[3],k)}
$$(".lv tr").forEach(r=>r.onclick=()=>phone(r.dataset.lv));
// Slide 9: scripted replay
const cx=$("#chart").getContext("2d"),LB={ok:"Normal",rest:"Rest",consult:"Consultation",alert:"Emergency"};let H=[],tm=0,rid,lastLv;
function sim(t){const n=Math.sin(t*3)*1.5;if(t<6)return{hr:68+n,sp:97+n/4,lv:"ok"};if(t<11)return{hr:68+(t-6)*3.4+n,sp:97-(t-6)*.4+n/4,lv:"rest"};if(t<16)return{hr:85+(t-11)*4+n,sp:95-(t-11)*.5+n/4,lv:"consult"};const u=Math.min(t-16,6);return{hr:105+u*4+n,sp:92.5-u*.7+n/4,lv:"alert"}}
function draw(){const w=640,h=220,c=cx;c.clearRect(0,0,w,h);c.fillStyle="#3ad1c01a";c.fillRect(0,h-(76-40)/110*h*1.0-0,w,0);const y=v=>h-(v-40)/110*h;c.fillStyle="#3ad1c014";c.fillRect(0,y(76),w,y(60)-y(76));c.font="11px sans-serif";c.fillStyle="#8fa1b2";c.fillText("personal baseline (HR)",8,y(76)-4);
[["hr","#3ad1c0",v=>y(v)],["sp","#e9a23b",v=>y(40+(v-84)*5)]].forEach(([k,col,f])=>{c.beginPath();c.strokeStyle=col;c.lineWidth=2;H.forEach((p,i)=>{const x=i/60*w;i?c.lineTo(x,f(p[k])):c.moveTo(x,f(p[k]))});c.stroke()});c.fillStyle="#3ad1c0";c.fillText("HR",w-52,16);c.fillStyle="#e9a23b";c.fillText("SpO₂",w-30,16)}
function why(p){const dh=p.hr-68,ds=97-p.sp,cls=p.lv=="ok"?"Normal":p.lv=="alert"?"Emergency":"Monitor",fc=p.lv=="alert"?"High":p.lv=="consult"?"Rising":"Low";$("#why").innerHTML=`<li>HR ${dh>=0?"+":""}${dh.toFixed(0)} bpm vs this patient’s baseline</li><li>SpO₂ −${Math.max(0,ds).toFixed(1)} points vs baseline</li><li>Activity low: not exercise</li><li>Random Forest: <b>${cls}</b></li><li>Gradient Boosting 15-min forecast: <b>${fc}</b></li>`}
function step(){tm+=.4;const p=sim(tm);H.push(p);$("#vals").textContent=`HR ${p.hr.toFixed(0)} · SpO₂ ${p.sp.toFixed(1)}`;$("#dlv").textContent=LB[p.lv];$("#dlv").className="pill "+p.lv;Watch.vitals(p.hr,p.sp,p.lv);why(p);
if(p.lv!=lastLv){lastLv=p.lv;const m={rest:"Rest recommended (watch + patient app)",consult:"Doctor notified: consultation recommended",alert:"Emergency workflow: watch notification + hospital alert record (mock_sent)"}[p.lv];if(m)$("#log").insertAdjacentHTML("afterbegin",`<li class="${p.lv}">t+${tm.toFixed(0)}s · ${m}</li>`)}
draw();if(tm>=24)clearInterval(rid)}
function reset(){clearInterval(rid);H=[];tm=0;lastLv=null;$("#log").innerHTML="";$("#vals").textContent="";$("#dlv").textContent="Normal";$("#dlv").className="pill ok";why({hr:68,sp:97,lv:"ok"});Watch.vitals(68,97,"ok");draw()}
$("#run").onclick=()=>{reset();rid=setInterval(step,400)};$("#rst").onclick=reset;reset();go(0);
