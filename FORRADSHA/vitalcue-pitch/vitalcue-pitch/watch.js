// Procedural 3D smartwatch (three.js r147, offline). Concept model, not a certified device.
(function(){
let R;try{R=new THREE.WebGLRenderer({canvas:document.getElementById("gl"),antialias:true,alpha:true})}catch(e){document.getElementById("gl").style.display="none";window.Watch={slide(){},toggle(){},focus(){},vitals(){}};return}
R.setPixelRatio(Math.min(devicePixelRatio,2));
const sc=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,1,.1,50);cam.position.z=10;
sc.add(new THREE.AmbientLight(0xffffff,.75));const dl=new THREE.DirectionalLight(0xffffff,1.1);dl.position.set(3,4,6);sc.add(dl);
const pl=new THREE.PointLight(0x3ad1c0,1.3,25);pl.position.set(-4,-2,5);sc.add(pl);
const root=new THREE.Group(),W=new THREE.Group();root.add(W);sc.add(root);
const M=(c,o)=>new THREE.MeshStandardMaterial(Object.assign({color:c,metalness:.45,roughness:.5},o||{}));
const P=[];
function part(id,mesh,x,y,z0,z1,dx,dy){mesh.position.set(x,y,z0);W.add(mesh);const ms=[];mesh.traverse(o=>o.material&&ms.push(o.material));P.push({id,mesh,x,y,z0,z1,dx:dx||0,dy:dy||0,ms});return mesh}
const cyl=(r,h,m)=>{const g=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,48),m);g.rotation.x=Math.PI/2;return g};
const box=(w,h,d,m)=>new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m);
const caseM=M(0x1c2733,{metalness:.7,roughness:.35,transparent:true});
part("case",cyl(1.08,.5,caseM),0,0,0,0);
const bez=new THREE.Mesh(new THREE.TorusGeometry(1.02,.06,16,64),M(0x3ad1c0,{emissive:0x3ad1c0,emissiveIntensity:.4}));bez.position.z=.27;W.add(bez);
part("glass",cyl(.97,.03,M(0x9fe8ff,{transparent:true,opacity:.2,roughness:.1})),0,0,.31,1.5);
// OLED with live screen texture
const tc=document.createElement("canvas");tc.width=tc.height=256;const tx=new THREE.CanvasTexture(tc);
const oled=new THREE.Group();oled.add(cyl(.92,.03,M(0x05080c)));const scr=new THREE.Mesh(new THREE.CircleGeometry(.88,48),new THREE.MeshBasicMaterial({map:tx}));scr.position.z=.02;oled.add(scr);
part("oled",oled,0,0,.27,1.0);
const esp=new THREE.Group();esp.add(box(1.35,1.35,.06,M(0x1e6b4f)));const chip=box(.55,.55,.05,M(0x9aa7b4,{metalness:.8}));chip.position.z=.05;esp.add(chip);part("esp",esp,0,0,.1,.55);
part("imu",box(.3,.3,.05,M(0x2a6f97)),-.35,.4,.16,.9);
part("vib",cyl(.13,.2,M(0x9aa7b4)),-.65,-.45,-.02,-.1,-.5,-.2);
part("bat",box(1.1,.75,.16,M(0x3b4a5a)),.05,0,-.14,-.6);
const ppg=new THREE.Group();ppg.add(cyl(.32,.05,M(0x103a40)));[[-.1,0xff4040],[.1,0xff9090]].forEach(([x,c])=>{const l=new THREE.Mesh(new THREE.SphereGeometry(.06,12,12),M(c,{emissive:c,emissiveIntensity:.8}));l.position.set(x,0,-.04);ppg.add(l)});part("ppg",ppg,-.2,-.05,-.3,-1.1);
part("temp",box(.22,.22,.05,M(0xe9a23b)),.6,-.5,-.3,-1.1);
const btn=cyl(.12,.26,M(0xd1495b));btn.rotation.set(0,0,Math.PI/2);part("btn",btn,1.12,0,0,0,.55,0);
[[1.75,1],[-1.75,-1]].forEach(([y])=>part("strap",box(.95,1.5,.16,M(0x26323f,{roughness:.8})),0,y,-.08,-.08,0,y>0?.5:-.5));
const LV={ok:[0x3ad1c0,"#3ad1c0"],rest:[0xe9a23b,"#e9a23b"],consult:[0xf08a3c,"#f08a3c"],alert:[0xd1495b,"#ff6b7d"]};
const S={hr:68,sp:97,lv:"ok"};let hl=null,ex=0,exT=0,ux=0,uy=0,uz=1,drag=false,sl=0,last=0;
function screen(){const c=tc.getContext("2d");c.fillStyle="#05080c";c.fillRect(0,0,256,256);c.fillStyle=LV[S.lv][1];c.textAlign="center";c.font="bold 78px sans-serif";c.fillText(Math.round(S.hr),128,120);c.font="18px sans-serif";c.fillStyle="#8fa1b2";c.fillText("bpm",128,146);c.fillStyle="#e6edf3";c.font="bold 28px sans-serif";c.fillText("SpO₂ "+S.sp.toFixed(0)+"%",128,192);c.font="bold 16px sans-serif";c.fillStyle=LV[S.lv][1];c.fillText(S.lv=="alert"?"EMERGENCY":S.lv=="ok"?"NORMAL":S.lv.toUpperCase(),128,226);tx.needsUpdate=true}
const CFG=[[.74,.55,1,-.45,1],[.8,.56,.85,.4,1],[.7,.54,1.1,-.3,0],[.93,.16,.26,0,1],[.93,.16,.26,0,1],[.93,.16,.26,0,1],[.95,.14,.2,0,1],[.9,.2,.3,0,1],[.9,.2,.38,0,1],[.78,.52,.85,-.3,1]];
const C={x:.74,y:.55,s:1,ry:-.45},T={x:.74,y:.55,s:1,ry:-.45};let auto=1;
function size(){R.setSize(innerWidth,innerHeight,false);cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix()}addEventListener("resize",size);size();
function loop(t){requestAnimationFrame(loop);for(const k in C)C[k]+=(T[k]-C[k])*.06;ex+=(exT-ex)*.08;
P.forEach(p=>{p.mesh.position.set(p.x+p.dx*ex,p.y+p.dy*ex,p.z0+(p.z1-p.z0)*ex);const on=p.id==hl;p.ms.forEach(m=>{if(m.emissive&&m!==caseM){m.emissive.setHex(on?0x3ad1c0:m.userData.e);m.emissiveIntensity=on?.9+.3*Math.sin(t/200):m.userData.i}})});
caseM.opacity=1-.8*ex;const beat=Math.pow(Math.max(0,Math.sin(t/1000*S.hr/60*Math.PI*2)),8);bez.material.emissive.setHex(LV[S.lv][0]);bez.material.emissiveIntensity=.25+1.1*beat;
if(t-last>200){screen();last=t}
const vh=2*10*Math.tan(17.5*Math.PI/180),vw=vh*cam.aspect;root.position.set((C.x-.5)*vw+(S.lv=="alert"?Math.sin(t/35)*.03:0),(.5-C.y)*vh,0);root.scale.setScalar(C.s*uz*1.35);
if(!drag&&sl!=2){ux*=.95;uy*=.95}W.rotation.y=C.ry+(auto&&!drag?Math.sin(t/2600)*.35:0)+ux;W.rotation.x=uy;R.render(sc,cam)}
requestAnimationFrame(loop);
const st=document.getElementById("stage");let px,py;
st.addEventListener("pointerdown",e=>{drag=true;px=e.clientX;py=e.clientY;st.setPointerCapture(e.pointerId)});
st.addEventListener("pointermove",e=>{if(!drag)return;ux+=(e.clientX-px)*.01;uy=Math.max(-1,Math.min(1,uy+(e.clientY-py)*.01));px=e.clientX;py=e.clientY});
st.addEventListener("pointerup",()=>drag=false);
st.addEventListener("wheel",e=>{e.preventDefault();uz=Math.max(.6,Math.min(1.7,uz-e.deltaY*.001))},{passive:false});
window.Watch={slide(i){sl=i;const c=CFG[i];Object.assign(T,{x:c[0],y:c[1],s:c[2],ry:c[3]});auto=c[4];if(i!=2){exT=0;uz=1}},
toggle(){exT=exT?0:1;return !!exT},focus(id){hl=id},vitals(hr,sp,lv){S.hr=hr;S.sp=sp;S.lv=lv}};
P.forEach(p=>p.ms.forEach(m=>{if(m.emissive){m.userData.e=m.emissive.getHex();m.userData.i=m.emissiveIntensity}}));
})();
