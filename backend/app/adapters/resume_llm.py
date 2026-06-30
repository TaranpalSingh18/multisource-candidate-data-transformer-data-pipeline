from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pdfplumber
import docx  # type: ignore[import]

from ..llm import GroqClient, LLMNotConfiguredError
from ..normalization import normalize_year_month
from ..observations import FieldObservation

logger = logging.getLogger(__name__)


def _extract_text_from_pdf(path: Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(texts)


def _extract_text_from_docx(path: Path) -> str:
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _load_resume_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_from_pdf(path)
    if suffix in {".docx", ".doc"}:
        return _extract_text_from_docx(path)
    # Fallback: treat as plain text
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_from_resume(path: Path, client: GroqClient | None = None) -> List[FieldObservation]:
    """
    Extract observations from a resume using Groq in JSON mode.

    If GROQ_API_KEY is not configured or the LLM call fails, returns an empty list.
    """
    observations: list[FieldObservation] = []

    try:
        text = _load_resume_text(path)
    except FileNotFoundError:
        logger.warning("Resume file %s not found; returning no observations", path)
        return []
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning("Failed to read resume file %s (%s); returning no observations", path, exc)
        return []

    if not text.strip():
        logger.info("Resume file %s contains no parseable text", path)
        return []

    client = client or GroqClient()
    try:
        payload = client.extract_resume(text)
    except LLMNotConfiguredError:
        logger.warning("GROQ_API_KEY not configured; skipping resume LLM extraction")
        return []
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning("Groq extraction failed for %s (%s); returning no observations", path, exc)
        return []

    candidate_ref = payload.get("full_name") or "resume"
    source_type = "resume"
    source_id = path.name

    def add(field_path: str, value) -> None:
        if value is None:
            return
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return
        else:
            v = value
        observations.append(
            FieldObservation(
                candidate_ref=candidate_ref,
                field_path=field_path,
                value=v,
                source_type=source_type,
                source_id=source_id,
                method="llm",
                raw_confidence=0.75,
            )
        )

    add("full_name", payload.get("full_name"))
    add("headline", payload.get("headline"))

    for email in payload.get("emails") or []:
        add("emails[]", email)

    for phone in payload.get("phones") or []:
        add("phones[]", phone)

    for loc in payload.get("locations") or []:
        add("location", loc)

    for skill in payload.get("skills") or []:
        add("skills[]", skill)

    for exp in payload.get("experiences") or []:
        company = exp.get("company")
        title = exp.get("title")
        start = normalize_year_month(exp.get("start", "") or "")
        end = normalize_year_month(exp.get("end", "") or "")
        add(
            "experience[]",
            {
                "company": company,
                "title": title,
                "start": start,
                "end": end,
            },
        )

    for edu in payload.get("educations") or []:
        school = edu.get("school")
        degree = edu.get("degree")
        field = edu.get("field_of_study")
        start = normalize_year_month(edu.get("start", "") or "")
        end = normalize_year_month(edu.get("end", "") or "")
        add(
            "education[]",
            {
                "school": school,
                "degree": degree,
                "field_of_study": field,
                "start": start,
                "end": end,
            },
        )

    return observations

