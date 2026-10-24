# Event Pilot: Specification Plan and Ownership

Status date: 23 Oct 2026. Based on `origin/main` (commit `8fcf706`) plus local work
that is not yet committed. Ownership is derived from commit history, so it describes
who has done the work so far. It is a proposal for the team to confirm, not an
assignment.

## 1. Purpose and scope

Event Pilot plans an Indian event from one chat message. Specialist agents build the
plan live, the owner resolves failures by choosing options, and the finished plan can
be downloaded as a PDF blueprint or a PPTX brochure.

In scope: the brief chat, the multi-agent planning run, recovery from failed steps,
live streaming to the browser, plan downloads, and the persistence of events and plans.

Out of scope for now: sign-in, multi-user access control, hosted deployment, real
vendor booking, and real-time venue availability.

## 2. Users

| Role | Who | What they do |
|---|---|---|
| Event owner | The person planning an event | Describes the event, answers questions, resolves failed steps, downloads the plan |
| Reviewer | Course reviewers and the team | Reads the architecture, runs the demo, checks the evidence documents |
| Maintainer | The developers | Changes the workflow, agents, UI and documents |

## 3. Functional specification

Status key: **Done** is implemented and tested. **Partial** works, but with a known gap.
**Not wired** exists in the backend but the current UI does not use it.

| ID | Feature | Status | Where |
|---|---|---|---|
| F1 | Brief intake from one sentence, with option chips and warnings with fixes | Done | `graphs/brief_workflow.py`, `agents/brief_extract.py`, `search/benchmarks.py` |
| F2 | "Call it …" and "named …" event names | Done | `agents/brief_extract.py` |
| F3 | Venue-first planning: Logistics picks the venue, the others receive it as a handoff | Done | `graphs/event_workflow.py`, `agents/specialists.py` |
| F4 | Parallel specialists: Finance, Schedule, Requirements, Marketing, Risk | Done | `agents/specialists.py` |
| F5 | Finance uses the quoted venue rent and trims other lines to fit the budget | Done | `agents/specialists.py` (`fit_lines_to_budget`) |
| F6 | Coordination check: venue rent versus the budget line, and budget total versus approval | Done | `graphs/event_workflow.py` (`coordination`) |
| F7 | Manager composes one plan from the reports, using LLM or rules | Done | `graphs/event_workflow.py`, `services/planning.py` |
| F8 | Review: arithmetic, 12-hour times, 2–5 risks, venue matches Logistics | Done | `graphs/event_workflow.py` (`_review`) |
| F9 | Targeted replanning: only the specialists the review names re-run, at most twice | Done | `graphs/event_workflow.py` (`replan`, `owners_for`) |
| F10 | Recovery of a failed step: options, custom text, retry, skip | Done | `agents/recovery.py`, `api/routes/runs.py` |
| F11 | Live streaming of run events, replay after refresh, reconnect via `Last-Event-ID` | Done | `runs/manager.py`, `api/routes/runs.py` |
| F12 | Step detail drawer: goal, what was done, tools with results | Done | `frontend/src/components/StepDetailDrawer.tsx` |
| F13 | Plan downloads: PPTX brochure (7 slides) and PDF blueprint | Done locally, not committed | `services/exports.py`, `api/routes/events.py` |
| F14 | Stop a run; keep completed steps | Done | `runs/manager.py`, `POST /runs/{id}/cancel` |
| F15 | Change a finished plan by chat, re-running only affected specialists | Not wired | `agents/plan_edit.py`, `POST /events/{id}/chat` |
| F16 | Plan workspace: budget, schedule and risk tabs; approval | Not wired | Legacy `frontend/src/App.jsx` (not rendered) |
| F17 | Saved conversations: restore the brief chat after refresh | Partial | Events reopen from the sidebar; brief chats are not restored |
| F18 | Knowledge guide (RAG over the planning guide) | Partial | `api/routes/rag.py`, needs Postgres and embeddings |
| F19 | Feedback buttons, title rename | Partial | Local only; no backend endpoint |
| F20 | Event deletion | Not wired | No endpoint |

## 4. Non-functional requirements

| Area | Requirement | How it is met |
|---|---|---|
| Resilience | A failed tool or model must not stop the whole run | Step-level recovery; MCP falls back to in-process tools; rule-based planner when the LLM is off |
| Cost control | LLM calls and runs are rate limited | `core/guard.py`: per-client limits, body cap, one live run per event |
| Safety | User text must not steer the agents | Injection screening; user text fenced in every prompt |
| Traceability | Every run is recorded | `run_events` table; Langfuse tracing when keys are set |
| Latency | Specialists run in parallel after the venue | `graphs/event_workflow.py` fan-out |
| Accuracy | The plan must agree with itself | Coordination and review checks, plus bounded replanning |
| Portability | Runs without cloud services | Rule mode, SQLite, bundled sample data |

Test status: 54 backend tests pass (`cd backend && pytest -q`). The frontend typecheck passes.

## 5. Architecture

```
Browser (React, Vite)
  └─ useAgentStream hook ── POST /chat/brief, /events, /events/{id}/runs
                         └─ EventSource GET /runs/{id}/stream  (SSE, replayable)
FastAPI (backend/app)
  ├─ api/routes     chat, events, runs, rag
  ├─ graphs         brief_workflow (intake → validate → check → frame)
  │                 event_workflow (LangGraph: specialists → coordination → manager → review → replan)
  ├─ agents         specialists, checks, recovery, brief_extract, plan_edit, voice
  ├─ mcp            planning tools (MCP server, with in-process fallback)
  ├─ runs           run manager, run store, SSE publishing
  ├─ services       planning, storage (SQLite), exports (PDF, PPTX), tracing
  └─ search         BM25, semantic, hybrid venue search
```

