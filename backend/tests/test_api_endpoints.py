from pathlib import Path
from typing import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import Base, get_db
from app.models import candidate  # noqa: F401  (ensure models are imported so tables are registered)


TEST_DB_URL = "sqlite+pysqlite:///:memory:"


engine = create_engine(
    TEST_DB_URL,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Create all tables once for the in-memory database.
Base.metadata.create_all(bind=engine)

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_endpoint_with_sample_sources():
    body = {
        "sources": [
            {"type": "recruiter_csv", "path": str(FIXTURES / "recruiter_sample.csv")},
            {"type": "ats_json", "path": str(FIXTURES / "ats_sample.json")},
        ]
    }
    resp = client.post("/candidates/ingest", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "candidate_ids" in data
    assert len(data["candidate_ids"]) >= 1


def test_ingest_with_missing_file_is_graceful():
    body = {"sources": [{"type": "recruiter_csv", "path": str(FIXTURES / "does_not_exist.csv")}]}
    resp = client.post("/candidates/ingest", json=body)
    assert resp.status_code == 200
    data = resp.json()
    # No observations -> no candidates created.
    assert data["candidate_ids"] == []


def test_ingest_rejects_unknown_source_type():
    body = {"sources": [{"type": "unknown_type", "path": "irrelevant"}]}
    resp = client.post("/candidates/ingest", json=body)
    assert resp.status_code == 400


def test_project_unknown_candidate_returns_404():
    random_id = str(UUID(int=1))
    resp = client.get(f"/candidates/{random_id}/project")
    assert resp.status_code == 404


def test_config_lifecycle_and_projection():
    # First ingest a candidate.
    body = {
        "sources": [
            {"type": "recruiter_csv", "path": str(FIXTURES / "recruiter_sample.csv")},
        ]
    }
    ingest_resp = client.post("/candidates/ingest", json=body)
    assert ingest_resp.status_code == 200
    candidate_id = ingest_resp.json()["candidate_ids"][0]

    # Create a projection config.
    cfg_body = {
        "name": "basic",
        "config": {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        },
    }
    cfg_resp = client.post("/configs", json=cfg_body)
    assert cfg_resp.status_code == 200

    # Use the stored config to project via GET.
    proj_resp = client.get(f"/candidates/{candidate_id}/project", params={"config_name": "basic"})
    assert proj_resp.status_code == 200
    payload = proj_resp.json()
    assert payload["full_name"] == "Alice Doe"
    assert payload["primary_email"] == "alice@example.com"

