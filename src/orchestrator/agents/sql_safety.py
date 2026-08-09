import re

FORBIDDEN_KEYWORDS = {
    "alter", "analyze", "begin", "call", "cluster", "comment", "commit", "copy",
    "create", "deallocate", "declare", "delete", "discard", "do", "drop",
    "execute", "grant", "import", "insert", "into", "listen", "load",
    "lock", "merge", "move", "notify", "prepare", "reassign", "refresh",
    "reindex", "release", "reset", "revoke", "rollback", "savepoint", "security",
    "set", "start", "truncate", "unlisten", "update", "vacuum",
}

FORBIDDEN_FUNCTIONS = {
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_sleep",
    "lo_import", "lo_export", "dblink", "dblink_exec", "pg_terminate_backend",
    "pg_reload_conf", "copy_from", "query_to_xml",
}

ALLOWED_LEADING_KEYWORDS = {"select", "with"}

_WORD = re.compile(r"[a-z_][a-z0-9_]*")
_LIMIT = re.compile(r"\blimit\b|\bfetch\s+(first|next)\b", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    pass


def _mask_literals(sql: str) -> str:
    out = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" 'literal' ")
        elif ch == '"':
            i += 1
            while i < n and sql[i] != '"':
                i += 1
            i += 1
            out.append(" ident ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _reject_comments(sql: str) -> None:
    masked = _mask_literals(sql)
    if "--" in masked or "/*" in masked:
        raise UnsafeSQLError("SQL comments are not allowed in generated queries.")
    if "$$" in masked:
        raise UnsafeSQLError("Dollar-quoted blocks are not allowed in generated queries.")


def _single_statement(sql: str) -> str:
    masked = _mask_literals(sql)
    body = masked.rstrip().rstrip(";")
    if ";" in body:
        raise UnsafeSQLError("Only a single SQL statement may be executed.")
    return sql.rstrip().rstrip(";").strip()


def validate_sql(sql: str) -> str:
    if sql is None or not sql.strip():
        raise UnsafeSQLError("No SQL statement was produced.")

    _reject_comments(sql)
    statement = _single_statement(sql)
    masked = _mask_literals(statement).lower()
    words = _WORD.findall(masked)

    if not words:
        raise UnsafeSQLError("No SQL statement was produced.")
    if words[0] not in ALLOWED_LEADING_KEYWORDS:
        raise UnsafeSQLError(
            f"Only SELECT queries may be executed, got a statement starting with '{words[0].upper()}'."
        )

    forbidden = sorted(set(words) & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise UnsafeSQLError(
            f"Query rejected, it contains disallowed keyword(s): {', '.join(k.upper() for k in forbidden)}."
        )

    blocked_functions = sorted(set(words) & FORBIDDEN_FUNCTIONS)
    if blocked_functions:
        raise UnsafeSQLError(
            f"Query rejected, it calls disallowed function(s): {', '.join(blocked_functions)}."
        )

    return statement


def has_limit(sql: str) -> bool:
    return bool(_LIMIT.search(_mask_literals(sql)))


def enforce_limit(sql: str, max_rows: int) -> str:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    statement = sql.rstrip().rstrip(";").strip()
    if has_limit(statement):
        return statement
    return f"{statement} LIMIT {max_rows}"


def make_safe(sql: str, max_rows: int = 200) -> str:
    return enforce_limit(validate_sql(sql), max_rows)
