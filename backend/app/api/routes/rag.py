from fastapi import APIRouter, HTTPException, status

from app.models.rag import RagQueryRequest, RagQueryResponse
from app.services.rag import RagUnavailableError, answer_question

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def query(payload: RagQueryRequest) -> RagQueryResponse:
    try:
        return answer_question(payload.question, payload.top_k)
    except RagUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The knowledge service is temporarily unavailable. Please try again shortly.") from error
