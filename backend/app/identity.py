from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Iterable, Optional

from rapidfuzz import fuzz

from .normalization import normalize_phone, normalize_country
from .observations import FieldObservation
from .schemas import CandidateProfile, Skill, Experience, Education


# Source trust tiers: higher is more trusted.
SOURCE_TIERS: Dict[str, int] = {
    "recruiter_csv": 4,
    "ats_json": 4,
    "github": 3,
    "linkedin": 3,
    "resume": 2,
    "notes": 1,
}

# Scoring weights for identity resolution.
WEIGHT_EMAIL = 0.7
WEIGHT_PHONE = 0.5
WEIGHT_NAME = 0.3
WEIGHT_CORROBORATION = 0.1
MERGE_THRESHOLD = 0.7


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_name(name: str) -> str:
    return " ".join((name or "").split()).lower()


@dataclass
class CandidateFeatures:
    candidate_ref: str
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    name: Optional[str] = None
    skills: Set[str] = field(default_factory=set)
    companies: Set[str] = field(default_factory=set)


def _build_features(observations: Iterable[FieldObservation]) -> Dict[str, CandidateFeatures]:
    features: Dict[str, CandidateFeatures] = {}
    for obs in observations:
        cf = features.setdefault(obs.candidate_ref, CandidateFeatures(candidate_ref=obs.candidate_ref))
        if obs.field_path == "full_name" and isinstance(obs.value, str):
            cf.name = _normalize_name(obs.value)
        elif obs.field_path == "emails[]" and isinstance(obs.value, str):
            cf.emails.add(_normalize_email(obs.value))
        elif obs.field_path == "phones[]" and isinstance(obs.value, str):
            norm = normalize_phone(obs.value)
            if norm.valid and norm.e164:
                cf.phones.add(norm.e164)
        elif obs.field_path == "skills[]" and isinstance(obs.value, str):
            cf.skills.add(obs.value.strip().lower())
        elif obs.field_path == "experience[]" and isinstance(obs.value, dict):
            company = (obs.value.get("company") or "").strip()
            if company:
                cf.companies.add(company.lower())
    return features


