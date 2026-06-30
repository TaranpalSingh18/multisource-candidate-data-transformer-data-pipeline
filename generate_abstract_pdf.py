from textwrap import wrap

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


ABSTRACT_TEXT = """This project is a backend-first, multi-source candidate data transformer designed to take messy, heterogeneous talent data (recruiter CSVs, ATS JSON, GitHub activity, and resumes via LLM) and turn it into a single canonical candidate profile in Postgres, with config-driven JSON projections exposed over FastAPI and a small React UI. The core design decision is to hard-separate ingestion and merging from output shape: the system always normalizes and merges into an internal CandidateProfile, and only then maps that canonical model into whatever JSON a caller needs through a runtime ProjectionConfig. This decoupling is crucial because consumers (downstream apps, reports, APIs) evolve faster than sources; changing a report or integration no longer requires touching ETL logic or database schema.

To handle noisy, partial, and conflicting inputs, I built an observation-based ingestion layer. Each adapter (recruiter_csv, ats_json, github_fixture, resume_llm) converts raw files into structured FieldObservation records instead of trying to guess the “truth” up front. A normalization module standardizes key fields (phones to E.164, countries to ISO codes, years/months to canonical formats) so later logic can be deterministic. All adapters are intentionally defensive: malformed CSVs, broken JSON, or missing files result in “no observations + clear logs” rather than a crashed pipeline. This makes the system safe to run in batch or via the UI on unvetted data—critical in real recruiting environments where source quality is outside your control.

On top of observations, I implemented an identity resolution and merge engine that clusters inputs into real-world people and builds the canonical CandidateProfile. It uses blocking rules (shared email/phone/name) plus fuzzy scoring (rapidfuzz) and source weighting to decide which records belong together, then persists both the merged profile and all raw observations into Postgres. This design matters because it preserves provenance and ambiguity: conflicting experiences, titles, or skills from different sources are not silently overwritten; they remain visible in arrays on the canonical profile, with an overall_confidence score to signal reliability. That combination—canonical view plus auditable raw history—is what makes the data trustworthy for downstream automation and analytics.

The projection layer is a separate, first-class component that applies a JSONPath-like ProjectionConfig to any canonical profile, supporting paths such as emails[0], skills[].name, or experience[0].company, along with type assertions and on_missing behavior (null, omit, or error). Projection configs are stored and versioned in a projection_configs table and can also be sent inline to the API, so new consumers can define their exact JSON contract without a deployment. This is extremely important for integration velocity: a BI dashboard, CRM sync, or scoring model can each request a different view over the same underlying candidate without creating a new table, a new ETL job, or a code fork.

The system is surfaced through a FastAPI backend and a minimal React/Vite frontend, wired together via docker-compose with Postgres and automatic Alembic migrations. The UI lets users upload sample sources, tweak projection configs, run ingestion + projection in one click, and visually inspect the resulting JSON, making the pipeline observable and debuggable without dropping into the CLI. End-to-end tests cover adapters, normalization, identity resolution, projection behavior, and main API flows to guard against regressions. Overall, the design focuses on making candidate data unified, explainable, and re-shapable on demand, which is exactly what’s required to turn fragmented recruiting data into a reliable, reusable asset."""


def create_pdf(output_path: str = "technical_abstract.pdf") -> None:
    canvas_obj = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    left_margin = 72  # 1 inch
    right_margin = 72
    top_margin = 72
    bottom_margin = 72

    max_width = width - left_margin - right_margin
    line_height = 14

    # Approximate chars per line for wrapping (depends on font size)
    chars_per_line = 95

    y = height - top_margin

    for paragraph in ABSTRACT_TEXT.split("\n\n"):
        lines = wrap(paragraph, chars_per_line)
        for line in lines:
            if y < bottom_margin:
                canvas_obj.showPage()
                y = height - top_margin
            canvas_obj.drawString(left_margin, y, line)
            y -= line_height
        # Extra space between paragraphs
        y -= line_height

    canvas_obj.save()


if __name__ == "__main__":
    create_pdf()

