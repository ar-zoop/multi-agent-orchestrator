from pathlib import Path

from dotenv import load_dotenv

from orchestrator.db.connection import connect

load_dotenv()

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "orchestrator" / "db" / "schema.sql"


def main():
    with connect(read_only=False, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())
    print(f"Applied {SCHEMA_PATH.name}")


if __name__ == "__main__":
    main()
