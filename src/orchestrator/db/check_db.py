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
        print("    -> POOLED endpoint. Delete '-pooler' from the host to get:")
        print(f"       {(parsed.hostname or '').replace('-pooler', '')}")


def main():
    from_shell = "DATABASE_URL" in os.environ or "POSTGRES_URL" in os.environ
    load_dotenv()
    url = database_url()

    if url:
        source = "the shell environment" if from_shell else "the .env file"
        print(f"DATABASE_URL is set, read from {source}:")
        if from_shell:
            print("  NOTE: a shell variable overrides .env. Clear it with "
                  "'Remove-Item Env:DATABASE_URL' or open a new terminal.")
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
                counts = {}
                for table in tables:
                    cur.execute(f'SELECT count(*) FROM "{table}"')
                    counts[table] = cur.fetchone()[0]
        print(f"  connected as {user} to {database}")
        print(f"  {version.split(',')[0]}")
        if not tables:
            print("  tables: (none - run scripts/apply_schema.py)")
        else:
            for table, count in counts.items():
                print(f"  {table:<12} {count:>7} rows")
            if not any(counts.values()):
                print("  -> schema exists but is empty. Run: uv run python -m orchestrator.db.seed")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
