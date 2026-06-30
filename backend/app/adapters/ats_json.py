from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from ..observations import FieldObservation

logger = logging.getLogger(__name__)

# Explicit mapping from ATS-specific keys to canonical field paths.
FIELD_MAPPING: Dict[str, str] = {
    "name_full": "full_name",
    "email_primary": "emails[]",
    "phone_mobile": "phones[]",
    "location_city": "location",
    "headline": "headline",
}


def extract_from_ats_json(path: Path) -> List[FieldObservation]:
    """
    Extract observations from an ATS JSON blob.

    Expected structure in the fixture JSON:
      {
        "candidates": [
          {
            "id": "ats-1",
            "name_full": "...",
            "email_primary": "...",
            ...
          }
        ]
      }
    """
    observations: list[FieldObservation] = []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("ATS JSON file %s not found; returning no observations", path)
        return []
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning("Failed to read ATS JSON %s (%s); returning no observations", path, exc)
        return []

    try:
        data: Dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Malformed ATS JSON in %s; returning no observations", path)
        return []

    candidates = data.get("candidates") or []
    if not isinstance(candidates, list):
        logger.warning("ATS JSON %s has no 'candidates' list; returning no observations", path)
        return []

    for item in candidates:
        if not isinstance(item, dict):
            continue

        candidate_ref = str(item.get("id") or "").strip()
        if not candidate_ref:
            continue

        source_type = "ats_json"
        source_id = candidate_ref

        for ats_key, field_path in FIELD_MAPPING.items():
            value = item.get(ats_key)
            if value is None:
                continue
            v = str(value).strip()
            if not v:
                continue
            observations.append(
                FieldObservation(
                    candidate_ref=candidate_ref,
                    field_path=field_path,
                    value=v,
                    source_type=source_type,
                    source_id=source_id,
                    method="deterministic",
                    raw_confidence=0.95,
                )
            )

    return observations

