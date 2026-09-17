import os
import secrets
from itsdangerous import URLSafeTimedSerializer

SALT = "lunchlab"

def make_session_token() -> str:
    return secrets.token_urlsafe(32)

def serialize_session(email: str) -> str:
    s = URLSafeTimedSerializer(os.environ["APP_SECRET"], salt=SALT)
    return s.dumps({"email": email})

def deserialize_session(token: str) -> str | None:
    s = URLSafeTimedSerializer(os.environ["APP_SECRET"], salt=SALT)
    try:
        data = s.loads(token, max_age=60 * 60 * 24 * 7)  # 7일
        return data.get("email")
    except Exception:
        return None
