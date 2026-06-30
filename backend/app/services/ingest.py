from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

from sqlalchemy.orm import Session

from ..adapters import (
    extract_from_recruiter_csv,
    extract_from_ats_json,
    extract_from_github_profile_file,
    extract_from_resume,
)
from ..identity import cluster_and_merge
from ..models.candidate import Candidate, RawObservation
from ..observations import FieldObservation


SourceType = Literal["recruiter_csv", "ats_json", "github_fixture", "resume"]


@dataclass
class SourceSpec:
    type: SourceType
    path: str
    username: Optional[str] = None  # for github_fixture


def _run_adapters(sources: List[SourceSpec]) -> List[FieldObservation]:
    observations: List[FieldObservation] = []
    for spec in sources:
        p = Path(spec.path)
        if spec.type == "recruiter_csv":
            observations.extend(extract_from_recruiter_csv(p))
        elif spec.type == "ats_json":
            observations.extend(extract_from_ats_json(p))
        elif spec.type == "github_fixture":
            username = spec.username or p.stem
            observations.extend(extract_from_github_profile_file(p, username=username))
        elif spec.type == "resume":
            observations.extend(extract_from_resume(p))
    return observations


def ingest_sources(db: Session, sources: List[SourceSpec]) -> List[Candidate]:
    """
    End-to-end ingestion:
      - run per-source adapters to collect FieldObservation objects
      - run identity resolution + merge engine
      - upsert Candidate rows with canonical profile JSON
      - persist RawObservation rows linked to candidate_id
    """
    observations = _run_adapters(sources)
    if not observations:
        return []

    profiles, ref_to_id = cluster_and_merge(observations)

    # Upsert candidates by canonical id.
    candidates_by_id: dict[str, Candidate] = {}
    for profile in profiles:
        existing: Candidate | None = db.get(Candidate, profile.id)
        profile_json = profile.model_dump(mode="json")
        if existing is None:
            candidate = Candidate(
                id=profile.id,
                profile=profile_json,
                overall_confidence=profile.overall_confidence,
            )
            db.add(candidate)
            candidates_by_id[str(profile.id)] = candidate
        else:
            existing.profile = profile_json
            existing.overall_confidence = profile.overall_confidence
            candidates_by_id[str(profile.id)] = existing

    # Persist raw observations with resolved candidate_id.
    for obs in observations:
        candidate_uuid = ref_to_id.get(obs.candidate_ref)
        raw = RawObservation(
            candidate_id=candidate_uuid,
            source_type=obs.source_type,
            source_id=obs.source_id,
            field_path=obs.field_path,
            raw_value=obs.value,
            normalized_value=obs.value,
            method=obs.method,
            confidence=obs.raw_confidence,
            extracted_at=obs.extracted_at,
        )
        db.add(raw)

    db.commit()
    return list(candidates_by_id.values())

