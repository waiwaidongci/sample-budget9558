from sqlalchemy import Column,Integer,String,Boolean,JSON,Float,ForeignKey,UniqueConstraint
from src.config.database import Base

class Channel(Base):
    """预先登记的投放渠道。渠道必须在发布前登记，发布时整组冻结。"""
    __tablename__='channels'
    __table_args__=(UniqueConstraint('study_id','name'),)
    id=Column(Integer,primary_key=True)
    study_id=Column(Integer,ForeignKey('studies.id'),nullable=False)
    name=Column(String(80),nullable=False)
    created_at=Column(String(40),nullable=False)
    created_by=Column(String(120),nullable=False)

class AudienceTouch(Base):
    """受众级触达记录。每一位受众在一个研究内只允许一条记录：
    跨组、跨渠道的总贡献上限为1，因此每个（渠道×组别×指标）计数查询的敏感度为1。"""
    __tablename__='audience_touches'
    __table_args__=(UniqueConstraint('study_id','audience_key'),)
    id=Column(Integer,primary_key=True)
    study_id=Column(Integer,ForeignKey('studies.id'),nullable=False)
    audience_key=Column(String(120),nullable=False)
    channel=Column(String(80),nullable=False)
    group=Column('group_label',String(1),nullable=False)
    reached=Column(Boolean,nullable=False,default=False)
    clicked=Column(Boolean,nullable=False,default=False)
    created_at=Column(String(40),nullable=False)
    created_by=Column(String(120),nullable=False)

class PrivacyBudget(Base):
    """每个研究预设的隐私额度（ε）。发布时原子扣减，不可回收。"""
    __tablename__='privacy_budgets'
    study_id=Column(Integer,ForeignKey('studies.id'),primary_key=True)
    total_epsilon=Column(Float,nullable=False)
    spent_epsilon=Column(Float,nullable=False,default=0.0)
    updated_at=Column(String(40),nullable=False)

class PrivacyRelease(Base):
    """一次已发布的受众级差分隐私结果。payload 即页面与下载共用的唯一结果。
    重试（相同幂等键）直接回读该行，不重复扣额度、不重抽噪声；更正生成新版本。"""
    __tablename__='privacy_releases'
    __table_args__=(
        UniqueConstraint('study_id','version'),
        UniqueConstraint('study_id','idempotency_key'),
    )
    id=Column(Integer,primary_key=True)
    study_id=Column(Integer,ForeignKey('studies.id'),nullable=False)
    version=Column(Integer,nullable=False)
    epsilon=Column(Float,nullable=False)
    idempotency_key=Column(String(160),nullable=False)
    channels=Column(JSON,nullable=False)
    payload=Column(JSON,nullable=False)
    caveat=Column(String(600),nullable=False,default='')
    input_sha256=Column(String(64),nullable=False)
    corrects_release_id=Column(Integer,ForeignKey('privacy_releases.id'),nullable=True)
    created_at=Column(String(40),nullable=False)
    created_by=Column(String(120),nullable=False)
