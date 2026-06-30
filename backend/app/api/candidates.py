from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.candidate import Candidate
from ..projection import ProjectionConfig, project_profile
from ..schemas import CandidateProfile
from ..services.ingest import SourceSpec, ingest_sources


router = APIRouter(prefix="/candidates", tags=["candidates"])


class IngestSource(BaseModel):
    type: str
    path: str
    username: Optional[str] = None


class IngestRequest(BaseModel):
    sources: List[IngestSource]


class IngestResponse(BaseModel):
    candidate_ids: List[UUID]


class ProjectRequest(BaseModel):
    config: ProjectionConfig


@router.post("/ingest", response_model=IngestResponse)
def ingest_candidates(request: IngestRequest, db: Session = Depends(get_db)) -> IngestResponse:
    specs: List[SourceSpec] = []
    for src in request.sources:
        if src.type not in {"recruiter_csv", "ats_json", "github_fixture", "resume"}:
            raise HTTPException(status_code=400, detail=f"Unsupported source type '{src.type}'")
        specs.append(SourceSpec(type=src.type, path=src.path, username=src.username))

    candidates = ingest_sources(db, specs)
    return IngestResponse(candidate_ids=[c.id for c in candidates])


def _get_candidate_or_404(db: Session, candidate_id: UUID) -> CandidateProfile:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.profile is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateProfile.model_validate(candidate.profile)


@router.post("/{candidate_id}/project")
def project_candidate_post(
    candidate_id: UUID,
    request: ProjectRequest,
    db: Session = Depends(get_db),
) -> dict:
    profile = _get_candidate_or_404(db, candidate_id)
    try:
        return project_profile(profile, request.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{candidate_id}/project")
def project_candidate_get(
    candidate_id: UUID,
    config_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    from ..models.candidate import StoredConfig
    from ..projection import ProjectionConfig

    profile = _get_candidate_or_404(db, candidate_id)

    if config_name is None:
        # Simple default projection: name + primary_email.
        config = ProjectionConfig.model_validate(
            {
                "fields": [
                    {"path": "full_name", "type": "string"},
                    {"path": "primary_email", "type": "string"},
                ],
                "on_missing": "null",
            }
        )
    else:
        stored = db.query(StoredConfig).filter(StoredConfig.name == config_name).one_or_none()
        if stored is None:
            raise HTTPException(status_code=404, detail="Config not found")
        try:
            config = ProjectionConfig.model_validate(stored.config_json)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Stored config is invalid: {exc}")

    try:
        return project_profile(profile, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

