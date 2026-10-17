from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    top_k: int | None = Field(default=None, ge=1, le=8)


class RagCitation(BaseModel):
    source: str
    title: str
    excerpt: str
    relevance: float


class RagQueryResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[RagCitation] = Field(default_factory=list)
