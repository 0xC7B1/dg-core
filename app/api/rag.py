"""RAG API — document upload for vector search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_admin_dep
from app.models.db_models import User
from app.models.responses import RagUploadResponse
from app.modules.rag.index import index_document

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RAGUploadRequest(BaseModel):
    content: str
    category: str
    metadata: dict | None = None


@router.post("/upload")
async def upload_rag_document(
    req: RAGUploadRequest,
    admin_user: Annotated[User, Depends(require_admin_dep)],
) -> RagUploadResponse:
    chunks = await index_document(req.content, req.category, req.metadata)
    return RagUploadResponse(chunks_indexed=chunks, category=req.category)
