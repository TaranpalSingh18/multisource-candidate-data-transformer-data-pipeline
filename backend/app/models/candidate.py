import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Enum,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..db import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Canonical profile snapshot and rollup confidence.
    profile = Column(JSON, nullable=True)
    overall_confidence = Column(Float, nullable=True)

    identity_links = relationship("CandidateIdentityLink", back_populates="candidate")
    observations = relationship("RawObservation", back_populates="candidate")


class SourceTypeEnum(str, Enum):  # type: ignore[misc]
    RECRUITER_CSV = "recruiter_csv"
    ATS_JSON = "ats_json"
    GITHUB = "github"
    RESUME = "resume"
    NOTES = "notes"


class MethodEnum(str, Enum):  # type: ignore[misc]
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class RawObservation(Base):
    __tablename__ = "raw_observations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    field_path = Column(String, nullable=False)
    raw_value = Column(JSON, nullable=False)
    normalized_value = Column(JSON, nullable=True)
    method = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    extracted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="observations")


class CandidateIdentityLink(Base):
    __tablename__ = "candidate_identity_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    matched_on = Column(String, nullable=False)
    score = Column(Float, nullable=False)

    candidate = relationship("Candidate", back_populates="identity_links")


class StoredConfig(Base):
    __tablename__ = "projection_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    config_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

