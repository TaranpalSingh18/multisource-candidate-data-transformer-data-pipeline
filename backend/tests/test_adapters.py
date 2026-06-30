from pathlib import Path

from app.adapters import (
    extract_from_recruiter_csv,
    extract_from_ats_json,
    extract_from_github_profile_file,
    extract_from_resume,
)
from app.llm import GroqClient


FIXTURES = Path(__file__).parent / "fixtures"


def test_recruiter_csv_empty_produces_no_observations():
    path = FIXTURES / "recruiter_empty.csv"
    observations = extract_from_recruiter_csv(path)
    assert observations == []


def test_recruiter_csv_sample_produces_observations():
    path = FIXTURES / "recruiter_sample.csv"
    observations = extract_from_recruiter_csv(path)
    # We expect at least full_name and email observations.
    field_paths = {obs.field_path for obs in observations}
    assert "full_name" in field_paths
    assert "emails[]" in field_paths


def test_ats_malformed_json_is_handled_gracefully():
    path = FIXTURES / "ats_malformed.json"
    observations = extract_from_ats_json(path)
    assert observations == []


def test_ats_sample_json_produces_observations():
    path = FIXTURES / "ats_sample.json"
    observations = extract_from_ats_json(path)
    assert any(obs.field_path == "full_name" for obs in observations)
    assert any(obs.field_path == "emails[]" for obs in observations)


def test_github_stub_uses_local_fixture():
    path = FIXTURES / "github_profile.json"
    observations = extract_from_github_profile_file(path, username="caroldev")
    assert any(obs.field_path == "full_name" for obs in observations)
    assert any(obs.field_path == "skills[]" for obs in observations)


class _StubGroqClient(GroqClient):
    def extract_resume(self, text: str):
        # Return a payload with no parseable dates to exercise the date handling.
        return {
            "full_name": "Jane Doe",
            "headline": "Senior Software Engineer",
            "emails": ["jane@example.com"],
            "phones": ["+1 212 555 1234"],
            "locations": ["New York"],
            "skills": ["Python", "FastAPI"],
            "experiences": [
                {"company": "Company A", "title": "Engineer", "start": "Summer 2021", "end": "present"}
            ],
            "educations": [],
        }


def test_resume_adapter_with_stub_llm_and_no_dates_file():
    path = FIXTURES / "resume_no_dates.txt"
    observations = extract_from_resume(path, client=_StubGroqClient())
    # We should at least see a full_name and one experience observation.
    field_paths = {obs.field_path for obs in observations}
    assert "full_name" in field_paths
    assert "experience[]", field_paths

