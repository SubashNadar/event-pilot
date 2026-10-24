# Resilience and Performance Evidence

EventPilot is designed to demonstrate dependable multi-agent coordination in a
local course environment. This document records the intentional controls that
limit unnecessary work, handle recoverable failure, and protect the planning API.

## Efficiency Controls

| Control | Implementation | Benefit |
|---|---|---|
| Parallel delegation | Independent specialist nodes fan out from the shared LangGraph event state, then converge at the Event Manager. | Reduces wall-clock planning time compared with a fully sequential workflow. |
| LLM concurrency limit | `MAX_PARALLEL_LLM_CALLS` uses an asyncio semaphore. | Prevents six simultaneous specialists from exhausting Azure deployment throughput. |
| Bounded reflection | Review sends only failed plans through the affected re-plan path; the manager's automatic re-plans are capped at `max_replans`. The owner's send-backs are re-split by the manager and repeat until the owner approves. | Avoids unbounded self-correction loops and unnecessary model calls; the owner stays in control of the final loop. |
| Tool-result cache | Identical MCP calls reuse a result for `TOOL_CACHE_TTL_S`. | Reduces latency and external-service load during retries or replay. |
| HTTP and embedding caches | Free-service responses and embedding vectors are persisted locally when available. | Keeps repeat demonstrations quick and less dependent on network availability. |
| Scoped plan edits | Plan-chat interpretation selects only affected specialists for a change. | A schedule or budget edit does not recreate every part of a valid plan. |

## Resilience Controls

| Failure or risk | Control | Observable outcome |
|---|---|---|
| MCP service unavailable | Client uses the same deterministic read-only local tool implementation. | Planning remains available while the run records the fallback context. |
| Slow tool or provider | Tool and HTTP calls have configured timeouts. | A failed step pauses with recovery options instead of hanging the entire workflow. |
| Invalid specialist result | Typed Pydantic models and review checks validate plan shape and key constraints. | Review can request one bounded reflection pass with specific feedback. |
| Temporary tool failure | Retry, retry-with-adjustment, and skip options are available per failed step. | The owner can continue without losing completed work. |
| Excessive tool use | Tool allowlists and `MAX_TOOL_CALLS_PER_RUN` restrict each planning run. | Specialists cannot call unrelated or unlimited tools. |
| Large or abusive request | Request-size limits, text limits, rate limits, prompt-injection screening, and user-data fencing. | The API returns a controlled response rather than sending unsafe input to the model. |
| Browser interruption | Runs and chat sessions are persisted; SSE supports replay using `Last-Event-ID`. | A saved run can be reopened and observed after reconnecting. |

## Verification Commands

From the repository root:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite uses isolated temporary data, disables free network APIs, and points
MCP to an unused local port so deterministic in-process tools are used. It does
not require Azure credentials or a running frontend.

For a production frontend build:

```bash
cd frontend
npm run build
```

## What Is Deliberately Not Claimed

- These controls are appropriate for a course demonstration, not a load-tested
  production service-level agreement.
- SQLite is the local transactional store for plans and runs. PostgreSQL with
  pgvector is used separately for the optional RAG knowledge base.
- Live vendor booking, calendar writes, email sending, and payment actions are
  outside the current read-only, human-approved planning scope.
