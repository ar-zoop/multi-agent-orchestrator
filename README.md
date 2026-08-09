# Multi-Agent Orchestrator

A provider-agnostic LLM orchestration layer with automatic failover, plus two agents built on
top of it: a natural-language-to-SQL agent over a fintech loan servicing database, and a code
review agent that turns a pull request diff into structured review comments.

One integration surface. Three providers. If OpenAI is down, the same request completes on
Anthropic or Gemini without the caller knowing.

## Why it exists

Most LLM application code is written directly against one vendor SDK. That is fine until the
vendor rate-limits you, changes a response shape, or prices you out. This project puts a single
typed interface in front of OpenAI, Anthropic and Gemini, and handles the operational concerns
that show up in production: retries, failover, circuit breaking, cost accounting, and safety
guards on anything the model generates that is about to be executed.

## Architecture

```
                       FastAPI
                          |
        /run   /stream   /agents/sql   /agents/review   /agents/run
                          |
                 CostTrackingProvider        tokens, latency, $ per provider
                          |
                   FallbackProvider          retries with exponential backoff
                          |                  then failover to the next provider
                   CircuitBreaker            stops hammering a dead provider
                          |
        +-----------------+-----------------+
        |                 |                 |
  OpenAIProvider   AnthropicProvider   GoogleProvider
        \                 |                 /
                  ChatRequest / ChatResponse
                  (one pydantic shape for all three)

  Agents
    SQL agent          schema-aware NL -> SQL -> safety guard -> read-only Postgres -> answer
    Code review agent  unified diff -> annotated diff -> forced JSON tool call -> markdown

  ToolRegistry         both agents are also exposed as tools the generic Agent loop can call
```

Every provider implements the same two methods, `complete()` and `stream()`, and every wrapper
in the chain is itself a `Provider`. That is what makes the chain composable: cost tracking
wraps failover wraps the real SDK calls, and the agent loop only ever sees a `Provider`.

## Layout

```
src/orchestrator/
  providers/     base Provider ABC, one implementation per vendor, fallback + chain builder
  core/          agent loop, tool registry, circuit breaker, cost tracker, pydantic models
  agents/        SQL agent, code review agent, diff parser, SQL safety guard, tool wrappers
  api/           FastAPI app and request/response schemas
  db/            fintech schema, seed script, read-only connection helper
tests/           unit and API tests, fakes in tests/helpers.py
scripts/         runnable demos
```

## Running it locally

```bash
uv sync
cp .env.example .env          # then fill in your API keys

docker compose up -d postgres
uv run python -m orchestrator.db.seed

uv run uvicorn orchestrator.api.app:app --reload
```

Or run the whole thing, API and database together:

```bash
docker compose up --build
```

## Endpoints

| Method | Path             | What it does                                              |
| ------ | ---------------- | --------------------------------------------------------- |
| GET    | `/health`        | Liveness probe                                              |
| POST   | `/run`           | One completion through the provider chain                   |
| POST   | `/stream`        | The same, streamed as server-sent events                    |
| POST   | `/agents/sql`    | Question -> SQL -> rows -> plain-English answer             |
| POST   | `/agents/review` | Unified diff -> structured review comments plus markdown    |
| POST   | `/agents/run`    | The tool-calling agent loop with both agents registered     |

```bash
curl -s localhost:8000/agents/sql \
  -H 'content-type: application/json' \
  -d '{"question": "How many loans are currently delinquent?"}'
```

## SQL safety

The model is never trusted with database access. Every generated statement passes through
`agents/sql_safety.py` before it reaches Postgres:

- only `SELECT` and `WITH` may lead the statement
- write and DDL keywords are rejected, checked after string literals are masked so a borrower
  named `'O''Brien'` or a status of `'update'` does not trip the guard
- SQL comments, dollar-quoted blocks, and multiple statements are rejected outright
- dangerous functions such as `pg_read_file` and `pg_sleep` are blocked
- a `LIMIT` is injected when the query does not have one
- the connection itself is opened read-only with a statement timeout, so the guard is a second
  line of defence rather than the only one

## Demos

```bash
uv run python scripts/demo_sql_agent.py
uv run python scripts/demo_sql_agent.py "Which borrowers have more than one loan?"
uv run python scripts/demo_code_review.py --git main...HEAD
uv run python scripts/demo_agent.py
```

## Tests

```bash
uv run pytest
```

The suite runs entirely offline. `tests/helpers.py` provides a scripted fake provider and a fake
database connection, so failover, circuit breaking, cost accounting, SQL safety, diff parsing and
every API route are covered without a network call or a live database.

## Deploying

The image is a plain Dockerfile, so anything that builds Dockerfiles works. `railway.json` is
committed for Railway: connect the repo, set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and
`GEMINI_API_KEY`, and it builds from the Dockerfile and health checks `/health`.

The database is deliberately not tied to the host. Set `DATABASE_URL` to any Postgres
connection string - a hosted Neon or Supabase instance, a Railway plugin, anything - and run
the seed script once against it:

```bash
DATABASE_URL='postgresql://...' uv run python -m orchestrator.db.seed
```

The container binds `0.0.0.0` on the injected `PORT`, so it works unchanged on any platform that
assigns a port at runtime.

## Configuration

`DATABASE_URL` wins if it is set; the individual `POSTGRES_*` variables are the local fallback.

| Variable                        | Default          | Purpose                       |
| ------------------------------- | ---------------- | ----------------------------- |
| `OPENAI_API_KEY`                | -                | OpenAI provider               |
| `ANTHROPIC_API_KEY`             | -                | Anthropic provider            |
| `GEMINI_API_KEY`                | -                | Gemini provider               |
| `DATABASE_URL`                  | -                | Full Postgres connection string |
| `POSTGRES_HOST`                 | auto-detected    | SQL agent database host       |
| `POSTGRES_PORT`                 | `55432`          | SQL agent database port       |
| `POSTGRES_USER`                 | `admin`          | SQL agent database user       |
| `POSTGRES_PASSWORD`             | `password`       | SQL agent database password   |
| `POSTGRES_DB`                   | `loan_bank_db`   | SQL agent database name       |
| `POSTGRES_STATEMENT_TIMEOUT_MS` | `10000`          | Kills runaway generated SQL   |
| `PORT`                          | `8000`           | HTTP port                     |
