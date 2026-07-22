from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime
import enum
from app.core.database import Base

class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"

class EvidenceSourceType(str, enum.Enum):
    LOG = "log"
    METRIC = "metric"
    K8S_EVENT = "k8s_event"
    DEPLOY = "deploy"

class Incident(Base):
    __tablename__ = 'incidents'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(Enum(IncidentStatus), default=IncidentStatus.OPEN)
    severity = Column(String)
    confidence_score = Column(Float, nullable=True)
    source_type = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    evidence = relationship("Evidence", back_populates="incident")
    agent_runs = relationship("AgentRun", back_populates="incident")
    fixes = relationship("Fix", back_populates="incident")


class Evidence(Base):
    __tablename__ = 'evidence'

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False)
    source_type = Column(Enum(EvidenceSourceType), nullable=False)
    raw_content = Column(Text, nullable=False)
    structured_content = Column(JSONB, nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    incident = relationship("Incident", back_populates="evidence")


class AgentRun(Base):
    __tablename__ = 'agent_runs'

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False)
    agent_name = Column(String, nullable=False)
    input = Column(JSONB, nullable=True)
    output = Column(JSONB, nullable=True)
    status = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", back_populates="agent_runs")


class Fix(Base):
    __tablename__ = 'fixes'

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False)
    diff_content = Column(Text, nullable=False)
    status = Column(String)
    test_results = Column(JSONB, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    incident = relationship("Incident", back_populates="fixes")
    pull_requests = relationship("PullRequest", back_populates="fix")


class PullRequest(Base):
    __tablename__ = 'pull_requests'

    id = Column(Integer, primary_key=True, index=True)
    fix_id = Column(Integer, ForeignKey('fixes.id'), nullable=False)
    repo = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String, nullable=True)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    fix = relationship("Fix", back_populates="pull_requests")


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(3072), nullable=False)
    source_type = Column(String, nullable=False)  # 'code_chunk' or 'past_incident'
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
