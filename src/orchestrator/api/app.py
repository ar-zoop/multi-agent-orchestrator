import json
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.chat_response import ChatResponse
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.providers.fallback_provider import FallbackProvider
from orchestrator.providers.google_provider import GoogleProvider
from orchestrator.providers.openai_provider import OpenAIProvider

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Multi-Agent Orchestrator")

# One shared circuit breaker + fallback chain for the whole app's lifetime -
# state (which providers are currently "open"/down) needs to persist across
# requests, not get rebuilt fresh on every call.
_circuit_breaker = CircuitBreaker()
_fallback_provider = FallbackProvider(
    providers=[OpenAIProvider(), AnthropicProvider(), GoogleProvider()],
    circuit_breaker=_circuit_breaker,
)


def _error_body(error_type: str, message: str) -> dict:
    return {"error": {"type": error_type, "message": message}}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run", response_model=ChatResponse)
def run(request: ChatRequest):
    try:
        return _fallback_provider.complete(request)
    except RuntimeError as e:
        # FallbackProvider raises RuntimeError once every provider in the
        # chain has been tried and failed - a real "we're down", not a bug.
        raise HTTPException(
            status_code=502,
            detail=_error_body("all_providers_exhausted", str(e)),
        )
    except Exception as e:
        logger.exception("Unexpected error in /run")
        raise HTTPException(
            status_code=500,
            detail=_error_body("internal_error", str(e)),
        )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _stream_events(request: ChatRequest):
    try:
        for chunk in _fallback_provider.stream(request):
            yield _sse({"text": chunk})
    except RuntimeError as e:
        # A streaming response has already sent its 200 OK + headers by the
        # time this can fire, so we can't raise an HTTPException here - the
        # error has to travel as an SSE event on the same open connection.
        yield _sse(_error_body("all_providers_exhausted", str(e)))
    except Exception as e:
        logger.exception("Unexpected error in /stream")
        yield _sse(_error_body("internal_error", str(e)))
    finally:
        yield "event: done\ndata: [DONE]\n\n"


@app.post("/stream")
def stream(request: ChatRequest):
    return StreamingResponse(_stream_events(request), media_type="text/event-stream")
