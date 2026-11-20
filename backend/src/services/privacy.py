import math,random
from fastapi import HTTPException
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError
from src.config.domain import DOMAIN
from src.models.privacy import Channel,AudienceTouch,PrivacyBudget,PrivacyRelease
from src.services import studies
from src.services.audits import log
from src.utils.serializers import now,record,checksum

GROUPS=('A','B');METRICS=('reached','clicked')
MAX_RELEASE_EPSILON=10.0

def default_total():
    return float(DOMAIN.get('privacy',{}).get('default_budget',4.0))

def _release_note():
    return DOMAIN.get('privacy',{}).get(
        'note',
        '每位受众跨组跨渠道的总贡献上限为1；每个（渠道×组别×触达/点击）计数独立加噪，单次发布ε平均分配；总计由分渠道带噪计数相加得到。')

def budget(db,study_id,create=True):
    studies.require(db,study_id)
    b=db.get(PrivacyBudget,study_id)
    if not b and create:
        b=PrivacyBudget(study_id=study_id,total_epsilon=default_total(),spent_epsilon=0.0,updated_at=now())
        db.add(b);db.flush()
    return b

def budget_view_for(db,study_id):
    """只读视图：尚未发布过的研究也显示预设额度，但不会因读取而写入。"""
    studies.require(db,study_id)
    b=db.get(PrivacyBudget,study_id)
    if b: return budget_view(b)
    return {'total_epsilon':default_total(),'spent_epsilon':0.0,'remaining_epsilon':default_total(),'updated_at':None}

def set_total_budget(db,study_id,value,user):
    if not 0<value<=100: raise HTTPException(422,'研究额度必须在0到100之间')
    b=budget(db,study_id)
    if value+1e-9<b.spent_epsilon: raise HTTPException(422,'新额度不能低于已用额度')
    b.total_epsilon=float(value);b.updated_at=now()
    log(db,user,'privacy.budget.set',f'{study_id}: {value}');db.commit()
    return budget_view(b)

def budget_view(b):
    if not b: return None
    remaining=max(0.0,round(b.total_epsilon-b.spent_epsilon,6))
    return {'total_epsilon':b.total_epsilon,'spent_epsilon':round(b.spent_epsilon,6),'remaining_epsilon':remaining,'updated_at':b.updated_at}

# ---------- 预登记渠道与受众触达 ----------
def list_channels(db,study_id):
    studies.require(db,study_id)
    return [record(c) for c in db.scalars(select(Channel).where(Channel.study_id==study_id).order_by(Channel.id))]

def register_channel(db,study_id,name,user):
    studies.require(db,study_id)
    name=(name or '').strip()
    if not 1<=len(name)<=80: raise HTTPException(422,'渠道名称长度必须为1到80')
    if db.scalar(select(Channel).where(Channel.study_id==study_id,Channel.name==name)):
        raise HTTPException(409,'渠道已登记')
    c=Channel(study_id=study_id,name=name,created_at=now(),created_by=user.email);db.add(c)
    log(db,user,'privacy.channel.register',f'{study_id}/{name}');db.commit();return record(c)

def remove_channel(db,study_id,channel_id,user):
    c=db.get(Channel,channel_id)
    if not c or c.study_id!=study_id: raise HTTPException(404,'渠道不存在')
    if db.scalar(select(func.count()).select_from(AudienceTouch).where(AudienceTouch.study_id==study_id,AudienceTouch.channel==c.name)):
        raise HTTPException(409,'该渠道已有受众触达记录，不能删除')
    db.delete(c);log(db,user,'privacy.channel.remove',f'{study_id}/{c.name}');db.commit();return {'deleted':True}

def touch_count(db,study_id):
    studies.require(db,study_id)
    return int(db.scalar(select(func.count()).select_from(AudienceTouch).where(AudienceTouch.study_id==study_id)) or 0)

