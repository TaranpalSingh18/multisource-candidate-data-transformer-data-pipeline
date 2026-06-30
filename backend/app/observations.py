from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


MethodType = Literal["deterministic", "llm"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class FieldObservation:
    """
    Ingestion-layer observation for a single logical field.
    This is intentionally decoupled from the SQLAlchemy RawObservation model.
    """

    candidate_ref: str
    field_path: str
    value: Any
    source_type: str
    source_id: str
    method: MethodType
    raw_confidence: float = 1.0
    extracted_at: datetime = field(default_factory=utc_now)

