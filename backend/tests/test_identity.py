from app.identity import resolve_identity, merge_observations
from app.observations import FieldObservation


def _obs(ref: str, field_path: str, value, source_type: str, source_id: str):
    return FieldObservation(
        candidate_ref=ref,
        field_path=field_path,
        value=value,
        source_type=source_type,
        source_id=source_id,
        method="deterministic",
        raw_confidence=0.95,
    )


def test_identity_merges_on_shared_email():
    observations = [
        _obs("csv-1", "emails[]", "alice@example.com", "recruiter_csv", "csv-1"),
        _obs("ats-1", "emails[]", "alice@example.com", "ats_json", "ats-1"),
    ]
    clusters = resolve_identity(observations)
    # Both refs should end up in a single cluster.
    assert len(clusters) == 1
    assert set(clusters[0]) == {"csv-1", "ats-1"}


def test_identity_does_not_merge_unrelated_candidates():
    observations = [
        _obs("csv-1", "full_name", "Alice Example", "recruiter_csv", "csv-1"),
        _obs("csv-2", "full_name", "Bob Other", "recruiter_csv", "csv-2"),
    ]
    clusters = resolve_identity(observations)
    # Names are different and there is no shared identifier; must remain separate.
    cluster_sets = [set(c) for c in clusters]
    assert {"csv-1"} in cluster_sets
    assert {"csv-2"} in cluster_sets


def test_merge_conflicting_companies_retains_experience_entries():
    observations = [
        _obs(
            "csv-1",
            "experience[]",
            {"company": "Company A", "title": "Engineer", "start": "2020-01", "end": "2021-01"},
            "recruiter_csv",
            "csv-1",
        ),
        _obs(
            "csv-1",
            "experience[]",
            {"company": "Company B", "title": "Engineer", "start": "2021-02", "end": None},
            "ats_json",
            "ats-1",
        ),
    ]
    profiles = merge_observations(observations)
    assert len(profiles) == 1
    profile = profiles[0]
    companies = {exp.company for exp in profile.experience}
    # Both companies should be present in experience provenance.
    assert {"Company A", "Company B"}.issubset(companies)

