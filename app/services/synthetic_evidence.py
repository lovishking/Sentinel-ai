import os
from sqlalchemy.orm import Session
from app.models.domain import Incident, Evidence, IncidentStatus, EvidenceSourceType
from datetime import datetime, timedelta

def create_buggy_file(archetype: str):
    repo_path = "sample_repo"
    os.makedirs(repo_path, exist_ok=True)
    
    if archetype == "crash_loop":
        file_path = os.path.join(repo_path, "auth_service.py")
        content = """def process_user(user_id: int):
    # Bug: user object can be None if not found, causing crash
    user = get_user_from_db(user_id)
    return user.name

def get_user_from_db(user_id: int):
    # Dummy DB return
    return None
"""
        with open(file_path, "w") as f:
            f.write(content)
            
    elif archetype == "latency_spike":
        file_path = os.path.join(repo_path, "billing_service.py")
        content = """def calculate_total_billing(user_ids: list):
    # Bug: N+1 query issue
    total = 0
    for uid in user_ids:
        # DB hit inside loop
        amount = get_user_balance(uid)
        total += amount
    return total

def get_user_balance(user_id: int):
    import time
    time.sleep(0.1) # Simulate slow query
    return 10.0
"""
        with open(file_path, "w") as f:
            f.write(content)
            
    elif archetype == "oom":
        file_path = os.path.join(repo_path, "worker.py")
        content = """global_cache = []

def process_event(event: dict):
    # Bug: Unbounded cache list causes memory leak
    global_cache.append(event)
    # Never cleared!
    return True
"""
        with open(file_path, "w") as f:
            f.write(content)

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
