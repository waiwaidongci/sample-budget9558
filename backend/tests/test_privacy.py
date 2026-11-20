"""DP 发布链路的自动化测试（SQLite + FastAPI TestClient，无需 Redis/Postgres）。

运行：cd backend && DATABASE_URL=sqlite:////tmp/dp-test.db REDIS_URL=redis://localhost:6379/0 \
        JWT_SECRET=test python3 -m pytest tests/test_privacy.py -q
Redis 只用于限流/队列；发布接口本身不触碰 Redis。
"""
import os, random, pytest
os.environ.setdefault('DATABASE_URL', 'sqlite:////tmp/dp-test.db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('SEED_DEMO', 'false')

from src.config.database import Base, engine, Session
from src.models import user, study, observation, run, review, audit, privacy as privacy_models
from src.models.study import Study
from src.models.user import User
from src.models.privacy import Channel, AudienceTouch, PrivacyBudget, PrivacyRelease
from src.services import privacy
from src.utils.security import hash_password
from src.utils.serializers import now


class Who:
    def __init__(self, email, role): self.email, self.role = email, role


def rel(eps=1.0, key='idem-key-0001', corrects=None):
    return type('R', (), {'epsilon': eps, 'idempotency_key': key, 'corrects_release_id': corrects})()


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = Session()
    admin = User(email='admin@x', role='admin', password_hash='x')
    s.add(admin); s.commit()
    yield s
    s.close()


def make_study(db, name='S'):
    st = Study(name=name, source_filename='f.csv', description='')
    db.add(st); db.commit()
    return st


def seed_touches(db, study_id, n=200, admin=None):
    admin = admin or Who('admin@x', 'admin')
    for ch in ('站内信', '推送'):
        privacy.register_channel(db, study_id, ch, admin)
    for i in range(n):
        ch = '站内信' if i % 2 else '推送'
        g = 'A' if i % 4 < 2 else 'B'
        d = type('T', (), {'audience_key': f'x{i}', 'channel': ch, 'group': g,
                           'reached': True, 'clicked': i % 10 == 0})()
        privacy.save_touch(db, study_id, d, admin)


def test_contributions_are_capped_to_one_per_audience(db):
    st = make_study(db)
    seed_touches(db, st.id, 50)
    keys = [t.audience_key for t in db.query(AudienceTouch).filter_by(study_id=st.id)]
    assert len(keys) == len(set(keys)) == 50           # 每位受众仅一条记录 → 贡献=1
    # 更新同一受众的其他渠道/组别不会新增行，仍是覆盖
    d = type('T', (), {'audience_key': 'x0', 'channel': '站内信', 'group': 'B',
                       'reached': True, 'clicked': False})()
    privacy.save_touch(db, st.id, d, Who('admin@x', 'admin'))
    assert db.query(AudienceTouch).filter_by(study_id=st.id).count() == 50


def test_channel_counts_sum_to_totals(db):
    st = make_study(db)
    seed_touches(db, st.id, 200)
    r = privacy.publish(db, st.id, rel(), Who('a', 'analyst'), rng=random.Random(7))
    p = r['payload']
    for ch in p['channels']:
        for m in ('reached', 'clicked'):
            assert ch['total'][m] == ch['groups']['A'][m] + ch['groups']['B'][m]
    for m in ('reached', 'clicked'):
        assert p['totals']['all'][m] == sum(c['total'][m] for c in p['channels'])
        assert p['totals']['all'][m] == p['totals']['A'][m] + p['totals']['B'][m]


def test_epsilon_per_query_and_counts_are_integers(db):
    st = make_study(db)
    seed_touches(db, st.id, 40)
    r = privacy.publish(db, st.id, rel(eps=2.0), Who('a', 'analyst'), rng=random.Random(3))
    p = r['payload']
    assert p['query_count'] == 2 * 2 * 2
    assert abs(p['per_query_epsilon'] - 2.0 / 8) < 1e-9
    for ch in p['channels']:
        for g in ('A', 'B'):
            x = ch['groups'][g]
            assert isinstance(x['reached'], int) and isinstance(x['clicked'], int)
            assert 0 <= x['clicked'] <= x['reached']


def test_retry_same_key_is_idempotent(db):
    st = make_study(db)
    seed_touches(db, st.id, 30)
    w = Who('a', 'analyst')
    r1 = privacy.publish(db, st.id, rel(key='same-key-1234567'), w, rng=random.Random(1))
    first = r1['payload']
    r2 = privacy.publish(db, st.id, rel(key='same-key-1234567'), w, rng=random.Random(999))
    assert r2['id'] == r1['id'] and r2['version'] == 1
    assert r2['payload'] == first                       # 不重抽噪声
    b = privacy.budget_view(db.get(PrivacyBudget, st.id))
    assert b['spent_epsilon'] == 1.0                    # 不重复扣额度
    assert db.query(PrivacyRelease).filter_by(study_id=st.id).count() == 1


def test_correction_creates_new_version(db):
    st = make_study(db)
    seed_touches(db, st.id, 30)
    w = Who('a', 'analyst')
    r1 = privacy.publish(db, st.id, rel(key='key-aaaaaaaa'), w, rng=random.Random(1))
    r2 = privacy.publish(db, st.id, rel(key='key-bbbbbbbb', corrects=r1['id']), w, rng=random.Random(2))
    assert r2['version'] == 2 and r2['corrects_release_id'] == r1['id']
    assert r2['id'] != r1['id']
    assert privacy.budget_view(db.get(PrivacyBudget, st.id))['spent_epsilon'] == 2.0


def test_budget_exhaustion_blocks_new_release_but_old_version_readable(db):
    st = make_study(db)
    seed_touches(db, st.id, 30)
    admin = Who('admin@x', 'admin')
    privacy.set_total_budget(db, st.id, 1.0, admin)
    r1 = privacy.publish(db, st.id, rel(eps=1.0, key='key-11111111'), Who('a', 'analyst'), rng=random.Random(1))
    with pytest.raises(Exception) as e:
        privacy.publish(db, st.id, rel(eps=1.0, key='key-22222222'), Who('a', 'analyst'), rng=random.Random(2))
    assert '额度不足' in str(getattr(e.value, 'detail', e.value))
    assert privacy.get(db, r1['id'], 'admin')['payload'] == r1['payload']
    assert privacy.get(db, r1['id'], 'partner')['payload'] == r1['payload']
    assert privacy.budget_view(db.get(PrivacyBudget, st.id))['spent_epsilon'] == 1.0


def test_export_matches_page_payload_without_extra_spend(db):
    st = make_study(db)
    seed_touches(db, st.id, 30)
    w = Who('a', 'analyst')
    r = privacy.publish(db, st.id, rel(), w, rng=random.Random(5))
    before = privacy.budget_view(db.get(PrivacyBudget, st.id))
    csv1 = privacy.export(db, r['id'], 'admin', w)
    csv2 = privacy.export(db, r['id'], 'partner', w)
    assert csv1 == csv2
    assert privacy.budget_view(db.get(PrivacyBudget, st.id)) == before
    page = privacy.get(db, r['id'], 'admin')['payload']
    for ch in page['channels']:
        assert str(ch['total']['reached']) in csv1


def test_partner_view_hides_internal_fields(db):
    st = make_study(db)
    seed_touches(db, st.id, 10)
    r = privacy.publish(db, st.id, rel(), Who('a', 'analyst'), rng=random.Random(4))
    partner = privacy.get(db, r['id'], 'partner')
    assert 'input_sha256' not in partner and 'idempotency_key' not in partner
    assert privacy.get(db, r['id'], 'admin')['input_sha256']


def test_touch_requires_registered_channel(db):
    st = make_study(db)
    with pytest.raises(Exception) as e:
        privacy.save_touch(db, st.id, type('T', (), {'audience_key': 'a1', 'channel': '未登记',
                                                     'group': 'A', 'reached': True, 'clicked': False})(), Who('a', 'analyst'))
    assert '必须先登记' in str(getattr(e.value, 'detail', e.value))


def test_click_requires_reached(db):
    st = make_study(db)
    privacy.register_channel(db, st.id, '推送', Who('a', 'analyst'))
    with pytest.raises(Exception) as e:
        privacy.save_touch(db, st.id, type('T', (), {'audience_key': 'a1', 'channel': '推送',
                                                     'group': 'A', 'reached': False, 'clicked': True})(), Who('a', 'analyst'))
    assert '点击必须同时触达' in str(getattr(e.value, 'detail', e.value))


def test_atomic_guard_blocks_double_spend_without_new_release(db):
    from sqlalchemy import update
    st = make_study(db)
    seed_touches(db, st.id, 10)
    privacy.set_total_budget(db, st.id, 1.0, Who('admin@x', 'admin'))
    privacy.publish(db, st.id, rel(eps=1.0, key='guard-key-0001'), Who('a', 'analyst'), rng=random.Random(1))
    # 第二笔扣减必须 rowcount=0，额度不再变化
    res = db.execute(update(PrivacyBudget)
                     .where(PrivacyBudget.study_id == st.id,
                            PrivacyBudget.spent_epsilon + 0.25 <= PrivacyBudget.total_epsilon + 1e-9)
                     .values(spent_epsilon=PrivacyBudget.spent_epsilon + 0.25))
    db.commit()
    assert res.rowcount == 0
    assert privacy.budget_view(db.get(PrivacyBudget, st.id))['spent_epsilon'] == 1.0


def test_release_write_failure_rolls_back_spend(db):
    st = make_study(db)
    seed_touches(db, st.id, 10)
    privacy.set_total_budget(db, st.id, 4.0, Who('admin@x', 'admin'))   # 已提交的额度行
    w = Who('a', 'analyst')
    original = privacy._noisy_payload
    privacy._noisy_payload = lambda *a, **k: {'bad': {1, 2, 3}}   # 无法序列化
    try:
        with pytest.raises(Exception):
            privacy.publish(db, st.id, rel(eps=1.0, key='fail-key-0001'), w, rng=random.Random(1))
    finally:
        privacy._noisy_payload = original
        db.rollback()
    b = privacy.budget_view(db.get(PrivacyBudget, st.id))
    assert b['spent_epsilon'] == 0.0                                  # 扣额与结果同生共死
    assert db.query(PrivacyRelease).filter_by(study_id=st.id).count() == 0


def test_same_idempotency_key_with_different_request_is_rejected(db):
    st = make_study(db)
    seed_touches(db, st.id, 10)
    w = Who('a', 'analyst')
    privacy.publish(db, st.id, rel(eps=1.0, key='intent-key-001'), w, rng=random.Random(1))
    with pytest.raises(Exception) as e:
        privacy.publish(db, st.id, rel(eps=0.5, key='intent-key-001'), w, rng=random.Random(2))
    assert '幂等键已用于不同' in str(getattr(e.value, 'detail', e.value))
    assert privacy.budget_view(db.get(PrivacyBudget, st.id))['spent_epsilon'] == 1.0
