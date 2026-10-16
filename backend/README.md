# EventPilot Backend

The FastAPI service currently exposes an in-memory event and planning API. It
returns deterministic plans so the React app can integrate before Azure OpenAI
and LangGraph credentials are configured.

When Azure OpenAI is configured in backend/.env, plan generation uses a
structured Azure model response and falls back to the deterministic plan if a
provider request fails.

When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are configured, every
Azure plan-generation and budget-revision request is traced in Langfuse. The
event ID is used as the Langfuse session ID, making the related runs easy to
find during a demo. `LANGFUSE_HOST` is also supported for existing local
configuration; new setups should use `LANGFUSE_BASE_URL`.

## Run locally

Python 3.11 or later is required for the Langfuse SDK used by this project.

    cd backend
    export PATH="$HOME/.local/bin:$PATH"
    uv venv --python 3.11 .venv
    source .venv/bin/activate
    uv pip install --python .venv/bin/python -r requirements.txt
    uvicorn app.main:app --reload --port 8001

Open API documentation at http://localhost:8001/docs.

## Current endpoints

- POST /api/v1/events
- GET /api/v1/events/{event_id}
- POST /api/v1/events/{event_id}/plan
- GET /api/v1/events/{event_id}/plan
- POST /api/v1/events/{event_id}/revisions/budget

## EventPilot MCP server

The project includes an internal, read-only MCP server for deterministic
planning tools. It exposes venue search, budget validation, schedule conflict
checking, and event requirements, plus a venue-catalog resource. It does not
send messages, create bookings, or modify external accounts.

Run it separately from the FastAPI API:

    cd backend
    python -m app.mcp.server

The default streamable HTTP endpoint is http://127.0.0.1:8000/mcp. Test the
tool logic locally with the MCP Inspector before connecting it to the LangGraph
agents.

## Next backend step

Replace build_demo_plan() with a compiled LangGraph workflow that delegates to
logistics, finance, schedule, marketing, and risk agents.
