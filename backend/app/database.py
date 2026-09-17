import os
import base64
import tempfile
import logging
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text

logger = logging.getLogger("rds")

_tunnel = None
_engine = None


def _write_ssh_key():
    b64 = os.environ.get("BASTION_SSH_KEY_B64", "")
    if not b64:
        return None
    raw = base64.b64decode(b64)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    tmp.write(raw.decode("utf-8"))
    tmp.close()
    os.chmod(tmp.name, 0o600)
    return tmp.name


def get_engine():
    global _tunnel, _engine
    if _engine is not None:
        return _engine

    key_path = _write_ssh_key()
    _tunnel = SSHTunnelForwarder(
        (os.environ["BASTION_HOST"], int(os.environ.get("BASTION_SSH_PORT", "22"))),
        ssh_username=os.environ["BASTION_USER"],
        ssh_pkey=key_path,
        remote_bind_address=(os.environ["RDS_HOST"], int(os.environ.get("RDS_PORT", "3306"))),
        set_keepalive=30,
    )
    _tunnel.start()

    url = (
        f"mysql+pymysql://{os.environ['RDS_USER']}:{os.environ['RDS_PASS']}"
        f"@127.0.0.1:{_tunnel.local_bind_port}/{os.environ['RDS_DB']}?charset=utf8mb4"
    )
    _engine = create_engine(url, pool_size=3, max_overflow=5, pool_pre_ping=True)
    logger.info("RDS engine created via SSH tunnel")
    return _engine


def rds_ok() -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:  # noqa
        logger.exception("RDS check failed")
        return False


_dash_engine = None

def get_dash_engine():
    global _dash_engine
    if _dash_engine is not None:
        return _dash_engine
    url = (
        f"postgresql+psycopg2://dash_user:{os.environ['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5433/delivery_dashboard"
    )
    _dash_engine = create_engine(url, pool_size=3, max_overflow=5, pool_pre_ping=True)
    return _dash_engine
