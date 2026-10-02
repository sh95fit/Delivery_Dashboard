from datetime import date, datetime

from app.services import day_cache as dc
from app.services.day_aggregate import KST

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=KST)


class FakeRedis:
    def __init__(self):
        self.d, self.ttl = {}, {}

    def get(self, k):
        return self.d.get(k)

    def setex(self, k, t, v):
        self.d[k], self.ttl[k] = v, t


class DownRedis:
    def get(self, k):
        raise ConnectionError("down")

    def setex(self, *a):
        raise ConnectionError("down")


def _patch(monkeypatch, client, calls):
    monkeypatch.setattr(dc, "_redis", lambda: client)
    monkeypatch.setattr(dc, "_targets_sig", lambda: "sig")
    monkeypatch.setattr(dc, "_compute", lambda t, n: calls.append(t) or {"date": t.isoformat(), "n": len(calls)})


def test_ttl():
    today = date(2026, 10, 1)
    assert dc.ttl_for(date(2026, 10, 2), today) == dc.TTL_TODAY
    assert dc.ttl_for(today, today) == dc.TTL_TODAY
    assert dc.ttl_for(date(2026, 9, 29), today) == dc.TTL_RECENT
    assert dc.ttl_for(date(2026, 9, 1), today) == dc.TTL_OLD


def test_get_day_uses_cache(monkeypatch):
    fake, calls = FakeRedis(), []
    _patch(monkeypatch, fake, calls)
    a = dc.get_day(date(2026, 9, 29), NOW)
    b = dc.get_day(date(2026, 9, 29), NOW)
    assert a == b and len(calls) == 1
    assert list(fake.ttl.values()) == [dc.TTL_RECENT]


def test_targets_change_uses_new_key(monkeypatch):
    fake, calls = FakeRedis(), []
    _patch(monkeypatch, fake, calls)
    dc.get_day(date(2026, 9, 29), NOW)
    monkeypatch.setattr(dc, "_targets_sig", lambda: "sig2")
    dc.get_day(date(2026, 9, 29), NOW)
    assert len(calls) == 2


def test_redis_down_still_works(monkeypatch):
    calls = []
    _patch(monkeypatch, DownRedis(), calls)
    assert dc.get_day(date(2026, 9, 29), NOW)["date"] == "2026-09-29"
    assert dc.get_day(date(2026, 9, 29), NOW)["date"] == "2026-09-29"
    assert len(calls) == 2
