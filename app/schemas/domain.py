from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from app.models.domain import IncidentStatus, EvidenceSourceType

class EvidenceBase(BaseModel):
    source_type: EvidenceSourceType
    raw_content: str
    structured_content: Optional[Any] = None

class EvidenceCreate(EvidenceBase):
    incident_id: int

class EvidenceResponse(EvidenceBase):
    id: int
    incident_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class IncidentBase(BaseModel):
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None
    confidence_score: Optional[float] = None
    source_type: Optional[str] = None

class IncidentCreate(IncidentBase):
    pass

class IncidentResponse(IncidentBase):
    id: int
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    evidence: List[EvidenceResponse] = []
    model_config = ConfigDict(from_attributes=True)

class RAGQuery(BaseModel):
    text: str

class RAGResult(BaseModel):
    id: int
    content: str
    source_type: str
    metadata: Optional[Any] = None
    distance: float

class InvestigationResult(BaseModel):
    root_cause: str
    confidence_score: float
    supporting_evidence: List[str]
    reasoning: str


class FixResponse(BaseModel):
    id: int
    incident_id: int
    diff_content: str
    status: str
    test_results: Optional[Any] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PullRequestResponse(BaseModel):
    id: int
    fix_id: int
    repo: str
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class IncidentReport(BaseModel):
    incident_id: int
    markdown: str


class ArchetypeEval(BaseModel):
    total_incidents: int
    root_cause_accuracy: float
    average_confidence: float
    fix_success_rate: float
    ground_truth_bug: str


class EvalSummary(BaseModel):
    total_incidents: int
    root_cause_accuracy: float
    average_confidence_score: float
    average_time_to_fix_seconds: float
    fix_success_rate: float
    per_archetype: dict[str, ArchetypeEval]

