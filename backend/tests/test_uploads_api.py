from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_upload_recruiter_csv_creates_path():
    content = b"candidate_ref,full_name\ncsv-x,Test Person\n"
    files = {"file": ("sample.csv", BytesIO(content), "text/csv")}

    resp = client.post("/uploads/recruiter_csv", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    # Basic sanity: returned path should end with the file name we sent.
    assert data["path"].endswith("sample.csv")

