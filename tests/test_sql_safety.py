import pytest

from orchestrator.agents.sql_safety import (
    UnsafeSQLError,
    enforce_limit,
    has_limit,
    make_safe,
    validate_sql,
)

SAFE_QUERIES = [
    "SELECT * FROM Loan",
    "select count(*) from loan where status = 'delinquent'",
    "SELECT l.loan_id, b.last_name FROM Loan l JOIN Borrower b USING (borrower_id)",
    "WITH recent AS (SELECT * FROM Payment ORDER BY due_date DESC LIMIT 10) SELECT * FROM recent",
    "SELECT SUM(amount) FROM Ledger WHERE transaction_type = 'interest_accrual'",
    "SELECT * FROM Loan ORDER BY loan_amount DESC FETCH FIRST 5 ROWS ONLY",
]

UNSAFE_QUERIES = [
    "DELETE FROM Loan",
    "UPDATE Loan SET status = 'paid_off'",
    "INSERT INTO Loan (loan_id) VALUES (1)",
    "DROP TABLE Borrower",
    "TRUNCATE Payment",
    "ALTER TABLE Loan ADD COLUMN x INT",
    "GRANT ALL ON Loan TO PUBLIC",
    "CREATE TABLE evil (id INT)",
    "SELECT * FROM Loan; DROP TABLE Loan",
    "SELECT * INTO backup FROM Loan",
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM Loan -- and now something sneaky",
    "SELECT /* hidden */ * FROM Loan",
    "",
    "   ",
]


@pytest.mark.parametrize("sql", SAFE_QUERIES)
def test_read_only_queries_are_allowed(sql):
    assert validate_sql(sql) == sql.rstrip().rstrip(";").strip()


@pytest.mark.parametrize("sql", UNSAFE_QUERIES)
def test_anything_that_is_not_a_plain_read_is_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_a_trailing_semicolon_is_stripped_not_rejected():
    assert validate_sql("SELECT 1;") == "SELECT 1"
    assert validate_sql("SELECT 1;   \n") == "SELECT 1"


def test_keywords_inside_string_literals_do_not_trip_the_guard():
    sql = "SELECT * FROM Loan WHERE status = 'update' AND loan_type = 'drop table'"
    assert validate_sql(sql) == sql


def test_an_escaped_quote_inside_a_literal_is_handled():
    sql = "SELECT * FROM Borrower WHERE last_name = 'O''Brien'"
    assert validate_sql(sql) == sql


def test_a_semicolon_inside_a_literal_is_not_a_second_statement():
    sql = "SELECT * FROM Borrower WHERE last_name = 'a;b'"
    assert validate_sql(sql) == sql


def test_the_error_message_names_the_offending_keyword():
    with pytest.raises(UnsafeSQLError, match="DELETE"):
        validate_sql("SELECT 1 FROM Loan WHERE loan_id IN (DELETE FROM Loan RETURNING loan_id)")


def test_has_limit_detects_both_limit_and_fetch_first():
    assert has_limit("SELECT * FROM Loan LIMIT 10") is True
    assert has_limit("SELECT * FROM Loan FETCH FIRST 5 ROWS ONLY") is True
    assert has_limit("SELECT * FROM Loan") is False


def test_has_limit_ignores_the_word_limit_inside_a_literal():
    assert has_limit("SELECT * FROM Loan WHERE loan_type = 'limit'") is False


def test_enforce_limit_appends_a_limit_when_one_is_missing():
    assert enforce_limit("SELECT * FROM Loan", 50) == "SELECT * FROM Loan LIMIT 50"


def test_enforce_limit_leaves_an_existing_limit_alone():
    assert enforce_limit("SELECT * FROM Loan LIMIT 5", 50) == "SELECT * FROM Loan LIMIT 5"


def test_enforce_limit_rejects_a_non_positive_cap():
    with pytest.raises(ValueError, match="must be positive"):
        enforce_limit("SELECT 1", 0)


def test_make_safe_validates_and_caps_in_one_call():
    assert make_safe("SELECT * FROM Loan;", max_rows=25) == "SELECT * FROM Loan LIMIT 25"

    with pytest.raises(UnsafeSQLError):
        make_safe("DROP TABLE Loan")
