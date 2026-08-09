import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

FALLBACK_HOSTS = ("host.docker.internal", "127.0.0.1", "localhost")
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000


def statement_timeout_ms() -> int:
    return int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", DEFAULT_STATEMENT_TIMEOUT_MS))


def statement_timeout_option() -> str:
    return f"-c statement_timeout={statement_timeout_ms()}"


def database_url() -> str | None:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def host_candidates() -> list[str]:
    hosts = [os.getenv("POSTGRES_HOST"), *FALLBACK_HOSTS]
    seen = set()
    ordered = []
    for host in hosts:
        if host and host not in seen:
            seen.add(host)
            ordered.append(host)
    return ordered


def connection_params(host: str) -> dict:
    return {
        "host": host,
        "port": int(os.getenv("POSTGRES_PORT", "55432")),
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "password"),
        "dbname": os.getenv("POSTGRES_DB", "loan_bank_db"),
        "connect_timeout": 5,
        "options": statement_timeout_option(),
    }


def connect(read_only: bool = True, autocommit: bool = True):
    import psycopg2

    url = database_url()
    if url:
        try:
            conn = psycopg2.connect(url, connect_timeout=5, options=statement_timeout_option())
        except psycopg2.OperationalError as exc:
            if "unsupported startup parameter" not in str(exc):
                raise
            logger.warning(
                "Connection pooler rejected startup options. Reconnecting without them and "
                "applying statement_timeout per session. Session-level read-only cannot be "
                "guaranteed through a transaction pooler - prefer the unpooled connection string."
            )
            conn = psycopg2.connect(url, connect_timeout=5)
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {statement_timeout_ms()}")
        conn.set_session(readonly=read_only, autocommit=autocommit)
        return conn

    last_error = None
    for host in host_candidates():
        try:
            conn = psycopg2.connect(**connection_params(host))
        except psycopg2.OperationalError as exc:
            last_error = exc
            continue
        conn.set_session(readonly=read_only, autocommit=autocommit)
        return conn
    raise last_error


@contextmanager
def read_only_connection():
    conn = connect(read_only=True)
    try:
        yield conn
    finally:
        conn.close()
