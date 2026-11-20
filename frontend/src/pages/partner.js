import {DOMAIN} from '../constants/domain.js';
import {privacy} from '../api/research.js';
import {table} from '../components/common/table.js';
import {esc,fmt} from '../utils/format.js';

export async function render(){
  const data=await privacy.partner();
  const rows=[];
  for(const s of data.studies) for(const r of s.releases)
    rows.push([esc(s.name),{html:`<a href="#release/${r.id}">v${r.version}</a>`},fmt(r.epsilon),r.corrects_release_id?`更正 #${r.corrects_release_id}`:'—',esc(r.created_at)]);
  return `<div class="eyebrow">PARTNER / CHANNEL REVIEW</div><h1>投放复盘 · 合作方视图</h1>
<p class="lead">这里只展示已发布的受众级差分隐私结果。所有数字均为带噪计数，不含原始受众记录。</p>
<div class="method-note">${esc(DOMAIN.privacy?.note||'')}</div>
<h2>可读发布版本</h2>
${table(['研究','版本','ε','更正自','发布时间'],rows)}`;
}
export function bind(){}
