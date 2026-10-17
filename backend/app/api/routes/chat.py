from fastapi import APIRouter

from app.graphs.chat_workflow import run_chat_turn
from app.models.chat import PlanningChatTurnRequest, PlanningChatTurnResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/planning-turn", response_model=PlanningChatTurnResponse)
def planning_turn(payload: PlanningChatTurnRequest) -> PlanningChatTurnResponse:
    return run_chat_turn(payload)
