import pytest

from helpers import ScriptedProvider, make_response
from orchestrator.agents.code_review_agent import (
    build_review_request,
    drop_comments_outside_diff,
    format_review,
    parse_review_response,
    review_diff,
    sort_comments,
)
from orchestrator.core.review_comment import ReviewComment


def comment(file="src/billing/invoice.py", line=13, severity="high", category="security",
            text="SQL built by string concatenation.", suggestion=None):
    return ReviewComment(
        file=file, line=line, severity=severity, category=category,
        comment=text, suggestion=suggestion,
    )


def tool_response(comments):
    return make_response(
        content="",
        tool_calls=[{"id": "call_1", "name": "submit_review", "arguments": {"comments": comments}}],
    )


def test_the_review_request_carries_an_annotated_diff_and_the_submit_tool(sample_diff):
    request = build_review_request(sample_diff, model="gpt-4o-mini")

    assert "FILE: src/billing/invoice.py" in request.messages[1].content
    assert [t["name"] for t in request.tools] == ["submit_review"]
    assert request.temperature == 0.0


def test_a_diff_with_nothing_reviewable_is_rejected():
    with pytest.raises(ValueError, match="no reviewable changes"):
        build_review_request("", model="gpt-4o-mini")


def test_a_tool_call_response_is_parsed_into_review_comments():
    response = tool_response([
        {
            "file": "src/billing/invoice.py",
            "line": 13,
            "severity": "high",
            "category": "security",
            "comment": "SQL injection via string concatenation.",
            "suggestion": "Use a parameterised query.",
        }
    ])

    comments = parse_review_response(response)

    assert len(comments) == 1
    assert comments[0].file == "src/billing/invoice.py"
    assert comments[0].severity == "high"
    assert comments[0].suggestion == "Use a parameterised query."


def test_tool_arguments_that_arrive_as_a_json_string_are_still_parsed():
    response = make_response(
        content="",
        tool_calls=[{
            "id": "call_1",
            "name": "submit_review",
            "arguments": '{"comments": [{"file": "a.py", "line": 2, "severity": "low", '
                         '"category": "style", "comment": "rename this"}]}',
        }],
    )

    comments = parse_review_response(response)

    assert comments[0].comment == "rename this"


def test_a_plain_json_response_is_accepted_as_a_fallback():
    response = make_response(
        content='```json\n{"comments": [{"file": "a.py", "line": 1, "severity": "low", '
                '"category": "style", "comment": "nit"}]}\n```'
    )

    assert parse_review_response(response)[0].comment == "nit"


def test_an_unparseable_response_yields_no_comments():
    assert parse_review_response(make_response(content="looks fine to me!")) == []


def test_an_empty_review_yields_no_comments():
    assert parse_review_response(tool_response([])) == []


def test_unknown_severities_and_categories_fall_back_to_defaults():
    response = tool_response([
        {"file": "a.py", "line": 1, "severity": "SHOWSTOPPER", "category": "vibes",
         "comment": "hmm"}
    ])

    parsed = parse_review_response(response)[0]

    assert parsed.severity == "medium"
    assert parsed.category == "bug"


def test_a_comment_with_no_text_is_dropped():
    response = tool_response([
        {"file": "a.py", "line": 1, "severity": "low", "category": "style", "comment": "   "}
    ])

    assert parse_review_response(response) == []


def test_a_missing_line_number_becomes_zero_rather_than_crashing():
    response = tool_response([
        {"file": "a.py", "severity": "low", "category": "style", "comment": "nit"}
    ])

    assert parse_review_response(response)[0].line == 0


def test_comments_are_sorted_by_severity_then_file_then_line():
    unsorted = [
        comment(file="b.py", line=2, severity="low"),
        comment(file="a.py", line=9, severity="critical"),
        comment(file="a.py", line=1, severity="low"),
    ]

    ordered = [(c.severity, c.file, c.line) for c in sort_comments(unsorted)]

    assert ordered == [("critical", "a.py", 9), ("low", "a.py", 1), ("low", "b.py", 2)]


def test_comments_about_untouched_files_are_dropped(sample_diff):
    kept = drop_comments_outside_diff(
        [comment(), comment(file="src/somewhere/else.py", line=4)], sample_diff
    )

    assert [c.file for c in kept] == ["src/billing/invoice.py"]


def test_comments_about_unchanged_lines_are_dropped(sample_diff):
    kept = drop_comments_outside_diff([comment(line=9999)], sample_diff)

    assert kept == []


def test_review_diff_filters_hallucinated_locations_by_default(sample_diff):
    provider = ScriptedProvider(outcomes=[tool_response([
        {"file": "src/billing/invoice.py", "line": 13, "severity": "high",
         "category": "security", "comment": "SQL injection."},
        {"file": "does/not/exist.py", "line": 1, "severity": "low",
         "category": "style", "comment": "made up"},
    ])])

    comments = review_diff(sample_diff, provider, model="gpt-4o-mini")

    assert [c.file for c in comments] == ["src/billing/invoice.py"]


def test_review_diff_can_keep_every_comment_when_asked(sample_diff):
    provider = ScriptedProvider(outcomes=[tool_response([
        {"file": "does/not/exist.py", "line": 1, "severity": "low",
         "category": "style", "comment": "made up"},
    ])])

    comments = review_diff(
        sample_diff, provider, model="gpt-4o-mini", restrict_to_changed_lines=False
    )

    assert len(comments) == 1


def test_format_review_groups_by_file_and_summarises():
    markdown = format_review([
        comment(line=13, severity="high", text="SQL injection.", suggestion="Parameterise it."),
        comment(file="src/billing/retry.py", line=8, severity="critical", category="bug",
                text="Bare except swallows every error."),
    ])

    assert "2 comment(s): 1 critical, 1 high" in markdown
    assert "### src/billing/retry.py" in markdown
    assert markdown.index("### src/billing/retry.py") < markdown.index("### src/billing/invoice.py")
    assert "- **L13 · high · security** — SQL injection." in markdown
    assert "Suggestion: Parameterise it." in markdown


def test_format_review_says_so_when_the_diff_is_clean():
    assert format_review([]) == "No issues found."
