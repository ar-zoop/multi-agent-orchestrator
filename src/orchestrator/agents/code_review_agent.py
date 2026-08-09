import json
import logging

from orchestrator.agents.diff_parser import annotate_diff, parse_diff
from orchestrator.core.chat_message import Message
from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.review_comment import CATEGORIES, SEVERITIES, ReviewComment

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {name: index for index, name in enumerate(SEVERITIES)}
DEFAULT_SEVERITY = "medium"
DEFAULT_CATEGORY = "bug"

SYSTEM_PROMPT = """You are a senior engineer reviewing a pull request diff.

Review only the lines that were changed. For each real problem you find, emit one comment \
citing the file path and the line number shown in the left gutter of the diff.

Focus on, in priority order:
1. bug - logic errors, unhandled edge cases, race conditions, resource leaks, swallowed exceptions
2. security - injection, secrets in code, missing authz, unsafe deserialisation
3. performance - N+1 queries, work inside loops that should be hoisted, unbounded memory growth
4. test - missing or misleading test coverage for the changed behaviour
5. style - naming, dead code, readability, only when it genuinely hurts maintainability

Do not comment on unchanged code. Do not restate what the diff does. Do not pad the review \
with trivia. If the diff is clean, return an empty list of comments.

Always answer by calling the submit_review tool."""

SUBMIT_REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit the structured review of the pull request diff.",
    "parameters": {
        "type": "object",
        "properties": {
            "comments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "severity": {"type": "string", "enum": list(SEVERITIES)},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "comment": {"type": "string"},
                        "suggestion": {"type": "string"},
                    },
                    "required": ["file", "line", "severity", "category", "comment"],
                },
            }
        },
        "required": ["comments"],
    },
}


def build_review_request(diff_text: str, model: str, temperature: float = 0.0) -> ChatRequest:
    annotated = annotate_diff(diff_text)
    if not annotated.strip():
        raise ValueError("The diff contains no reviewable changes.")
    return ChatRequest(
        model=model,
        messages=[
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"Review this diff:\n\n{annotated}"),
        ],
        temperature=temperature,
        tools=[SUBMIT_REVIEW_TOOL],
    )


def _normalise(value: str, allowed: tuple, default: str) -> str:
    candidate = (value or "").strip().lower()
    return candidate if candidate in allowed else default


def _coerce_line(value) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _to_comment(raw: dict) -> ReviewComment | None:
    text = (raw.get("comment") or "").strip()
    if not text:
        return None
    suggestion = raw.get("suggestion")
    return ReviewComment(
        file=(raw.get("file") or "unknown").strip(),
        line=_coerce_line(raw.get("line")),
        severity=_normalise(raw.get("severity"), SEVERITIES, DEFAULT_SEVERITY),
        category=_normalise(raw.get("category"), CATEGORIES, DEFAULT_CATEGORY),
        comment=text,
        suggestion=(suggestion or "").strip() or None,
    )


def _extract_payload(response) -> list[dict]:
    for tool_call in response.tool_calls or []:
        if tool_call.get("name") != "submit_review":
            continue
        arguments = tool_call.get("arguments") or {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return arguments.get("comments") or []

    content = (response.content or "").strip()
    if not content:
        return []
    if content.startswith("```"):
        lines = content.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("code review response was neither a tool call nor valid JSON")
        return []
    if isinstance(parsed, dict):
        return parsed.get("comments") or []
    if isinstance(parsed, list):
        return parsed
    return []


def parse_review_response(response) -> list[ReviewComment]:
    comments = []
    for raw in _extract_payload(response):
        if not isinstance(raw, dict):
            continue
        comment = _to_comment(raw)
        if comment is not None:
            comments.append(comment)
    return sort_comments(comments)


def sort_comments(comments: list[ReviewComment]) -> list[ReviewComment]:
    return sorted(
        comments,
        key=lambda c: (SEVERITY_ORDER.get(c.severity, len(SEVERITIES)), c.file, c.line),
    )


def drop_comments_outside_diff(comments: list[ReviewComment],
                               diff_text: str) -> list[ReviewComment]:
    touched = {
        f.path: {line.new_lineno for line in f.added_lines if line.new_lineno is not None}
        for f in parse_diff(diff_text)
    }
    kept = []
    for comment in comments:
        lines = touched.get(comment.file)
        if lines is None:
            logger.info("dropping review comment for untouched file %s", comment.file)
            continue
        if lines and comment.line not in lines:
            logger.info(
                "dropping review comment for %s:%d - not an added line", comment.file, comment.line
            )
            continue
        kept.append(comment)
    return kept


def review_diff(diff_text: str, provider, model: str,
                restrict_to_changed_lines: bool = True) -> list[ReviewComment]:
    response = provider.complete(build_review_request(diff_text, model=model))
    comments = parse_review_response(response)
    if restrict_to_changed_lines:
        comments = drop_comments_outside_diff(comments, diff_text)
    return comments


def format_review(comments: list[ReviewComment]) -> str:
    if not comments:
        return "No issues found."

    counts = {}
    for comment in comments:
        counts[comment.severity] = counts.get(comment.severity, 0) + 1
    summary = ", ".join(
        f"{counts[s]} {s}" for s in SEVERITIES if s in counts
    )

    lines = ["## Code review", "", f"{len(comments)} comment(s): {summary}", ""]
    current_file = None
    for comment in sort_comments(comments):
        if comment.file != current_file:
            current_file = comment.file
            lines.append(f"### {current_file}")
            lines.append("")
        lines.append(
            f"- **L{comment.line} · {comment.severity} · {comment.category}** — {comment.comment}"
        )
        if comment.suggestion:
            lines.append(f"  - Suggestion: {comment.suggestion}")
    lines.append("")
    return "\n".join(lines)
