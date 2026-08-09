import os
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from orchestrator.db.connection import connect, database_url, host_candidates

SPECIAL = set("@/?#[]%: ")


def describe_url(url: str) -> None:
    parsed = urlparse(url)
    password = unquote(parsed.password or "")
    print(f"  scheme   : {parsed.scheme}")
    print(f"  user     : {parsed.username}")
    print(f"  host     : {parsed.hostname}")
    print(f"  port     : {parsed.port or 5432}")
    print(f"  database : {(parsed.path or '/').lstrip('/')}")
    print(f"  query    : {parsed.query or '(none)'}")
    print(f"  password : {len(password)} chars")
    if not password:
        print("    -> EMPTY. The password is missing from the URL.")
    if "..." in url:
        print("    -> URL still contains '...'. The placeholder was not replaced.")
    risky = sorted(SPECIAL & set(password))
    if risky:
        print(f"    -> contains {risky} which must be percent-encoded in a URI")
    if "-pooler" in (parsed.hostname or ""):
        print("    -> pooled endpoint. Use the unpooled host for session-level read-only.")


def main():
    load_dotenv()
    url = database_url()

    if url:
        print("DATABASE_URL is set:")
        describe_url(url)
    else:
        print("DATABASE_URL is not set. Falling back to POSTGRES_* variables:")
        print(f"  hosts    : {host_candidates()}")
        print(f"  port     : {os.getenv('POSTGRES_PORT', '55432')}")
        print(f"  user     : {os.getenv('POSTGRES_USER', 'admin')}")
        print(f"  database : {os.getenv('POSTGRES_DB', 'loan_bank_db')}")

    print("\nConnecting...")
    try:
        with connect(read_only=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, current_database(), version()")
                user, database, version = cur.fetchone()
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
                tables = [r[0] for r in cur.fetchall()]
        print(f"  connected as {user} to {database}")
        print(f"  {version.split(',')[0]}")
        print(f"  tables: {tables or '(none - run scripts/apply_schema.py)'}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