def list_touches(db,study_id):
    studies.require(db,study_id)
    return [record(x) for x in db.scalars(select(AudienceTouch).where(AudienceTouch.study_id==study_id).order_by(AudienceTouch.id))]

def _validate_touch(db,study_id,data):
    key=(data.audience_key or '').strip()
    if not 1<=len(key)<=120: raise HTTPException(422,'受众标识长度必须为1到120')
    channel=(data.channel or '').strip()
    if not db.scalar(select(Channel.id).where(Channel.study_id==study_id,Channel.name==channel)):
        raise HTTPException(422,'渠道必须先登记：'+channel)
    if data.group not in GROUPS: raise HTTPException(422,'组别必须为A或B')
    if data.clicked and not data.reached: raise HTTPException(422,'点击必须同时触达')
    return key,channel

def save_touch(db,study_id,data,user):
    studies.require(db,study_id)
    key,channel=_validate_touch(db,study_id,data)
    row=db.scalar(select(AudienceTouch).where(AudienceTouch.study_id==study_id,AudienceTouch.audience_key==key))
    if row:
        row.channel=channel;row.group=data.group;row.reached=bool(data.reached);row.clicked=bool(data.clicked)
    else:
        if db.scalar(select(func.count()).select_from(AudienceTouch).where(AudienceTouch.study_id==study_id))>=20000:
            raise HTTPException(422,'单个研究最多20000位受众')
        row=AudienceTouch(study_id=study_id,audience_key=key,channel=channel,group=data.group,
                          reached=bool(data.reached),clicked=bool(data.clicked),created_at=now(),created_by=user.email)
        db.add(row)
    log(db,user,'privacy.touch.save',f'{study_id}/{key}');db.commit();return record(row)

def remove_touch(db,study_id,touch_id,user):
    row=db.get(AudienceTouch,touch_id)
    if not row or row.study_id!=study_id: raise HTTPException(404,'受众触达记录不存在')
    db.delete(row);log(db,user,'privacy.touch.remove',touch_id);db.commit();return {'deleted':True}

# ---------- 差分隐私发布 ----------
def laplace(scale,rng):
    """Laplace(0, scale) 逆CDF采样；rng 需提供 random()。"""
    u=rng.random();t=max(min(u,1.0-u),1e-300)
    x=-scale*math.log(2.0*t)
    return x if u>=0.5 else -x

def _input_hash(rows):
    return checksum([{'audience_key':r.audience_key,'channel':r.channel,'group':r.group,
                      'reached':bool(r.reached),'clicked':bool(r.clicked)} for r in rows])

def _tally(rows,channels):
    cells={(ch,g,m):0 for ch in channels for g in GROUPS for m in METRICS}
    for r in rows:
        if r.channel not in channels: continue
        if r.reached: cells[(r.channel,r.group,'reached')]+=1
        if r.clicked: cells[(r.channel,r.group,'clicked')]+=1
    return cells

def _ctr(clicked,reached):
    return round(clicked/reached,6) if reached>0 else None

