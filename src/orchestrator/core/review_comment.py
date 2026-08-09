from pydantic import BaseModel

SEVERITIES = ("critical", "high", "medium", "low", "info")
CATEGORIES = ("bug", "style", "performance", "security", "test")


class ReviewComment(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    comment: str
    suggestion: str | None = None
