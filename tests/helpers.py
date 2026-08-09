import itertools
from contextlib import contextmanager
from pathlib import Path

from orchestrator.core.chat_response import ChatResponse
from orchestrator.providers.base import Provider

FIXTURES = Path(__file__).parent / "fixtures"


class FakeAPIError(Exception):
    def __init__(self, status_code):
        super().__init__(f"fake error {status_code}")
        self.status_code = status_code


def make_response(provider_name="openai", content="hello", tool_calls=None,
                  stop_reason=None, input_tokens=10, output_tokens=5) -> ChatResponse:
    if stop_reason is None:
        stop_reason = "tool_call" if tool_calls else "final"
    return ChatResponse(
        content=content,
        provider=provider_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason=stop_reason,
        tool_calls=tool_calls,
    )


class ScriptedProvider(Provider):
    def __init__(self, name="openai", outcomes=None, stream_chunks=None):
        self.name = name
        self.requests = []
        self.call_count = 0
        outcomes = list(outcomes or [make_response(name)])
        self._outcomes = itertools.chain(outcomes, itertools.repeat(outcomes[-1]))
        self._stream_chunks = list(stream_chunks or [])

    def complete(self, request):
        self.call_count += 1
        self.requests.append(request)
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def stream(self, request):
        self.call_count += 1
        self.requests.append(request)
        for chunk in self._stream_chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class FakeCursor:
    def __init__(self, columns, rows, executed):
        self._columns = columns
        self._rows = list(rows)
        self._executed = executed
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._executed.append(sql)

    @property
    def description(self):
        if self._columns is None:
            return None
        return [(name, None, None, None, None, None, None) for name in self._columns]

    def fetchmany(self, size):
        chunk = self._rows[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self):
        return None


class FakeConnection:
    def __init__(self, columns, rows, executed):
        self.columns = columns
        self.rows = rows
        self.executed = executed
        self.closed = False

    def cursor(self):
        return FakeCursor(self.columns, self.rows, self.executed)

    def close(self):
        self.closed = True


def make_connection_factory(columns=None, rows=(), executed=None):
    executed = executed if executed is not None else []

    @contextmanager
    def factory():
        conn = FakeConnection(columns or [], list(rows), executed)
        try:
            yield conn
        finally:
            conn.close()

    factory.executed = executed
    return factory