def _pair_score(a: CandidateFeatures, b: CandidateFeatures) -> float:
    score = 0.0

    if a.emails & b.emails:
        score += WEIGHT_EMAIL
    if a.phones & b.phones:
        score += WEIGHT_PHONE

    if a.name and b.name:
        name_sim = fuzz.WRatio(a.name, b.name) / 100.0
        score += WEIGHT_NAME * name_sim

    if a.companies & b.companies and a.skills & b.skills:
        score += WEIGHT_CORROBORATION

    return min(score, 1.0)


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent: Dict[str, str] = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def clusters(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for x in self.parent:
            root = self.find(x)
            out.setdefault(root, []).append(x)
        return out


def resolve_identity(observations: List[FieldObservation]) -> List[List[str]]:
    """
    Group candidate_refs for the same logical candidate.
    Returns a list of clusters, each being a list of candidate_refs.
    """
    if not observations:
        return []

    features = _build_features(observations)
    refs = sorted(features.keys())
    uf = _UnionFind(refs)

    # Blocking: compare only pairs that share at least one blocking key.
    for i, ref_a in enumerate(refs):
        fa = features[ref_a]
        for ref_b in refs[i + 1 :]:
            fb = features[ref_b]

            if not (fa.emails & fb.emails or fa.phones & fb.phones or (fa.name and fb.name and fa.name == fb.name)):
                continue

            score = _pair_score(fa, fb)
            if score >= MERGE_THRESHOLD:
                uf.union(ref_a, ref_b)

    return list(uf.clusters().values())


def _source_tier(source_type: str) -> int:
    return SOURCE_TIERS.get(source_type, 1)


def _group_observations_by_field(
    observations: Iterable[FieldObservation],
) -> Dict[str, List[FieldObservation]]:
    grouped: Dict[str, List[FieldObservation]] = {}
    for obs in observations:
        grouped.setdefault(obs.field_path, []).append(obs)
    return grouped


def _choose_scalar_value(group: List[FieldObservation]) -> Tuple[Optional[str], float]:
    if not group:
        return None, 0.0

    # Normalize values to strings and bucket them.
    buckets: Dict[str, List[FieldObservation]] = {}
    for obs in group:
        if obs.value is None:
            continue
        val = str(obs.value).strip()
        if not val:
            continue
        buckets.setdefault(val, []).append(obs)

    if not buckets:
        return None, 0.0

    # If we have corroboration (same value from 2+ independent sources), that value wins.
    best_value = None
    best_score = -1.0
    for value, obs_list in buckets.items():
        num_sources = len({o.source_type for o in obs_list})
        max_tier = max(_source_tier(o.source_type) for o in obs_list)
        if num_sources >= 2:
            score = 0.8 + 0.05 * min(num_sources, 3)  # cap around 0.95
        else:
            score = 0.5 + 0.1 * max_tier
        if score > best_score:
            best_score = score
            best_value = value

    return best_value, min(best_score, 0.99)


def _merge_cluster(
    cluster_refs: List[str],
    observations: List[FieldObservation],
) -> CandidateProfile:
    cluster_obs = [o for o in observations if o.candidate_ref in cluster_refs]
    grouped = _group_observations_by_field(cluster_obs)

    # Deterministically derive candidate_id from sorted candidate_refs.
    cluster_key = "|".join(sorted(cluster_refs))
    candidate_id = uuid.uuid5(uuid.NAMESPACE_URL, f"candidate:{cluster_key}")

    full_name, _ = _choose_scalar_value(grouped.get("full_name", []))
    headline, _ = _choose_scalar_value(grouped.get("headline", []))
    primary_email, _ = _choose_scalar_value(grouped.get("emails[]", []))
    location, _ = _choose_scalar_value(grouped.get("location", []))

    # Emails and phones: union with simple per-element confidence.
    email_values = {str(o.value).strip() for o in grouped.get("emails[]", []) if o.value}
    phone_values = {str(o.value).strip() for o in grouped.get("phones[]", []) if o.value}

    skills: Dict[str, float] = {}
    for obs in grouped.get("skills[]", []):
        if not isinstance(obs.value, str):
            continue
        name = obs.value.strip()
        if not name:
            continue
        tier = _source_tier(obs.source_type)
        skills[name] = max(skills.get(name, 0.0), 0.4 + 0.1 * tier)

    experience_entries: List[Experience] = []
    for obs in grouped.get("experience[]", []):
        if not isinstance(obs.value, dict):
            continue
        experience_entries.append(
            Experience(
                company=obs.value.get("company"),
                title=obs.value.get("title"),
                start=obs.value.get("start"),
                end=obs.value.get("end"),
                current=False,
            )
        )

    education_entries: List[Education] = []
    for obs in grouped.get("education[]", []):
        if not isinstance(obs.value, dict):
            continue
        education_entries.append(
            Education(
                school=obs.value.get("school"),
                degree=obs.value.get("degree"),
                field_of_study=obs.value.get("field_of_study"),
                start=obs.value.get("start"),
                end=obs.value.get("end"),
            )
        )

    # Very simple overall confidence rollup: average of non-zero field confidences.
    field_confidences: List[float] = []
    for field_name in ["full_name", "headline", "emails[]", "phones[]", "location"]:
        value, conf = _choose_scalar_value(grouped.get(field_name, []))
        if value is not None:
            field_confidences.append(conf)

    overall_confidence = sum(field_confidences) / len(field_confidences) if field_confidences else 0.0

    return CandidateProfile(
        id=candidate_id,
        full_name=full_name,
        headline=headline,
        primary_email=primary_email,
        emails=sorted(email_values),
        phones=sorted(phone_values),
        location=location,
        country=None,
        years_experience=None,
        skills=[Skill(name=name, confidence=conf) for name, conf in sorted(skills.items())],
        experience=experience_entries,
        education=education_entries,
        overall_confidence=overall_confidence,
    )


def merge_observations(observations: List[FieldObservation]) -> List[CandidateProfile]:
    """
    Full Phase 2 engine: resolve identities into clusters and produce canonical
    CandidateProfile objects per cluster.
    """
    clusters = resolve_identity(observations)
    return [_merge_cluster(cluster_refs, observations) for cluster_refs in clusters]


def cluster_and_merge(
    observations: List[FieldObservation],
) -> Tuple[List[CandidateProfile], Dict[str, uuid.UUID]]:
    """
    Helper that returns both merged profiles and a mapping from candidate_ref
    to canonical candidate_id, for use when persisting RawObservation rows.
    """
    clusters = resolve_identity(observations)
    profiles: List[CandidateProfile] = []
    ref_to_id: Dict[str, uuid.UUID] = {}
    for cluster_refs in clusters:
        profile = _merge_cluster(cluster_refs, observations)
        profiles.append(profile)
        for ref in cluster_refs:
            ref_to_id[ref] = profile.id
    return profiles, ref_to_id

