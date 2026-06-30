from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable, List

from ..observations import FieldObservation

logger = logging.getLogger(__name__)


def extract_from_recruiter_csv(path: Path) -> List[FieldObservation]:
    """
    Extract observations from a recruiter CSV export.

    Expected columns in the fixture CSV:
      - candidate_ref (unique per row)
      - full_name
      - email
      - phone
      - location
      - headline
      - skills (comma-separated)
    """
    observations: list[FieldObservation] = []

    try:
        with path.open("r", encoding="utf-8") as f:
            reader: Iterable[dict[str, str]] = csv.DictReader(f)
            if reader.fieldnames is None:
                logger.warning("Recruiter CSV %s has no header, skipping", path)
                return []

            for row in reader:
                candidate_ref = (row.get("candidate_ref") or "").strip()
                if not candidate_ref:
                    # Without a candidate_ref we cannot safely associate observations.
                    continue

                source_type = "recruiter_csv"
                source_id = candidate_ref

                def add(field_path: str, value: str) -> None:
                    if value is None:
                        return
                    v = value.strip()
                    if not v:
                        return
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

                add("full_name", row.get("full_name", ""))
                add("headline", row.get("headline", ""))
                add("emails[]", row.get("email", ""))
                add("phones[]", row.get("phone", ""))
                add("location", row.get("location", ""))

                skills_raw = row.get("skills") or ""
                if skills_raw:
                    for skill in skills_raw.split(","):
                        add("skills[]", skill)

    except FileNotFoundError:
        logger.warning("Recruiter CSV file %s not found; returning no observations", path)
        return []
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning(
            "Failed to parse recruiter CSV %s (%s); returning no observations",
            path,
            exc,
        )
        return []

    return observations

