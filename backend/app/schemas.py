from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None  # YYYY-MM or null
    current: bool = False


class Education(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None  # YYYY-MM


class CandidateProfile(BaseModel):
    id: UUID
    full_name: Optional[str] = None
    headline: Optional[str] = None
    primary_email: Optional[str] = None
    emails: List[str] = []
    phones: List[str] = []
    location: Optional[str] = None
    country: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = []
    experience: List[Experience] = []
    education: List[Education] = []
    overall_confidence: float = Field(ge=0.0, le=1.0)

