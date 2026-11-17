from sqlalchemy.orm import Session
from app.models.domain import Incident, Evidence, IncidentStatus, EvidenceSourceType
from datetime import datetime, timedelta

def create_buggy_file(archetype: str):
    """Keep incident simulation from overwriting the checked-in sample code.

    The source files are maintained as real, testable examples. Incidents are
    represented by synthetic evidence below rather than by mutating the repo.
    """
    if archetype not in {"crash_loop", "latency_spike", "oom"}:
        raise ValueError(f"Unsupported incident archetype: {archetype}")

def generate_evidence_for_crash_loop() -> list[dict]:
    return [
        {
            "source_type": EvidenceSourceType.LOG,
            "raw_content": "AttributeError: 'NoneType' object has no attribute 'name'\n  File \"auth_service.py\", line 4, in process_user\n    return user.name",
            "structured_content": {"error": "AttributeError", "file": "auth_service.py", "line": 4}
        },
        {
            "source_type": EvidenceSourceType.METRIC,
            "raw_content": "auth_service_pod_restarts_total{pod=\"auth-service-xyz\"} 15",
            "structured_content": {"metric": "pod_restarts", "value": 15}
        },
        {
            "source_type": EvidenceSourceType.K8S_EVENT,
            "raw_content": "Warning: Back-off restarting failed container",
            "structured_content": {"reason": "CrashLoopBackOff"}
        },
        {
            "source_type": EvidenceSourceType.DEPLOY,
            "raw_content": "Deployment auth-service v2.1.0 rolled out",
            "structured_content": {"service": "auth-service", "version": "v2.1.0"}
        }
    ]

def generate_evidence_for_latency_spike() -> list[dict]:
    return [
        {
            "source_type": EvidenceSourceType.LOG,
            "raw_content": "WARN: Query taking longer than 100ms in billing_service",
            "structured_content": {"level": "WARN", "service": "billing_service"}
        },
        {
            "source_type": EvidenceSourceType.METRIC,
            "raw_content": "http_request_duration_seconds{quantile=\"0.99\"} 2.5",
            "structured_content": {"metric": "p99_latency", "value": 2.5}
        },
        {
            "source_type": EvidenceSourceType.DEPLOY,
            "raw_content": "Deployment billing-service v1.4.2 rolled out",
            "structured_content": {"service": "billing-service", "version": "v1.4.2"}
        }
    ]

def generate_evidence_for_oom() -> list[dict]:
    return [
        {
            "source_type": EvidenceSourceType.LOG,
            "raw_content": "INFO: Worker memory usage: 850MB",
            "structured_content": {"level": "INFO", "memory_mb": 850}
        },
        {
            "source_type": EvidenceSourceType.METRIC,
            "raw_content": "container_memory_usage_bytes{pod=\"worker-abc\"} 1073741824",
            "structured_content": {"metric": "memory_usage", "value": 1073741824}
        },
        {
            "source_type": EvidenceSourceType.K8S_EVENT,
            "raw_content": "Warning: OOMKilled container worker",
            "structured_content": {"reason": "OOMKilled"}
        }
    ]

def simulate_incident(db: Session, archetype: str) -> Incident:
    create_buggy_file(archetype)
    
    titles = {
        "crash_loop": "Auth Service CrashLoopBackOff",
        "latency_spike": "Billing Service Latency Spike",
        "oom": "Background Worker OOMKilled"
    }
    
    incident = Incident(
        title=titles.get(archetype, "Unknown Incident"),
        description=f"Auto-generated incident for archetype {archetype}",
        status=IncidentStatus.OPEN,
        severity="HIGH",
        source_type="synthetic"
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    
    if archetype == "crash_loop":
        evidence_data = generate_evidence_for_crash_loop()
    elif archetype == "latency_spike":
        evidence_data = generate_evidence_for_latency_spike()
    elif archetype == "oom":
        evidence_data = generate_evidence_for_oom()
    else:
        evidence_data = []

    for ev_data in evidence_data:
        ev = Evidence(
            incident_id=incident.id,
            source_type=ev_data["source_type"],
            raw_content=ev_data["raw_content"],
            structured_content=ev_data["structured_content"]
        )
        db.add(ev)
    
    db.commit()
    return incident
