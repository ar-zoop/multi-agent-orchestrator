import os
from contextlib import contextmanager

FALLBACK_HOSTS = ("host.docker.internal", "127.0.0.1", "localhost")
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000


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
    timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", DEFAULT_STATEMENT_TIMEOUT_MS))
    return {
        "host": host,
        "port": int(os.getenv("POSTGRES_PORT", "55432")),
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "password"),
        "dbname": os.getenv("POSTGRES_DB", "loan_bank_db"),
        "connect_timeout": 5,
        "options": f"-c statement_timeout={timeout_ms}",
    }


def connect(read_only: bool = True):
    import psycopg2

    last_error = None
    for host in host_candidates():
        try:
            conn = psycopg2.connect(**connection_params(host))
        except psycopg2.OperationalError as exc:
            last_error = exc
            continue
        conn.set_session(readonly=read_only, autocommit=True)
        return conn
    raise last_error


@contextmanager
def read_only_connection():
    conn = connect(read_only=True)
    try:
        yield conn
    finally:
        conn.close()
