import json

from app.services import account_service as svc
from sqlalchemy import create_engine, text


def _seed(pg):
    with pg.connect() as c:
        c.execute(text("DROP TABLE IF EXISTS accounts, invitations, auth_permission_sets CASCADE"))
        c.execute(text("CREATE TABLE auth_permission_sets (id SERIAL PRIMARY KEY, name TEXT UNIQUE, "
                       "grants JSONB, builtin BOOLEAN DEFAULT FALSE, deleted_at TIMESTAMPTZ)"))
        c.execute(text("""CREATE TABLE accounts (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                       name TEXT, auth_permission_set_id INT REFERENCES auth_permission_sets(id),
                       is_super BOOLEAN DEFAULT FALSE, active BOOLEAN DEFAULT TRUE,
                       last_login_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ)"""))
        c.execute(text("""CREATE TABLE invitations (id SERIAL PRIMARY KEY, token TEXT UNIQUE,
                       email TEXT, auth_permission_set_id INT REFERENCES auth_permission_sets(id),
                       invited_by TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), expires_at TIMESTAMPTZ,
                       used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ)"""))
        c.execute(text("INSERT INTO auth_permission_sets (name, grants, builtin) "
                       "VALUES ('열람', '{\\\"routes\\\":{\\\"R\\\":true}}', TRUE) RETURNING id"))
        c.commit()


def test_invite_accept_creates_account(monkeypatch):
    from sqlalchemy import create_engine as ce
    pg = ce("postgresql+psycopg2://user:migtest@localhost:5432/migtest2")
    _seed(pg)
    monkeypatch.setattr("app.services.account_service.get_dash_engine", lambda: pg)
    inv = svc.create_invitation("new@lunchlab.me", 1, "admin@x")
    r = svc.accept_invitation(inv["token"], "new@lunchlab.me")
    assert r["ok"]
    with pg.connect() as c:
        row = c.execute(text("SELECT email, auth_permission_set_id FROM accounts WHERE email='new@lunchlab.me'")).fetchone()
        used = c.execute(text("SELECT used_at FROM invitations WHERE token=:t"),
                         {"t": inv["token"]}).scalar()
    assert row and row[1] == 1 and used is not None


def test_invite_rejects_wrong_email(monkeypatch):
    from sqlalchemy import create_engine as ce
    pg = ce("postgresql+psycopg2://user:migtest@localhost:5432/migtest2")
    _seed(pg)
    monkeypatch.setattr("app.services.account_service.get_dash_engine", lambda: pg)
    inv = svc.create_invitation("a@lunchlab.me", 1, "admin@x")
    try:
        svc.accept_invitation(inv["token"], "b@lunchlab.me")
        assert False, "다른 이메일이 수락되면 안 됨"
    except ValueError as e:
        assert "다릅니다" in str(e)


def test_builtin_set_cannot_be_modified():
    try:
        svc.save_permission_set("관리자", {}, "x@y", set_id=1)
        assert False
    except ValueError:
        pass
