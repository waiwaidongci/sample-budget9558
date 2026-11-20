import json,random
import numpy as np
from sqlalchemy import select,func
from src.config.database import Base,engine,Session
from src.config.domain import DOMAIN
from src.models.user import User
from src.models.study import Study
from src.models.observation import Observation
from src.models.privacy import Channel,AudienceTouch,PrivacyBudget,PrivacyRelease
from src.models import run,review,audit
from src.utils.security import hash_password
from src.utils.serializers import now
from src.services import privacy

DEMO_CHANNELS=['站内信','推送','邮件']

def seed_privacy(db,study,index):
    """预登记渠道与受众触达，并发布第1版带噪结果；重复执行不产生重复数据。
    每位受众只有一条记录，因此跨组跨渠道贡献恒为1。"""
    for name in DEMO_CHANNELS:
        if not db.scalar(select(Channel.id).where(Channel.study_id==study.id,Channel.name==name)):
            db.add(Channel(study_id=study.id,name=name,created_at=now(),created_by='seed@demo.local'))
    db.flush()
    if not db.scalar(select(PrivacyBudget.study_id).where(PrivacyBudget.study_id==study.id)):
        db.add(PrivacyBudget(study_id=study.id,total_epsilon=privacy.default_total(),spent_epsilon=0.0,updated_at=now()))
    rng=np.random.default_rng(42+index)
    existing=db.scalar(select(func.count()).select_from(AudienceTouch).where(AudienceTouch.study_id==study.id))
    if not existing:
        for n in range(600):
            channel=DEMO_CHANNELS[n%len(DEMO_CHANNELS)]
            group='A' if n%2==0 else 'B'
            reached=bool(rng.random()<0.6)
            clicked=bool(reached and rng.random()<(0.05 if group=='A' else 0.07))
            db.add(AudienceTouch(study_id=study.id,audience_key=f'AUD-{index+1}-{n+1:04d}',channel=channel,
                                 group=group,reached=reached,clicked=clicked,created_at=now(),created_by='seed@demo.local'))
        db.flush()
    if not db.scalar(select(func.count()).select_from(PrivacyRelease).where(PrivacyRelease.study_id==study.id)):
        user=db.scalar(select(User).where(User.email=='analyst@demo.local'))
        privacy.publish(db,study.id,type('R',(),{'epsilon':1.0,'idempotency_key':f'seed-{index+1}-v1','corrects_release_id':None})(),
                            user,rng=random.Random(42+index))

def seed():
    Base.metadata.create_all(engine)
    rng=np.random.default_rng(42)
    i=DOMAIN['index']
    with Session() as db:
        for role in ('admin','analyst','viewer','partner'):
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)): db.add(User(email=email,role=role,password_hash=hash_password('Research2026!')))
        for k,name in enumerate(DOMAIN['names']):
            study=db.scalar(select(Study).where(Study.name==name))
            if not study:
                study=Study(name=name,source_filename=DOMAIN['slug']+f'-202611-{k+1}.csv',description='独立合成业务观测 / 固定种子42 / 仅用于方法与流程演示');db.add(study);db.flush()
            rows=[]
            if i==0:
                for n in range(120): rows.append({'moisture':round(float(np.clip(rng.normal(5.2+k*.7,.7),0,100)),3),'extract':round(float(np.clip(rng.normal(34+k*2,2.4),0,100)),3)})
            elif i==1:
                rows=[{'group':'A','success':87+k*2,'failure':13-k*2},{'group':'B','success':96-k,'failure':4+k}]
            elif i==2:
                for n in range(24):
                    b=float(rng.uniform(3,6));rows.append({'before':round(b,3),'after':round(max(.1,b+rng.normal(-.45+k*.3,.5)),3)})
            elif i==3:
                for n in range(90):
                    x=round(float(rng.uniform(4,28)),1);rows.append({'porosity':x,'absorption':round(max(0,x*(.18+k*.08)+rng.normal(0,1.5)),2)})
            else: rows=[{'p0':.08+k*.02,'p1':.1+k*.025,'cost_per_contact':.12+k*.04,'budget':3000+k*500}]
            for n,values in enumerate(rows):
                key=f'DEMO-{k+1}-{n+1:04}'
                if not db.scalar(select(Observation.id).where(Observation.study_id==study.id,Observation.source_key==key)):
                    db.add(Observation(study_id=study.id,source_key=key,values=values))
            db.flush()
            seed_privacy(db,study,k)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in (User,Study,Observation,Channel,AudienceTouch,PrivacyRelease)}
        print(json.dumps(counts));return counts
if __name__=='__main__': seed()
