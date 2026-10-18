from fastapi import APIRouter

from app.graphs.brief_workflow import run_brief_turn
from app.graphs.chat_workflow import run_chat_turn
from app.models.chat import BriefTurnRequest, BriefTurnResponse, PlanningChatTurnRequest, PlanningChatTurnResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/planning-turn", response_model=PlanningChatTurnResponse)
def planning_turn(payload: PlanningChatTurnRequest) -> PlanningChatTurnResponse:
    return run_chat_turn(payload)


@router.post("/brief", response_model=BriefTurnResponse)
async def brief_turn(payload: BriefTurnRequest) -> BriefTurnResponse:
    """Dynamic brief intake: extract fields from free text, check them against
    benchmarks and frame the next question with data-driven options."""
    return await run_brief_turn(payload)
