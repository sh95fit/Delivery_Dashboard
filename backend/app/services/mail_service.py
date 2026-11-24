"""초대 메일 자동 발송 (Gmail SMTP + 앱 비밀번호). 실패해도 초대는 유지."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587


def config() -> tuple[str, str, str]:
    user = os.getenv("GMAIL_USER", "").strip()
    pw = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    url = os.getenv("APP_URL", "").strip().rstrip("/")
    return user, pw, url


def build_invite(to: str, sender: str, app_url: str, days: int) -> EmailMessage:
    m = EmailMessage()
    m["Subject"] = "[LunchLab 대시보드] 접속 초대"
    m["From"] = f"LunchLab 대시보드 <{sender}>"
    m["To"] = to
    m.set_content("\n".join([
        "안녕하세요.", "",
        "LunchLab 배송 대시보드에 초대되었습니다.", "",
        f"1. 접속 주소: {app_url or '(관리자에게 문의)'}",
        f"2. 'Google로 로그인'을 누르고 이 메일을 받은 계정({to})으로 로그인하세요.", "",
        f"초대는 {days}일 동안 유효합니다. 기간이 지나면 관리자에게 재초대를 요청해 주세요.",
    ]))
    return m


def send_invite(to: str, days: int, smtp_cls=smtplib.SMTP) -> dict:
    user, pw, url = config()
    if not user or not pw:
        return {"mail_sent": False, "mail_error": "메일 설정(GMAIL_USER/GMAIL_APP_PASSWORD)이 없습니다"}
    try:
        with smtp_cls(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(build_invite(to, user, url, days))
        return {"mail_sent": True, "mail_error": None}
    except Exception as e:  # noqa: BLE001 — 발송 실패가 초대 저장을 깨지 않게
        return {"mail_sent": False, "mail_error": f"메일 발송 실패 ({type(e).__name__})"}
