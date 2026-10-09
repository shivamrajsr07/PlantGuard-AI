from __future__ import annotations

import re
from io import BytesIO

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import models


MAX_UPLOAD_BYTES = 2_000_000
ALLOWED_TYPES = {"text/plain", "application/pdf"}


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9]{3,}", text.lower()) if token not in {"the", "and", "for", "with"}}


def chunk_text(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    for idx, block in enumerate(blocks, start=1):
        if "\n" in block and len(block.split("\n", 1)[0]) < 90:
            title, body = block.split("\n", 1)
        else:
            title, body = f"Section {idx}", block
        for part_idx, start in enumerate(range(0, len(body), 850), start=1):
            sections.append((f"{title.strip()} #{part_idx}", body[start : start + 850].strip()))
    return sections or [("Document", text[:850])]


async def ingest_document(db: Session, upload: UploadFile) -> models.Document:
    content_type = upload.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only text/plain and application/pdf documents are supported.")
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 2 MB demo upload limit.")
    if content_type == "application/pdf":
        text = _extract_pdf(data)
    else:
        text = data.decode("utf-8", errors="ignore")
    if len(text.strip()) < 20:
        raise HTTPException(status_code=422, detail="No usable document text could be extracted.")
    doc = models.Document(filename=upload.filename or "uploaded-document", content_type=content_type)
    db.add(doc)
    db.flush()
    for section, body in chunk_text(text):
        db.add(models.DocumentChunk(document_id=doc.id, section=section, text=body))
    db.commit()
    db.refresh(doc)
    return doc


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise HTTPException(status_code=422, detail=f"Could not extract PDF text: {exc}") from exc


def search_documents(db: Session, query: str, limit: int = 5) -> list[dict]:
    query_tokens = tokenize(query)
    rows = db.query(models.DocumentChunk, models.Document).join(models.Document, models.Document.id == models.DocumentChunk.document_id).all()
    scored = []
    for chunk, doc in rows:
        score = len(query_tokens & tokenize(f"{chunk.section} {chunk.text}"))
        if score:
            scored.append((score, chunk, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "chunk_id": chunk.id,
            "filename": doc.filename,
            "section": chunk.section,
            "excerpt": chunk.text[:320],
            "score": score,
        }
        for score, chunk, doc in scored[:limit]
    ]
