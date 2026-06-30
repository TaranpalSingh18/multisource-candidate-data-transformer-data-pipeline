from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile


router = APIRouter(prefix="/uploads", tags=["uploads"])

AllowedSourceType = Literal["recruiter_csv", "ats_json", "github_fixture", "resume"]


def _uploads_root() -> Path:
    # backend root = .../backend; uploads under backend/uploads/
    return Path(__file__).resolve().parents[2] / "uploads"


@router.post("/{source_type}")
async def upload_source_file(
    source_type: AllowedSourceType,
    file: UploadFile = File(...),
) -> dict:
    if source_type not in {"recruiter_csv", "ats_json", "github_fixture", "resume"}:
        raise HTTPException(status_code=400, detail="Unsupported source_type")

    root = _uploads_root()
    target_dir = root / source_type
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / file.filename

    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    # Return the absolute path, which the ingest pipeline can use directly.
    return {"path": str(dest)}

