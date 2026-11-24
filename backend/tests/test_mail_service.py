from app.services import mail_service as m


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.logged = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        if FakeSMTP.fail:
            raise OSError("boom")
        self.logged = (u, p)

    def send_message(self, msg):
        FakeSMTP.sent.append((self.logged, msg))


def _env(monkeypatch, pw="abcd efgh ijkl mnop"):
    monkeypatch.setenv("GMAIL_USER", "admin@lunchlab.me")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", pw)
    monkeypatch.setenv("APP_URL", "https://dash.example.com/")
    FakeSMTP.sent, FakeSMTP.fail = [], False


def test_config_strips_spaces_and_slash(monkeypatch):
    _env(monkeypatch)
    assert m.config() == ("admin@lunchlab.me", "abcdefghijklmnop", "https://dash.example.com")


def test_build_invite_contents():
    msg = m.build_invite("kim@x.com", "admin@lunchlab.me", "https://d.com", 7)
    body = msg.get_content()
    assert msg["To"] == "kim@x.com" and "admin@lunchlab.me" in msg["From"]
    assert "https://d.com" in body and "7일" in body and "kim@x.com" in body


def test_send_ok(monkeypatch):
    _env(monkeypatch)
    r = m.send_invite("kim@x.com", 7, smtp_cls=FakeSMTP)
    assert r == {"mail_sent": True, "mail_error": None}
    logged, msg = FakeSMTP.sent[0]
    assert logged == ("admin@lunchlab.me", "abcdefghijklmnop")
    assert msg["To"] == "kim@x.com"


def test_send_failure_returns_false(monkeypatch):
    _env(monkeypatch)
    FakeSMTP.fail = True
    r = m.send_invite("kim@x.com", 7, smtp_cls=FakeSMTP)
    assert r["mail_sent"] is False and "OSError" in r["mail_error"]


def test_send_without_config(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    r = m.send_invite("kim@x.com", 7, smtp_cls=FakeSMTP)
    assert r["mail_sent"] is False