def _noisy_payload(rows,channels,epsilon,rng):
    """每个渠道×组别×指标独立加噪，ε在 4×渠道数 个子查询间均分。
    渠道计数先截断取整，再逐层相加得到组别总计与总计，保证“分渠道相加即总计”。"""
    if epsilon<=0 or epsilon>MAX_RELEASE_EPSILON: raise HTTPException(422,'单次发布ε必须在0到10之间')
    q=len(channels)*len(GROUPS)*len(METRICS)
    per_query=epsilon/q;scale=1.0/per_query
    cells=_tally(rows,channels)
    channel_blocks=[];group_totals={g:{m:0 for m in METRICS} for g in GROUPS}
    for ch in channels:
        groups={}
        for g in GROUPS:
            reached=max(0,int(round(cells[(ch,g,'reached')]+laplace(scale,rng))))
            clicked=max(0,int(round(cells[(ch,g,'clicked')]+laplace(scale,rng))))
            clicked=min(clicked,reached)          # 后处理：点击不超过触达，保持DP有效
            groups[g]={'reached':reached,'clicked':clicked,'ctr':_ctr(clicked,reached)}
            group_totals[g]['reached']+=reached;group_totals[g]['clicked']+=clicked
        subtotal={m:groups['A'][m]+groups['B'][m] for m in METRICS}
        subtotal['ctr']=_ctr(subtotal['clicked'],subtotal['reached'])
        channel_blocks.append({'channel':ch,'groups':groups,'total':subtotal})
    for g in GROUPS: group_totals[g]['ctr']=_ctr(group_totals[g]['clicked'],group_totals[g]['reached'])
    overall={m:group_totals['A'][m]+group_totals['B'][m] for m in METRICS}
    overall['ctr']=_ctr(overall['clicked'],overall['reached'])
    return {
        'epsilon':epsilon,'per_query_epsilon':round(per_query,10),'query_count':q,
        'mechanism':'Laplace 机制（纯差分隐私）；每个（渠道×组别×触达/点击）计数独立加噪，ε均分',
        'contribution_cap':1,
        'channels':channel_blocks,
        'totals':{'A':group_totals['A'],'B':group_totals['B'],'all':overall},
        'note':_release_note(),
    }

def _partner_view(rel):
    return {'id':rel.id,'study_id':rel.study_id,'version':rel.version,'epsilon':rel.epsilon,
            'channels':rel.channels,'payload':rel.payload,'created_at':rel.created_at}

def _internal_view(rel):
    x=_partner_view(rel);x.update({'input_sha256':rel.input_sha256,'idempotency_key':rel.idempotency_key,
                                    'corrects_release_id':rel.corrects_release_id,'created_by':rel.created_by})
    return x

def view(rel,role):
    return _partner_view(rel) if role=='partner' else _internal_view(rel)

def list_releases(db,study_id,role):
    studies.require(db,study_id)
    rows=db.scalars(select(PrivacyRelease).where(PrivacyRelease.study_id==study_id).order_by(PrivacyRelease.version.desc()))
    if role=='partner':
        return [{'id':r.id,'study_id':r.study_id,'version':r.version,'epsilon':r.epsilon,
                 'channels':r.channels,'created_at':r.created_at,'corrects_release_id':r.corrects_release_id} for r in rows]
    return [_internal_view(r) for r in rows]

def get(db,release_id,role):
    rel=db.get(PrivacyRelease,release_id)
    if not rel: raise HTTPException(404,'发布记录不存在')
    return view(rel,role)

