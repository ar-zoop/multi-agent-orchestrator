from pydantic import BaseModel, Field

from orchestrator.core.review_comment import ReviewComment

DEFAULT_MODEL = "gpt-4o-mini"


class SqlAgentRequest(BaseModel):
    question: str = Field(min_length=1)
    model: str = DEFAULT_MODEL
    max_rows: int = Field(default=200, ge=1, le=1000)


class SqlAgentResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    answer: str


class CodeReviewRequest(BaseModel):
    diff: str = Field(min_length=1)
    model: str = DEFAULT_MODEL
    restrict_to_changed_lines: bool = True


class CodeReviewResponse(BaseModel):
    comments: list[ReviewComment]
    markdown: str


class AgentRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = DEFAULT_MODEL
    max_iterations: int = Field(default=8, ge=1, le=25)


class UsageResponse(BaseModel):
    cost: float
    input_tokens: int
    output_tokens: int
    calls: int


class AgentRunResponse(BaseModel):
    answer: str
    usage: dict[str, UsageResponse]
