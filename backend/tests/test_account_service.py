"""P11-b 계정·초대 서비스 테스트 — DB 없이 순수 로직만 검증 (CI 안전).

DB 의존 동작(수락 시 계정 생성 등)은 배포 후 서버 검증 스크립트로 확인합니다 —
P11-b 가이드 8장의 서버 검증이 그 역할입니다.
"""
import datetime

from app.services import account_service as svc
from datetime import datetime


def _inv_row(email="a@lunchlab.me", expires_in=1, used_at=None, revoked_at=None):
    """invitations 행 모양(dict) — accept_invitation이 읽는 칸만."""
    tz = datetime.timezone.utc
    return {"id": 1, "email": email,
            "auth_permission_set_id": 1,
            "expires_at": datetime.datetime.now(tz) + datetime.timedelta(hours=expires_in),
            "used_at": used_at, "revoked_at": revoked_at}


class _FakeResult:
    def __init__(self, value): self._v = value
    def scalar(self): return self._v
    def mappings(self): return self
    def fetchone(self): return self._v


class _FakeConn:
    """accept_invitation의 with get_dash_engine().begin() conn 최소 모조."""
    def __init__(self, rows):
        self._rows = list(rows); self._i = 0
        self.executed = []
    def execute(self, q, params=None):
        self.executed.append((str(q)[:40], params))
        r = _FakeResult(self._rows[self._i] if self._i < len(self._rows) else None)
        self._i += 1
        return r
    def begin(self): return self
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_accept_rejects_used_invitation(monkeypatch):
    row = _inv_row(used_at=datetime.datetime.now(datetime.timezone.utc))
    monkeypatch.setattr(svc, "get_dash_engine", lambda: _FakeConn([row]))
    try:
        svc.accept_invitation("tok", "a@lunchlab.me")
        assert False, "사용된 초대가 수락되면 안 됨"
    except ValueError as e:
        assert "사용·만료·취소" in str(e)


def test_accept_rejects_expired_invitation(monkeypatch):
    row = _inv_row(expires_in=-1)
    monkeypatch.setattr(svc, "get_dash_engine", lambda: _FakeConn([row]))
    try:
        svc.accept_invitation("tok", "a@lunchlab.me")
        assert False, "만료된 초대가 수락되면 안 됨"
    except ValueError as e:
        assert "사용·만료·취소" in str(e)


def test_accept_rejects_revoked_invitation(monkeypatch):
    row = _inv_row(revoked_at=datetime.datetime.now(datetime.timezone.utc))
    monkeypatch.setattr(svc, "get_dash_engine", lambda: _FakeConn([row]))
    try:
        svc.accept_invitation("tok", "a@lunchlab.me")
        assert False, "취소된 초대가 수락되면 안 됨"
    except ValueError as e:
        assert "사용·만료·취소" in str(e)


def test_accept_rejects_email_mismatch(monkeypatch):
    row = _inv_row(email="a@lunchlab.me")
    conn = _FakeConn([row, None, None, None])
    monkeypatch.setattr(svc, "get_dash_engine", lambda: conn)
    try:
        svc.accept_invitation("tok", "b@lunchlab.me")
        assert False, "다른 이메일이 수락되면 안 됨"
    except ValueError as e:
        assert "다릅니다" in str(e)


def test_accept_success_flow(monkeypatch):
    row = _inv_row(email="a@lunchlab.me")
    conn = _FakeConn([row, 1, 1, 1])
    monkeypatch.setattr(svc, "get_dash_engine", lambda: conn)
    calls = []
    monkeypatch.setattr("app.services.permission_service.invalidate",
                        lambda e=None: calls.append(e))
    r = svc.accept_invitation("tok", "a@lunchlab.me")
    assert r["ok"]
    assert "a@lunchlab.me" in calls           # 수락 후 캐시 무효화 확인
    sql_all = " | ".join(s for s, _ in conn.executed)
    assert "accounts" in sql_all and "used_at = NOW()" in sql_all
