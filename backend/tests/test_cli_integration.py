import json
import shutil
from pathlib import Path

from pipeline.cli import main as cli_main


FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_ingest_and_project_end_to_end(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()

    # Reuse existing fixtures for recruiter CSV and ATS JSON.
    shutil.copy(FIXTURES / "recruiter_sample.csv", inputs / "recruiter_sample.csv")
    shutil.copy(FIXTURES / "ats_sample.json", inputs / "ats_sample.json")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "fields": [
                    {"path": "full_name", "type": "string", "required": True},
                    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
                    {"path": "skills", "from": "skills[].name", "type": "string[]"},
                ],
                "include_provenance": False,
                "include_confidence": True,
                "on_missing": "null",
            }
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "out.json"
    db_path = tmp_path / "cli.sqlite"
    db_url = f"sqlite+pysqlite:///{db_path}"

    cli_main(
        [
            "ingest",
            "--inputs",
            str(inputs),
            "--config",
            str(config_path),
            "--out",
            str(out_path),
            "--database-url",
            db_url,
        ]
    )

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "candidates" in data
    assert len(data["candidates"]) >= 1

    first = data["candidates"][0]
    assert "id" in first
    proj = first["projection"]
    # Order of merged candidates is not guaranteed; just assert basic schema.
    assert "full_name" in proj and proj["full_name"]
    assert "primary_email" in proj and proj["primary_email"]
    assert isinstance(proj["skills"], list)


def test_cli_with_invalid_config_raises(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    # One valid input to ensure we get past source discovery.
    shutil.copy(FIXTURES / "recruiter_sample.csv", inputs / "recruiter_sample.csv")

    bad_config = tmp_path / "bad_config.json"
    # Reference an invalid root field to trigger config validation error.
    bad_config.write_text(
        json.dumps({"fields": [{"path": "x", "from": "does_not_exist", "type": "string"}]}),
        encoding="utf-8",
    )

    out_path = tmp_path / "out.json"
    db_path = tmp_path / "cli.sqlite"
    db_url = f"sqlite+pysqlite:///{db_path}"

    try:
        cli_main(
            [
                "ingest",
                "--inputs",
                str(inputs),
                "--config",
                str(bad_config),
                "--out",
                str(out_path),
                "--database-url",
                db_url,
            ]
        )
        assert False, "Expected SystemExit for invalid config"
    except SystemExit:
        pass

