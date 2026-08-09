import json
import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.agents.code_review_agent import format_review, review_diff
from orchestrator.agents.sql_agent import SqlAgentError, answer_question
from orchestrator.agents.sql_safety import UnsafeSQLError
from orchestrator.agents.tools import build_default_registry
from orchestrator.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    CodeReviewRequest,
    CodeReviewResponse,
    SqlAgentRequest,
    SqlAgentResponse,
    UsageResponse,
)
from orchestrator.core.agent import Agent
from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.chat_response import ChatResponse
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.providers.chain import build_provider_chain, default_providers

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Multi-Agent Orchestrator", version="0.1.0")

_circuit_breaker = CircuitBreaker()
_provider = None


def get_provider():
    global _provider
    if _provider is None:
        _provider = build_provider_chain(
            default_providers(), circuit_breaker=_circuit_breaker
        )
    return _provider


def get_connection_factory():
    return None


def _error_body(error_type: str, message: str) -> dict:
    return {"error": {"type": error_type, "message": message}}


def _usage_payload(provider) -> dict:
    usage = getattr(provider, "usage_by_provider", {})
    return {
        name: UsageResponse(
            cost=stats.cost,
            input_tokens=stats.input_tokens,
            output_tokens=stats.output_tokens,
            calls=stats.calls,
        )
        for name, stats in usage.items()
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run", response_model=ChatResponse)
def run(request: ChatRequest, provider=Depends(get_provider)):
    try:
        return provider.complete(request)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=_error_body("all_providers_exhausted", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /run")
        raise HTTPException(status_code=500, detail=_error_body("internal_error", str(e)))


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _stream_events(request: ChatRequest, provider):
    try:
        for chunk in provider.stream(request):
            yield _sse({"text": chunk})
    except RuntimeError as e:
        yield _sse(_error_body("all_providers_exhausted", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /stream")
        yield _sse(_error_body("internal_error", str(e)))
    finally:
        yield "event: done\ndata: [DONE]\n\n"


@app.post("/stream")
def stream(request: ChatRequest, provider=Depends(get_provider)):
    return StreamingResponse(
        _stream_events(request, provider), media_type="text/event-stream"
    )


@app.post("/agents/sql", response_model=SqlAgentResponse)
def run_sql_agent(
    request: SqlAgentRequest,
    provider=Depends(get_provider),
    connection_factory=Depends(get_connection_factory),
):
    try:
        answer = answer_question(
            request.question,
            provider=provider,
            model=request.model,
            connection_factory=connection_factory,
            max_rows=request.max_rows,
        )
    except (SqlAgentError, UnsafeSQLError) as e:
        raise HTTPException(status_code=400, detail=_error_body("unsafe_sql", str(e)))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=_error_body("all_providers_exhausted", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /agents/sql")
        raise HTTPException(status_code=500, detail=_error_body("internal_error", str(e)))

    return SqlAgentResponse(
        question=answer.question,
        sql=answer.sql,
        columns=answer.result.columns,
        rows=[[_jsonable(cell) for cell in row] for row in answer.result.rows],
        row_count=answer.result.row_count,
        truncated=answer.result.truncated,
        answer=answer.answer,
    )


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@app.post("/agents/review", response_model=CodeReviewResponse)
def run_code_review_agent(request: CodeReviewRequest, provider=Depends(get_provider)):
    try:
        comments = review_diff(
            request.diff,
            provider=provider,
            model=request.model,
            restrict_to_changed_lines=request.restrict_to_changed_lines,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_body("invalid_diff", str(e)))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=_error_body("all_providers_exhausted", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /agents/review")
        raise HTTPException(status_code=500, detail=_error_body("internal_error", str(e)))

    return CodeReviewResponse(comments=comments, markdown=format_review(comments))


@app.post("/agents/run", response_model=AgentRunResponse)
def run_agent(
    request: AgentRunRequest,
    provider=Depends(get_provider),
    connection_factory=Depends(get_connection_factory),
):
    registry = build_default_registry(
        provider, request.model, connection_factory=connection_factory
    )
    agent = Agent(
        provider=provider,
        model=request.model,
        tool_registry=registry,
        max_iterations=request.max_iterations,
    )
    try:
        answer = agent.run(request.prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=_error_body("agent_failed", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /agents/run")
        raise HTTPException(status_code=500, detail=_error_body("internal_error", str(e)))

    return AgentRunResponse(answer=answer, usage=_usage_payload(provider))
