import {store} from '../stores/research.js';
import {privacy} from '../api/research.js';
import {table} from '../components/common/table.js';
import {esc,fmt} from '../utils/format.js';
import {download} from '../utils/download.js';

const GROUPS=['A','B'];
function blocks(payload){
  const out=[];
  for(const ch of payload.channels){
    out.push({label:`${ch.channel} · A组`,x:ch.groups.A});
    out.push({label:`${ch.channel} · B组`,x:ch.groups.B});
    out.push({label:`${ch.channel} · 小计`,x:ch.total});
  }
  for(const g of GROUPS) out.push({label:`全部渠道 · ${g}组`,x:payload.totals[g]});
  out.push({label:'全部渠道 · 总计',x:payload.totals.all});
  return out;
}

export async function render(id){
  if(!id)return `<h1>带噪结果</h1><p>选择一次发布版本查看分渠道带噪计数。合作方仅能读取此页。</p><p class="method-note">请从<a href="#partner">合作方视图</a>或<a href="#channels">分渠道复盘</a>选择发布版本。</p>`;
  const r=await privacy.release(id);store.releaseId=r.id;
  const p=r.payload;
  return `<div class="eyebrow">07 / PRIVACY RELEASE · V${r.version}</div><h1>分渠道带噪结果 <span class="status completed">v${r.version}</span></h1>
<div class="checksum">RELEASE #${r.id} · 研究 ${r.study_id} · ε=${fmt(r.epsilon)} · 每子查询 ε=${fmt(p.per_query_epsilon)} · ${esc(r.created_at)}</div>
<div class="method-note">这是受众级差分隐私结果：所有计数均带Laplace噪声，<strong>不是真实业务计数</strong>。分渠道带噪计数相加即为总计。查看页面与下载CSV读取的是同一份已发布结果，不会重新抽噪。</div>
${r.corrects_release_id?`<p>本版更正了发布 #${r.corrects_release_id}。</p>`:''}
<h2>分渠道 × 组别明细</h2>
${table(['渠道 / 组别','触达 (带噪)','点击 (带噪)','点击率 (带噪)'],blocks(p).map(({label,x})=>[label,fmt(x.reached),fmt(x.clicked),x.ctr==null?'—':fmt(x.ctr)]))}
<h2>发布参数</h2>
${table(['项目','值'],[['ε',fmt(p.epsilon)],['子查询数',fmt(p.query_count)],['每子查询 ε',fmt(p.per_query_epsilon)],['贡献上限',fmt(p.contribution_cap)],['机制',esc(p.mechanism)],['说明',esc(p.note)]])}
<p><small>${esc(r.input_sha256?`输入SHA256 ${r.input_sha256}`:'')}</small></p>
<div class="toolbar"><button id="export">下载带噪 CSV</button><a class="button secondary" href="#channels">返回分渠道复盘 →</a></div>`;
}
export function bind(){const button=document.getElementById('export');if(button)button.onclick=async()=>{try{download(await privacy.export(store.releaseId),'privacy-release-'+store.releaseId+'.csv');}catch(e){document.getElementById('notice').textContent=e.message;}};}