def publish(db,study_id,data,user,rng=None):
    studies.require(db,study_id)
    budget(db,study_id)                                  # 首次发布前落实预设额度
    rng=rng or random.SystemRandom()
    key=(data.idempotency_key or '').strip()
    if not 8<=len(key)<=160: raise HTTPException(422,'幂等键长度必须为8到160')
    epsilon=round(float(data.epsilon),6)
    if not 0<epsilon<=MAX_RELEASE_EPSILON: raise HTTPException(422,'单次发布ε必须在0到10之间')

    existing=db.scalar(select(PrivacyRelease).where(PrivacyRelease.study_id==study_id,
                                                   PrivacyRelease.idempotency_key==key))
    if existing:
        # 幂等键绑定“请求意图”（ε与被更正版本）。命中即原样回读，即使之后又补录了受众：
        # 重试不重抽噪声、不重复扣额度；要用新数据请换新键或走更正。
        same_request=(existing.epsilon==epsilon
                      and existing.corrects_release_id==data.corrects_release_id)
        if not same_request:
            raise HTTPException(409,'幂等键已用于不同的发布请求；如需按新的 ε 或更正目标发布，请更换幂等键')
        log(db,user,'privacy.release.reuse',f'{study_id}/{key}');db.commit()
        return view(existing,user.role)

    channels=[c.name for c in db.scalars(select(Channel).where(Channel.study_id==study_id).order_by(Channel.id))]
    if not channels: raise HTTPException(422,'先登记至少一个渠道再发布')
    if data.corrects_release_id:
        old=db.get(PrivacyRelease,data.corrects_release_id)
        if not old or old.study_id!=study_id: raise HTTPException(422,'被更正的发布记录不存在')

    rows=list(db.scalars(select(AudienceTouch).where(AudienceTouch.study_id==study_id).order_by(AudienceTouch.id)))
    payload=_noisy_payload(rows,channels,epsilon,rng)
    input_hash=_input_hash(rows)

    for _attempt in range(4):
        # 原子扣减：只有剩余额度足够时这一行才会更新；与结果写入同一事务。
        stmt=(update(PrivacyBudget)
              .where(PrivacyBudget.study_id==study_id,
                     PrivacyBudget.spent_epsilon+epsilon<=PrivacyBudget.total_epsilon+1e-9)
              .values(spent_epsilon=PrivacyBudget.spent_epsilon+epsilon,updated_at=now()))
        try:
            res=db.execute(stmt)
            if res.rowcount!=1:
                db.rollback()
                remaining=budget_view_for(db,study_id)['remaining_epsilon']
                raise HTTPException(409,f'隐私额度不足：剩余 {remaining}，本次需要 {epsilon}；可读取既有版本')
            last=db.scalar(select(func.max(PrivacyRelease.version)).where(PrivacyRelease.study_id==study_id)) or 0
            version=last+1
            stored={**payload,'version':version}
            rel=PrivacyRelease(study_id=study_id,version=version,epsilon=epsilon,idempotency_key=key,
                               channels=channels,payload=stored,caveat=_release_note(),input_sha256=input_hash,
                               corrects_release_id=data.corrects_release_id,created_at=now(),created_by=user.email)
            db.add(rel);db.flush()
            log(db,user,'privacy.release.publish',f'{study_id} v{version} ε={epsilon}');db.commit()
            return view(rel,user.role)
        except IntegrityError:
            db.rollback()
            existing=db.scalar(select(PrivacyRelease).where(PrivacyRelease.study_id==study_id,
                                                           PrivacyRelease.idempotency_key==key))
            if existing: return view(existing,user.role)
            continue
    raise HTTPException(409,'并发发布冲突，请重试')

# ---------- 下载（与页面共用同一 payload，不重抽噪声、不扣额度） ----------
import csv,io
def export(db,release_id,role,user):
    rel=db.get(PrivacyRelease,release_id)
    if not rel: raise HTTPException(404,'发布记录不存在')
    p=rel.payload;stream=io.StringIO();w=csv.writer(stream)
    w.writerow([f'研究编号 {rel.study_id} · 第 {rel.version} 版 · ε={rel.epsilon} · 受众级差分隐私（带噪计数，非真实业务计数）'])
    w.writerow(['渠道','组别','触达 (带噪)','点击 (带噪)','点击率 (带噪)'])
    for block in p['channels']:
        for g in GROUPS:
            x=block['groups'][g];w.writerow([block['channel'],g,x['reached'],x['clicked'],'' if x['ctr'] is None else x['ctr']])
        t=block['total'];w.writerow([block['channel'],'小计',t['reached'],t['clicked'],'' if t['ctr'] is None else t['ctr']])
    for g in GROUPS:
        x=p['totals'][g];w.writerow(['全部渠道',g,x['reached'],x['clicked'],'' if x['ctr'] is None else x['ctr']])
    a=p['totals']['all'];w.writerow(['全部渠道','总计',a['reached'],a['clicked'],'' if a['ctr'] is None else a['ctr']])
    w.writerow([]);w.writerow(['机制',p['mechanism']]);w.writerow(['单查询ε',p['per_query_epsilon']]);w.writerow(['子查询数',p['query_count']])
    w.writerow(['注意',p['note']])
    log(db,user,'privacy.release.export',release_id);db.commit()
    return '﻿'+stream.getvalue()
