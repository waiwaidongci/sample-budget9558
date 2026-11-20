"""HTTP 层测试：角色隔离、幂等重试、PDF/CSV 共用、合作方只能看带噪结果。"""
import os, random, pytest
os.environ.setdefault('DATABASE_URL', 'sqlite:////tmp/dp-api-test.db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('SEED_DEMO', 'false')

import src.middlewares.rate_limit as rate_limit
from fastapi.testclient import TestClient
from src.config.database import Base, engine, Session, get_db
from src.models import user, study, observation, run, review, audit, privacy as privacy_models
from src.models.study import Study
from src.models.user import User
from src.utils.security import hash_password
from src.services import privacy
from src.main import app


class FakeRedis:
    def incr(self, key): return 1
    def expire(self, key, seconds): return True
    def rpush(self, *a, **k): return 1
    def blpop(self, *a, **k): return None
    def ping(self): return True


@pytest.fixture()
def client(monkeypatch):
    rate_limit.redis = FakeRedis()
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    s = Session()
    for role in ('admin', 'analyst', 'viewer', 'partner'):
        s.add(User(email=role + '@x', role=role, password_hash=hash_password('pw123456')))
    st = Study(name='HTTP研究', source_filename='f.csv', description=''); s.add(st); s.commit()
    s.add(privacy_models.Channel(study_id=st.id, name='推送', created_at='t', created_by='seed'))
    s.add(privacy_models.Channel(study_id=st.id, name='邮件', created_at='t', created_by='seed'))
    s.commit(); study_id = st.id; s.close()
    app.dependency_overrides[get_db] = lambda: Session()
    c = TestClient(app)
    c.study_id = study_id
    yield c
    app.dependency_overrides.clear()


def headers(role):
    return {'Authorization': 'Bearer ' + __import__('src.utils.security', fromlist=['token']).token(
        type('U', (), {'id': {'admin': 1, 'analyst': 2, 'viewer': 3, 'partner': 4}[role], 'role': role})())}


def test_roles_and_publish_flow(client):
    sid = client.study_id
    admin, analyst, viewer, partner = (headers(r) for r in ('admin', 'analyst', 'viewer', 'partner'))
    for i in range(40):
        r = client.post(f'/studies/{sid}/privacy/touches', headers=analyst,
                        json={'audience_key': f'h{i}', 'channel': '推送' if i % 2 else '邮件',
                              'group': 'A' if i % 4 < 2 else 'B', 'reached': True, 'clicked': i % 8 == 0})
        assert r.status_code == 200, r.text
    # viewer 不能记账，partner 不能看原始触达
    assert client.post(f'/studies/{sid}/privacy/touches', headers=viewer,
                       json={'audience_key': 'z', 'channel': '推送', 'group': 'A', 'reached': True, 'clicked': False}).status_code == 403
    assert client.get(f'/studies/{sid}/privacy/touches', headers=partner).status_code == 403
    assert client.get('/studies', headers=partner).status_code == 403
    assert client.get('/overview', headers=partner).status_code == 403

    body = {'epsilon': 1.0, 'idempotency_key': 'http-key-00001'}
    r1 = client.post(f'/studies/{sid}/privacy/releases', headers=analyst, json=body)
    assert r1.status_code == 200, r1.text
    rid = r1.json()['id']
    assert r1.json()['version'] == 1
    # 同一幂等键重试 → 同版本、同结果
    r2 = client.post(f'/studies/{sid}/privacy/releases', headers=analyst, json=body)
    assert r2.json()['id'] == rid and r2.json()['payload'] == r1.json()['payload']
    assert client.get(f'/studies/{sid}/privacy', headers=admin).json()['budget']['spent_epsilon'] == 1.0

    # viewer 不能发布
    assert client.post(f'/studies/{sid}/privacy/releases', headers=viewer,
                       json={'epsilon': 1.0, 'idempotency_key': 'viewer-key-1234'}).status_code == 403

    # 页面与下载共用 payload
    page = client.get(f'/privacy/releases/{rid}', headers=partner)
    assert page.status_code == 200 and 'input_sha256' not in page.json()
    csv = client.get(f'/privacy/releases/{rid}/export', headers=partner)
    assert csv.status_code == 200 and csv.headers['content-type'].startswith('text/csv')
    total = page.json()['payload']['totals']['all']['reached']
    assert f'全部渠道,总计,{total}' in csv.text

    # 合作方只能看到有发布的研究
    pv = client.get('/partner/overview', headers=partner)
    assert pv.status_code == 200 and pv.json()['studies'][0]['id'] == sid
    # 合作方不能看内部总览
    assert client.get('/partner/overview', headers=admin).status_code == 403


def test_budget_exhaustion_returns_409_and_old_version_readable(client):
    sid = client.study_id
    admin, analyst, partner = headers('admin'), headers('analyst'), headers('partner')
    for i in range(10):
        client.post(f'/studies/{sid}/privacy/touches', headers=analyst,
                    json={'audience_key': f'b{i}', 'channel': '推送', 'group': 'B', 'reached': True, 'clicked': False})
    client.put(f'/studies/{sid}/privacy/budget', headers=admin, json={'total_epsilon': 0.5})
    ok = client.post(f'/studies/{sid}/privacy/releases', headers=analyst,
                     json={'epsilon': 0.5, 'idempotency_key': 'budget-key-01'})
    assert ok.status_code == 200
    rid = ok.json()['id']
    bad = client.post(f'/studies/{sid}/privacy/releases', headers=analyst,
                      json={'epsilon': 0.5, 'idempotency_key': 'budget-key-02'})
    assert bad.status_code == 409 and '额度不足' in bad.json()['detail']
    assert client.get(f'/privacy/releases/{rid}', headers=partner).status_code == 200


def test_viewer_can_read_published_only(client):
    sid = client.study_id
    analyst, viewer = headers('analyst'), headers('viewer')
    for i in range(6):
        client.post(f'/studies/{sid}/privacy/touches', headers=analyst,
                    json={'audience_key': f'v{i}', 'channel': '邮件', 'group': 'A', 'reached': True, 'clicked': i % 3 == 0})
    rel = client.post(f'/studies/{sid}/privacy/releases', headers=analyst,
                      json={'epsilon': 0.25, 'idempotency_key': 'viewer-key-01'}).json()
    got = client.get(f'/privacy/releases/{rel["id"]}', headers=viewer)
    assert got.status_code == 200 and got.json()['payload']['epsilon'] == 0.25
    assert client.get(f'/privacy/releases/{rel["id"]}/export', headers=viewer).status_code == 200
