import {DOMAIN} from '../constants/domain.js';
import {store,loadPrivacy} from '../stores/research.js';
import {privacy} from '../api/research.js';
import {table} from '../components/common/table.js';
import {studySelect} from '../components/common/study-select.js';
import {esc,fmt} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';

const cap=DOMAIN.privacy?.contribution_cap??1;
function randomKey(){
  if(globalThis.crypto?.randomUUID)return crypto.randomUUID();
  return 'key-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,12);
}

export async function render(){
  const writable=localStorage.getItem('research-role')!=='viewer';
  const isAdmin=localStorage.getItem('research-role')==='admin';
  await loadPrivacy();
  const p=store.privacy;if(!p)return '<p>读取失败</p>';
  const b=p.budget||{total_epsilon:0,spent_epsilon:0,remaining_epsilon:0};
  const channels=p.channels||[];
  const defEps=DOMAIN.privacy?.default_release_epsilon??1;
  const perQuery=channels.length?+(defEps/(4*channels.length)).toFixed(6):null;
  const latest=p.releases?.[0];
  let key=sessionStorage.getItem('privacy-key');
  if(!key){key=randomKey();sessionStorage.setItem('privacy-key',key);}   // 失败后刷新仍沿用同一键，避免重复扣额
  return `<div class="eyebrow">06 / CHANNEL REVIEW</div><h1>分渠道投放复盘</h1>
<p class="lead">按预先登记的渠道分别核算双组触达与点击；所有对外数字均加入Laplace噪声，页面与下载共用同一份已发布结果。</p>
<div class="method-note">${esc(DOMAIN.privacy?.note||'')} 每位受众跨组跨渠道总贡献上限为 ${cap}。</div>
<div class="toolbar">${studySelect()}</div>
<h2>隐私额度 <small>发布即扣减，不可回收；额度不足仍可读取旧版本</small></h2>
${table(['总额度 ε','已用 ε','剩余 ε','最近更新'],[[fmt(b.total_epsilon),fmt(b.spent_epsilon),fmt(b.remaining_epsilon),esc(b.updated_at||'—')]])}
${isAdmin?`<form id="budget-form" class="inline-form"><label>重设总 ε (0–100)<input name="total_epsilon" type="number" step="any" min="0" value="${b.total_epsilon}" required></label><button type="submit">保存额度</button></form>`:''}
<h2>渠道登记 <small>发布前整组冻结；已录入受众的渠道不可删除</small></h2>
${channels.length?table(['渠道','登记人','登记时间',...(writable?['操作']:[])],channels.map(c=>[esc(c.name),esc(c.created_by),esc(c.created_at),...(writable?[{html:`<button class="text" data-drop-channel="${c.id}">删除</button>`}]:[])])):'<p class="method-note">尚未登记渠道。</p>'}
${writable?`<form id="channel-form" class="inline-form"><label>新渠道名称<input name="name" required maxlength="80" placeholder="如 站内信 / 推送 / 邮件"></label><button type="submit">登记渠道</button></form>`:''}
<h2>受众触达录入 <small>每位受众仅一条记录，保证跨组跨渠道总贡献为 ${cap}</small></h2>
${writable&&channels.length?`<form id="touch-form" class="inline-form">
<label>受众标识<input name="audience_key" required maxlength="120" placeholder="如 AUD-0001"></label>
<label>渠道<select name="channel">${channels.map(c=>`<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('')}</select></label>
<label>组别<select name="group"><option value="A">A</option><option value="B">B</option></select></label>
<label>触达<select name="reached"><option value="true">是</option><option value="false">否</option></select></label>
<label>点击<select name="clicked"><option value="false">否</option><option value="true">是</option></select></label>
<button type="submit">保存触达</button></form>`:''}
${table(['受众标识','渠道','组别','触达','点击',...(writable?['操作']:[])],store.touches.slice(-50).reverse().map(t=>[esc(t.audience_key),esc(t.channel),esc(t.group),t.reached?'是':'否',t.clicked?'是':'否',...(writable?[{html:`<button class="text" data-drop-touch="${t.id}">移除</button>`}]:[])]))}
<p><small>共 ${store.touches.length} 条受众记录，显示最近50条。</small></p>
<h2>发布带噪结果</h2>
<div class="method-note">本次 ε 在 4×渠道数 个子查询间均分${perQuery!=null?`；当前 ${channels.length} 个渠道，若本次 ε=${defEps} 则每子查询 ε=${perQuery}`:''}。同一幂等键重试不会重复扣额度或重抽噪声；更正另发新版。</div>
${writable&&channels.length?`<form id="publish-form" class="inline-form">
<label>本次 ε (0–10)<input name="epsilon" type="number" step="any" min="0" max="10" value="${DOMAIN.privacy?.default_release_epsilon??1}" required></label>
<label>幂等键 (失败重试沿用；更改ε或意图请换新键)<input name="idempotency_key" value="${esc(key)}" required minlength="8" maxlength="160"></label>
<label>更正自版本<select name="corrects_release_id"><option value="">全新发布</option>${(p.releases||[]).map(r=>`<option value="${r.id}">v${r.version} · ε=${r.epsilon}</option>`).join('')}</select></label>
<button type="submit">扣减额度并发布 →</button></form>`:latest?`<p class="method-note">观察员可读取已发布版本，不能发起新发布。</p>`:''}
<h2>发布历史</h2>
${table(['版本','ε','子查询ε','本版输入SHA256','更正自','发布人','时间'],(p.releases||[]).map(r=>[{html:`<a href="#release/${r.id}">v${r.version}</a>`},fmt(r.epsilon),r.payload?.per_query_epsilon??'—',esc((r.input_sha256||'').slice(0,16)),r.corrects_release_id?`v${(p.releases.find(x=>x.id===r.corrects_release_id)||{}).version||r.corrects_release_id}`:'—',esc(r.created_by||''),esc(r.created_at||'')]))}`;
}

export function bind(refresh){
  const sel=document.getElementById('study-select');if(sel)sel.onchange=()=>{store.studyId=+sel.value;refresh();};
  bindForm('budget-form',async data=>{await privacy.setBudget(store.studyId,+data.total_epsilon);refresh();});
  bindForm('channel-form',async data=>{await privacy.addChannel(store.studyId,data.name);refresh();});
  bindForm('touch-form',async data=>{await privacy.saveTouch(store.studyId,{audience_key:data.audience_key,channel:data.channel,group:data.group,reached:data.reached==='true',clicked:data.clicked==='true'});refresh();});
  bindForm('publish-form',async data=>{
    const key=data.idempotency_key.trim()||randomKey();
    sessionStorage.setItem('privacy-key',key);
    const r=await privacy.publish(store.studyId,{epsilon:+data.epsilon,idempotency_key:key,corrects_release_id:data.corrects_release_id?+data.corrects_release_id:null});
    sessionStorage.removeItem('privacy-key');    // 成功后才轮换，失败重试沿用同一键
    location.hash='release/'+r.id;
  });
  document.querySelectorAll('[data-drop-channel]').forEach(el=>el.onclick=async()=>{try{await privacy.removeChannel(store.studyId,+el.dataset.dropChannel);refresh();}catch(e){document.getElementById('notice').textContent=e.message;}});
  document.querySelectorAll('[data-drop-touch]').forEach(el=>el.onclick=async()=>{try{await privacy.removeTouch(store.studyId,+el.dataset.dropTouch);refresh();}catch(e){document.getElementById('notice').textContent=e.message;}});
}
