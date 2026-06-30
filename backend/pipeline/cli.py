from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base
from app.models import candidate  # noqa: F401  # ensure models are imported
from app.projection import ProjectionConfig, project_profile
from app.schemas import CandidateProfile
from app.services.ingest import SourceSpec, ingest_sources


def _build_source_specs(inputs_dir: Path) -> List[SourceSpec]:
    specs: List[SourceSpec] = []
    for entry in inputs_dir.iterdir():
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix == ".csv":
            specs.append(SourceSpec(type="recruiter_csv", path=str(entry)))
        elif suffix == ".json":
            # For this exercise, treat JSON as ATS blobs by default.
            specs.append(SourceSpec(type="ats_json", path=str(entry)))
        elif suffix in {".pdf", ".doc", ".docx", ".txt"}:
            specs.append(SourceSpec(type="resume", path=str(entry)))
    return specs


def _run_ingest(
    inputs: Path,
    config_path: Path,
    out_path: Path,
    database_url: Optional[str],
) -> None:
    if not inputs.exists() or not inputs.is_dir():
        raise ValueError(f"inputs directory '{inputs}' does not exist or is not a directory")

    try:
        cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"config file '{config_path}' not found")
    except json.JSONDecodeError as exc:
        raise ValueError(f"config file '{config_path}' is not valid JSON: {exc}")

    proj_config = ProjectionConfig.model_validate(cfg_data)

    db_url = database_url or settings.database_url

    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)

    specs = _build_source_specs(inputs)
    with SessionLocal() as db:
        candidates = ingest_sources(db, specs)

        projections: List[dict[str, Any]] = []
        for cand in candidates:
            if cand.profile is None:
                continue
            profile = CandidateProfile.model_validate(cand.profile)
            proj = project_profile(profile, proj_config)
            projections.append({"id": str(cand.id), "projection": proj})

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"candidates": projections}, indent=2), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest sources and project candidates")
    ingest_parser.add_argument("--inputs", required=True, help="Directory containing source files")
    ingest_parser.add_argument("--config", required=True, help="Projection config JSON file")
    ingest_parser.add_argument("--out", required=True, help="Output JSON file path")
    ingest_parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy database URL (defaults to app settings)",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "ingest":
            _run_ingest(
                inputs=Path(args.inputs),
                config_path=Path(args.config),
                out_path=Path(args.out),
                database_url=getattr(args, "database_url", None),
            )
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()

