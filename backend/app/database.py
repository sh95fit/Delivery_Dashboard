import os
import base64
import tempfile
import logging
import threading

from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

logger = logging.getLogger("rds")

_tunnel = None
_engine = None
_dash_engine = None
_tunnel_lock = threading.Lock()


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


def _start_tunnel():
    global _tunnel
    key_path = _write_ssh_key()
    tunnel = SSHTunnelForwarder(
        (os.environ["BASTION_HOST"], int(os.environ.get("BASTION_SSH_PORT", "22"))),
        ssh_username=os.environ["BASTION_USER"],
        ssh_pkey=key_path,
        remote_bind_address=(os.environ["RDS_HOST"], int(os.environ.get("RDS_PORT", "3306"))),
        set_keepalive=10.0,          # 30 → 10초로 단축 (끊김 조기 감지)
    )
    tunnel.start()
    _tunnel = tunnel
    logger.info("SSH tunnel started, local port=%s", tunnel.local_bind_port)
    return tunnel


def _get_tunnel():
    """터널이 살아있는지 확인하고, 죽었으면 재시작 (스레드 세이프)."""
    global _tunnel
    with _tunnel_lock:
        if _tunnel is None or not _tunnel.is_active or not _tunnel.local_bind_port:
            try:
                if _tunnel is not None:
                    try:
                        _tunnel.stop()
                    except Exception:
                        pass
            except Exception:
                pass
            logger.warning("SSH tunnel dead — restarting")
            _start_tunnel()
        return _tunnel


def get_engine():
    """AWS RDS(MySQL 8.0) — 터널 자동 복구 포함, 읽기 전용."""
    global _engine
    if _engine is not None:
        return _engine

    tunnel = _get_tunnel()
    url = (
        f"mysql+pymysql://{os.environ['RDS_USER']}:{os.environ['RDS_PASS']}"
        f"@127.0.0.1:{tunnel.local_bind_port}/{os.environ['RDS_DB']}?charset=utf8mb4"
    )
    _engine = create_engine(
        url,
        pool_size=3,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 10,
            "read_timeout": 30,
            "write_timeout": 30,
        },
    )
    logger.info("RDS engine created via SSH tunnel")
    return _engine


def get_dash_engine():
    """대시보드 전용 PostgreSQL(dash_db)."""
    global _dash_engine
    if _dash_engine is not None:
        return _dash_engine
    url = URL.create(
        "postgresql+psycopg2",
        username="dash_user",
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        host="db",
        port=5432,
        database="delivery_dashboard",
    )
    _dash_engine = create_engine(url, pool_size=3, max_overflow=5, pool_pre_ping=True)
    return _dash_engine


def rds_ok() -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("RDS check failed")
        # 터널 재시작 유도 (다음 호출에서 새 터널)
        global _tunnel, _engine
        try:
            with _tunnel_lock:
                if _tunnel is not None:
                    try:
                        _tunnel.stop()
                    except Exception:
                        pass
                _tunnel = None
                _engine = None   # 엔진도 재생성 (포트가 바뀔 수 있음)
        except Exception:
            pass
        return False
