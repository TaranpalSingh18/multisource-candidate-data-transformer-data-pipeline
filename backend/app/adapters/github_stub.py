from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from ..observations import FieldObservation


logger = logging.getLogger(__name__)


def extract_from_github_profile_file(path: Path, username: str) -> List[FieldObservation]:
    """
    Deterministic GitHub adapter using a local JSON fixture instead of live API calls.

    Expected JSON structure in the fixture:
      {
        "profile": {"name": "...", "bio": "..."},
        "languages": ["Python", "TypeScript"]
      }
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("GitHub fixture file %s not found; returning no observations", path)
        return []
    except Exception as exc:  # safety net
        logger.warning("Failed to read GitHub fixture %s (%s); returning no observations", path, exc)
        return []

    try:
        data: Dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Malformed GitHub fixture JSON in %s; returning no observations", path)
        return []

    profile = data.get("profile") or {}
    languages = data.get("languages") or []

    observations: list[FieldObservation] = []
    candidate_ref = username
    source_type = "github"
    source_id = username

    def add(field_path: str, value: Any) -> None:
        if value is None:
            return
        v = str(value).strip()
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
                raw_confidence=0.9,
            )
        )

    add("full_name", profile.get("name"))
    add("headline", profile.get("bio"))

    for lang in languages:
        add("skills[]", lang)

    return observations