### 5.1 Planning run, in order

1. `logistics_agent` picks a venue and its quoted rent.
2. `finance`, `schedule`, `requirements`, `marketing`, `risk` run in parallel, each with the venue handoff.
3. `coordination` checks venue rent against the budget, and the budget total against the approved amount.
4. `event_manager` composes the plan.
5. `review_plan` checks arithmetic, agenda times, risks, and venue agreement.
6. If the review fails and replans remain (`max_replans`, default 2): `replan` re-runs the named specialists, then steps 3–5 repeat.
7. `recommendations` writes the summary. Open issues are reported as a notice.

## 6. API contract (main endpoints, under `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat/brief` | One brief turn: answer, next question, options, warnings |
| POST | `/events` | Save a brief as an event |
| GET | `/events` | List events |
| GET | `/events/{id}` | Read one event |
| POST | `/events/{id}/runs` | Start a planning run (409 if one is live) |
| GET | `/events/{id}/runs/latest` | Most recent run |
| GET | `/runs/{id}/stream` | Live events over SSE, with replay |
| POST | `/runs/{id}/steps/{step}/resolve` | Answer a failed step with an option or custom text |
| POST | `/runs/{id}/steps/{step}/retry` / `skip` | Retry or skip a failed step |
| POST | `/runs/{id}/cancel` | Stop a run |
| GET | `/events/{id}/plan` | The saved plan |
| GET | `/events/{id}/exports/{pdf\|pptx}` | Download the plan |
| POST | `/events/{id}/chat` | Plan chat (not wired in the UI) |

## 7. Data

SQLite under `backend/data/`: events, plans, runs, `run_events` (the replay log),
chat sessions and chat messages, and LangGraph checkpoints. Secrets live only in
`backend/.env`, which git ignores.

## 8. Ownership

Derived from `git log` on `origin/main` (24 commits).

| Area | Primary owner (commits) | Secondary | Notes |
|---|---|---|---|
| Brief intake and chat workflow | Indushree (guided chat, planner guidance) | subash (brief fixes, "Call it" names) | `brief_workflow.py`, `brief_extract.py` |
| Planning workflow and agents | subash (live runs, coordination, replan) and Indushree (workflow hardening, latest commits) | Shared | Overlap: `event_workflow.py`, `specialists.py` |
| Recovery and run management | subash | Indushree | `recovery.py`, `runs/` |
| MCP tools and search | subash (MCP tools, hybrid search) | Indushree (MCP helpers) | `mcp/`, `search/` |
| Plan editing by chat | subash | — | `plan_edit.py`, `api/routes/chat.py` |
| Models, config, guards | subash | Indushree | `models/`, `core/` |
| Exports (PDF, PPTX) | Indushree (PDF blueprint, 2026-10-16); subash (PPTX brochure, local) | Shared | `services/exports.py` |
| Eventa chat UI (`frontend/src`) | subash | — | Hook, components, theme, logo |
| Legacy planning UI (`App.jsx`, `components/`, `run/`) | Indushree | — | Not rendered by the current app |
| Documentation and reviewer materials | Indushree (7 documents, guides, reviewer deck) | subash | `docs/`, `scripts/`, `README.md` |
| Tests | subash (run, coordination, exports) | Indushree (brief, LLM mode) | `backend/tests/` |

### 8.1 Contributors

- **Indushree** (19 commits): brief and guided chat, pgvector knowledge, the PDF
  blueprint and its design, the legacy planning UI, the demo and reviewer documents,
  and the latest workflow hardening.
- **subash** (3 commits, plus local work): live planning runs, hybrid search, MCP tools,
  plan editing, saved conversations, abuse protection, the Eventa rebrand, the
  coordination and replanning design, and the exports.
- **BHARGAV** (1 commit): the initial commit.

### 8.2 Merge risks to resolve before combining

1. **UI direction.** `origin/main` still has the legacy UI, which Indushree's latest
   commits change (`PlanChat`, `PlanWorkspace`, `run/`). Local `main` replaces that
   UI with Eventa. A merge would bring the legacy files back. This needs a decision.
2. **Workflow files.** Indushree's latest commits change `event_workflow.py` and
   `specialists.py`, which hold the coordination and replan code. These need a careful
   three-way merge with tests.
3. **Hook.** Both sides change `frontend/src/hooks/useAgentStream.ts` and
   `lib/langfuse.ts`.
4. **Local work.** The PDF and PPTX exports, the green theme, and the timing and
   budget-line fixes are not committed yet.

## 9. Decisions needed

1. Which UI is the product: Eventa (current local `main`) or the legacy planning UI?
2. Should the plan workspace (budget, risk tabs, approval) return inside the Eventa UI?
3. Should plan chat (F15) be wired into the UI?
4. Should exports require approval, as the earlier version did?
5. Which PPTX content is wanted beyond the seven slides?

## 10. Milestones

| Milestone | Scope | Owner (proposed) |
|---|---|---|
| M1: Sync | Merge `origin/main`, resolve the risks in 8.2, run the 54 tests | subash, with Indushree reviewing |
| M2: Commit local work | Exports, theme, timing and budget fixes | subash |
| M3: UI decision | Answer section 9 | Team |
| M4: Restore features | Plan workspace and plan chat, if M3 chooses Eventa | Indushree (workspace), subash (plan chat) |
| M5: Evidence | Refresh the reviewer deck and guide from the final code | Indushree |
| M6: Hardening | Brief restore, feedback and rename persistence, event deletion | Shared |

## 11. Risks

- Merge conflicts in the workflow files, which hold the most logic.
- The LLM output varies, so checks must keep catching mistakes in prose.
- The venue and vendor catalogues are sample data.
- Rate limits are kept in memory and reset on restart.
- There is no sign-in, so every user sees every event.
