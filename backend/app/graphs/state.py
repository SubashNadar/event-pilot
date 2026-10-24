"""LangGraph state for the event-planning workflow.

`steps` holds every step's status. Parallel specialists write different keys in
the same superstep, so the channel uses a merge reducer instead of overwrite.
The checkpointer persists this state per run (thread_id = run_id); pending
recovery questions live in the checkpoint as interrupts.
"""

from typing import Annotated, Any, TypedDict


def merge_steps(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(old or {})
    for step_id, record in (new or {}).items():
        merged[step_id] = {**merged.get(step_id, {}), **record}
    return merged


def merge_usage(old: dict[str, int] | None, new: dict[str, int] | None) -> dict[str, int]:
    merged = dict(old or {})
    for key, value in (new or {}).items():
        merged[key] = merged.get(key, 0) + int(value or 0)
    return merged


class EventPlanningState(TypedDict, total=False):
    run_id: str
    event: dict[str, Any]          # EventBrief as JSON-safe dict
    operation: str
    interactive: bool              # False = legacy blocking API: failed steps are skipped, never paused
    steps: Annotated[dict[str, Any], merge_steps]
    usage: Annotated[dict[str, int], merge_usage]
    # Specialist reports (SpecialistReport dumps, or {"skipped": True, ...}).
    logistics: dict[str, Any]
    finance: dict[str, Any]
    schedule: dict[str, Any]
    requirements: dict[str, Any]
    marketing: dict[str, Any]
    risks: dict[str, Any]
    final_plan: dict[str, Any]     # EventPlan dump
    review: dict[str, Any]         # {approved, issues, notes}: rule issues, plus the LLM judge's notes per specialist
    approval: dict[str, Any]       # {decision: 'approve' | 'revise'} from the event owner
    revision_count: int            # every re-plan pass so far (keys the UI events)
    manager_round: int             # automatic manager re-plans in the current owner round; reset when the owner sends it back
    human_rounds: int              # how many times the owner has sent the plan back
    feedback: list[str]            # the owner's requested changes, used by the manager's re-split and the next replan
    conflicts: dict[str, Any]      # {'items': [...]} mismatches found by the coordination step
    recommendations: str
    # Plan edits: reports kept from the previous plan, and inputs for the steps that run again.
    reuse: dict[str, Any]
    step_overrides: dict[str, Any]
