"""Run manager: executes planning runs as background tasks.

A run keeps going if the browser disconnects. Every event goes to `run_events`
first; SSE clients tail that log, so they can reconnect with `Last-Event-ID` and
miss nothing. When steps fail, the graph pauses at `interrupt()`; the API
collects one choice per paused step and resumes the graph with all of them
(`Command(resume={interrupt_id: choice})`).
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.agents import llm
from app.core.config import settings
from app.graphs.event_workflow import STEPS, build_graph
from app.services import ui_state
from app.models.event import EventBrief, EventPlan
from app.runs import store
from app.services.storage import load_event, save_plan

logger = logging.getLogger(__name__)
TERMINAL = {"completed", "cancelled", "error"}
STOPPED = "You stopped the plan."
REPLACED = "Replaced by the updated plan with your changes."


class RunNotFound(LookupError):
    pass


class RunConflict(RuntimeError):
    pass


class RunManager:
    def __init__(self) -> None:
        self.graph = None
        self._saver_cm = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._wakeups: dict[str, asyncio.Event] = {}
        # Callbacks for a run's outcome (plan edits post the result into the chat).
        self._hooks: dict[str, dict[str, Any]] = {}
        self._cancel_reasons: dict[str, str] = {}

    # ------------------------------------------------------------ lifecycle

    async def startup(self, checkpoint_path: str | None = None) -> None:
        path = checkpoint_path or str(Path(settings.data_dir) / "checkpoints.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._saver_cm = AsyncSqliteSaver.from_conn_string(path)
        saver = await self._saver_cm.__aenter__()
        self.graph = build_graph().compile(checkpointer=saver)
        store.initialize_run_storage()
        for run_id in store.mark_interrupted_runs():
            self.publish(run_id, {"type": "error", "message": store.INTERRUPTED_MESSAGE}, "error")

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        if self._saver_cm is not None:
            await self._saver_cm.__aexit__(None, None, None)

    # ------------------------------------------------------------ events

    def waiter(self, run_id: str) -> asyncio.Event:
        """Get this before reading events, then wait on it: no wake-up is lost."""
        return self._wakeups.setdefault(run_id, asyncio.Event())

    def publish(self, run_id: str, event: dict[str, Any], dedupe: str | None = None) -> None:
        event = {**event, "at": event.get("at") or datetime.now(timezone.utc).isoformat()}  # server time: replays keep true timings
        if store.append_event(run_id, event, dedupe) is None:
            return
        old = self._wakeups.pop(run_id, None)
        if old is not None:
            old.set()

    # ------------------------------------------------------------ config

    def _config(self, run_id: str, event_id: str, operation: str) -> tuple[dict[str, Any], str | None, str | None]:
        config: dict[str, Any] = {"configurable": {"thread_id": run_id}, "run_name": f"eventpilot-{operation}", "metadata": {"run_id": run_id, "event_id": event_id, "langfuse_session_id": event_id, "langfuse_tags": ["eventpilot", operation]}}
        trace_id = trace_url = None
        if settings.langfuse_enabled:
            try:
                from langfuse import Langfuse
                from langfuse.langchain import CallbackHandler

                from app.services.tracing import configure_langfuse_env

                configure_langfuse_env()
                trace_id = Langfuse.create_trace_id(seed=run_id)  # same trace across resumes
                config["callbacks"] = [CallbackHandler(trace_context={"trace_id": trace_id})]
                if settings.langfuse_project_id:
                    trace_url = f"{settings.resolved_langfuse_base_url.rstrip('/')}/project/{settings.langfuse_project_id}/traces/{trace_id}"
            except Exception:
                logger.exception("Langfuse tracing unavailable for run %s", run_id)
        return config, trace_id, trace_url

    # ------------------------------------------------------------ runs

    async def previous_reports(self, run_id: str) -> dict[str, Any]:
        """Specialist reports from a finished run's checkpoint."""
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        values = snapshot.values or {}
        return {key: values.get(key) or {} for key in ("logistics", "finance", "schedule", "requirements", "marketing", "risks")}

    def record_change_request(self, event_id: str) -> int:
        """Count one change request the owner made at approval (applied or sent back); returns the total so far."""
        return ui_state.bump_attempts(event_id)

    def change_requests(self, event_id: str) -> int:
        return ui_state.attempts(event_id)

    async def paused_state(self, run_id: str) -> dict[str, Any]:
        """The run's state while it is paused: the plan built so far, the review's open notes and the owner's rounds."""
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        return dict(snapshot.values or {})

    async def paused_plan(self, run_id: str) -> dict[str, Any] | None:
        """The plan a run has built so far, for the owner to review while it is paused."""
        return (await self.paused_state(run_id)).get("final_plan")

    def on_outcome(self, run_id: str, **hooks: Any) -> None:
        self._hooks[run_id] = hooks

    def _hook(self, run_id: str, name: str, *args: Any) -> None:
        hook = self._hooks.get(run_id, {}).get(name)
        if hook is None:
            return
        try:
            hook(*args)
        except Exception:
            logger.exception("Run %s %s hook failed", run_id, name)

    async def start_edit(self, event: EventBrief, reports: dict[str, Any], step_overrides: dict[str, Any], session_id: str | None = None, *, base_plan: dict[str, Any] | None = None, owner_review: bool = False) -> str:
        """A plan-edit run: listed steps run again with their inputs, the rest keep their reports.

        `base_plan` is the plan the owner is looking at: the edit changes only the parts the re-run steps own.
        `owner_review` pauses the edited plan at approval: set when the plan was never approved (a change sent back
        from the approval card, or from a failed step), so nothing becomes final without the owner seeing it."""
        from app.agents.plan_edit import STATE_KEYS

        reuse = {step: reports[key] for step, key in STATE_KEYS.items() if step not in step_overrides and reports.get(key) and not reports[key].get("skipped")}
        extra: dict[str, Any] = {"reuse": reuse, "step_overrides": step_overrides, "owner_review": owner_review}
        if base_plan:
            extra["base_plan"] = base_plan
        return await self.start(event, "plan-edit", session_id, extra=extra)

    async def start(self, event: EventBrief, operation: str = "plan-generation", session_id: str | None = None, interactive: bool = True, extra: dict[str, Any] | None = None) -> str:
        if self.graph is None:
            raise RuntimeError("Run manager is not started")
        run_id = store.create_run(str(event.id), operation, session_id)
        config, trace_id, trace_url = self._config(run_id, str(event.id), operation)
        store.update_run(run_id, trace_id=trace_id, trace_url=trace_url)
        self.publish(run_id, {"type": "run_started", "runId": run_id, "traceId": trace_id or "", "traceUrl": trace_url, "operation": operation, "eventId": str(event.id)}, "run_started")
        self.publish(run_id, {"type": "plan_created", "steps": STEPS}, "plan_created")
        if not llm.llm_enabled():
            self.publish(run_id, {"type": "notice", "message": "Azure OpenAI isn't configured, so the agents use rule-based logic with the same tools."}, "notice:rules")
        graph_input = {
            "run_id": run_id, "event": event.model_dump(mode="json"), "operation": operation, "interactive": interactive,
            "steps": {step["id"]: {"status": "pending"} for step in STEPS}, "revision_count": 0,
            **(extra or {}),
        }
        self._spawn(run_id, graph_input, config)
        return run_id

    def _spawn(self, run_id: str, graph_input: Any, config: dict[str, Any]) -> None:
        store.update_run(run_id, status="running")
        self._tasks[run_id] = asyncio.create_task(self._execute(run_id, graph_input, config))

    async def _execute(self, run_id: str, graph_input: Any, config: dict[str, Any]) -> None:
        try:
            async for mode, chunk in self.graph.astream(graph_input, config, stream_mode=["custom", "updates"]):
                if mode == "custom" and isinstance(chunk, dict) and "event" in chunk:
                    self.publish(run_id, chunk["event"], chunk.get("dedupe"))
            snapshot = await self.graph.aget_state(config)
            pending = [interrupt for task in snapshot.tasks for interrupt in task.interrupts]
            if pending:
                store.update_run(run_id, status="paused")
                self.publish(run_id, {"type": "run_paused", "pendingStepIds": [interrupt.value["step_id"] for interrupt in pending]})
                self._hook(run_id, "paused", [interrupt.value for interrupt in pending])
                return
            values = snapshot.values
            if values.get("review", {}).get("approved") is False:
                message = "The plan needs attention: " + " ".join(values["review"].get("issues", [])) + " Update the brief or budget and generate the plan again."
                store.update_run(run_id, status="error", error=message)
                self.publish(run_id, {"type": "error", "message": message}, "error")
                self._hook(run_id, "ended", "error", message)
                self._hooks.pop(run_id, None)
                return
            plan = EventPlan.model_validate({**values["final_plan"], "run_id": run_id})
            save_plan(plan)
            usage = values.get("usage", {})
            run = store.get_run(run_id)
            duration = int((datetime.now(timezone.utc) - run.created_at).total_seconds() * 1000) if run else 0
            self.publish(run_id, {"type": "plan_ready", "plan": plan.model_dump(mode="json")}, "plan_ready")
            self.publish(run_id, {"type": "run_completed", "usage": {
                "tokensIn": usage.get("tokens_in", 0), "tokensOut": usage.get("tokens_out", 0),
                "costUsd": llm.cost_usd(usage.get("tokens_in", 0), usage.get("tokens_out", 0)),
                "durationMs": duration, "model": llm.model_name() if llm.llm_enabled() else "rules",
            }}, "run_completed")
            store.update_run(run_id, status="completed")
            self._hook(run_id, "completed", plan)
            self._hooks.pop(run_id, None)
        except asyncio.CancelledError:
            store.update_run(run_id, status="cancelled")
            self.publish(run_id, {"type": "run_cancelled", "message": self._cancel_reasons.pop(run_id, STOPPED)}, "run_cancelled")
            self._hook(run_id, "ended", "cancelled", "You stopped the update.")
            self._hooks.pop(run_id, None)
            raise
        except Exception as error:
            logger.exception("Run %s failed", run_id)
            message = f"The planning run could not finish. Check the brief and try again. Reference: {run_id}"
            store.update_run(run_id, status="error", error=message)
            self.publish(run_id, {"type": "error", "message": message}, "error")
            self._hook(run_id, "ended", "error", message)
            self._hooks.pop(run_id, None)
        finally:
            self._tasks.pop(run_id, None)

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.shield(task)

    def _require(self, run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run

    def _run_config(self, run) -> dict[str, Any]:
        return self._config(run.id, run.event_id, run.operation)[0]

    async def pending_interrupt(self, run_id: str, step_id: str) -> dict[str, Any]:
        run = self._require(run_id)
        if run.status != "paused":
            raise RunConflict(f"Run is {run.status}, not waiting for a decision")
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        for task in snapshot.tasks:
            for interrupt in task.interrupts:
                if interrupt.value.get("step_id") == step_id:
                    return {"id": interrupt.id, **interrupt.value}
        raise RunConflict(f"Step {step_id} is not waiting for a decision")

    async def resolve(self, run_id: str, step_id: str, choice: dict[str, Any]) -> str:
        """Record a choice; resume once every paused step has one. Returns 'resumed' or 'queued'."""
        run = self._require(run_id)
        target = await self.pending_interrupt(run_id, step_id)
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        waiting = {interrupt.id: interrupt.value["step_id"] for task in snapshot.tasks for interrupt in task.interrupts}
        pending = store.get_pending_choices(run_id)
        pending[target["id"]] = choice
        pending = {key: value for key, value in pending.items() if key in waiting}
        self.publish(run_id, {"type": "recovery_chosen", "stepId": step_id, "action": choice.get("action"), "label": choice.get("label", "")})
        if set(pending) != set(waiting):
            store.set_pending_choices(run_id, pending)
            return "queued"
        store.set_pending_choices(run_id, {})
        self._spawn(run_id, Command(resume=pending), self._run_config(run))
        return "resumed"

    async def continue_run(self, run_id: str) -> str:
        """Pick a stopped, errored or interrupted run up from its checkpoint, where it left off.

        Paused runs continue through their pending decisions (see `resolve`), so they are not restarted here.
        """
        run = self._require(run_id)
        if run_id in self._tasks:
            return "running"
        if run.status == "paused":
            raise RunConflict("This run is waiting for your decision on a step")
        if run.status == "completed":
            raise RunConflict("This run has already finished")
        config = self._run_config(run)
        snapshot = await self.graph.aget_state(config)
        if not snapshot.values:
            raise RunConflict("The run stopped before it saved any progress, so there is nothing to continue. Start the plan again.")
        if not (snapshot.next or snapshot.tasks):  # a run stopped mid-step has its step pending, not in next
            raise RunConflict("There is nothing left to continue in this run")
        self._spawn(run_id, None, config)  # None input: LangGraph resumes from the last checkpoint
        return "resumed"

    async def cancel(self, run_id: str, reason: str = STOPPED) -> None:
        """Stop a run. `reason` is what the owner reads: they stopped it, or their change replaced it with a new run."""
        run = self._require(run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            self._cancel_reasons[run_id] = reason
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        elif run.status not in TERMINAL:
            store.update_run(run_id, status="cancelled")
            self.publish(run_id, {"type": "run_cancelled", "message": reason}, "run_cancelled")

    async def run_to_completion(self, event: EventBrief, operation: str) -> EventPlan:
        """Legacy blocking API: failed steps are skipped instead of paused."""
        run_id = await self.start(event, operation, interactive=False)
        await self.wait(run_id)
        run = store.get_run(run_id)
        if run is None or run.status != "completed":
            raise RuntimeError(run.error if run and run.error else "The planning run did not complete")
        from app.services.storage import load_plan

        plan = load_plan(event.id)
        if plan is None:
            raise RuntimeError("The planning run finished without a plan")
        return plan

    def event_for(self, run) -> EventBrief:
        from uuid import UUID

        event = load_event(UUID(run.event_id))
        if event is None:
            raise RunNotFound(run.event_id)
        return event


run_manager = RunManager()
