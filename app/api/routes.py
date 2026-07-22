from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.domain import (
    IncidentResponse, IncidentCreate, EvidenceResponse, RAGQuery, RAGResult,
    InvestigationResult, FixResponse, PullRequestResponse, IncidentReport, EvalSummary,
)
from app.models.domain import Incident
from app.services.synthetic_evidence import simulate_incident
from app.services.rag import chunk_and_embed_repo, seed_past_incidents, query_knowledge_base

router = APIRouter()

@router.post("/incidents/simulate", response_model=IncidentResponse)
def simulate_new_incident(archetype: str, db: Session = Depends(get_db)):
    """
    Simulate a new incident using the synthetic evidence generator.
    Supported archetypes: crash_loop, latency_spike, oom
    """
    if archetype not in ["crash_loop", "latency_spike", "oom"]:
        raise HTTPException(status_code=400, detail="Invalid archetype")
    
    incident = simulate_incident(db, archetype)
    return incident

@router.get("/incidents", response_model=list[IncidentResponse])
def get_incidents(db: Session = Depends(get_db)):
    """
    Get all incidents.
    """
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).all()
    return incidents

@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    """
    Get incident by ID, including evidence.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@router.post("/rag/seed")
def seed_rag(db: Session = Depends(get_db)):
    """
    Seed the knowledge base with past incidents and code chunks.
    """
    try:
        chunks_added = chunk_and_embed_repo(db)
        incidents_seeded = seed_past_incidents(db)
        return {"status": "success", "chunks_added": chunks_added, "past_incidents_seeded": incidents_seeded}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rag/query", response_model=list[RAGResult])
def query_rag(query: RAGQuery, db: Session = Depends(get_db)):
    """
    Query the knowledge base for top-k results.
    """
    try:
        results = query_knowledge_base(db, query.text)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/incidents/{incident_id}/investigate", response_model=InvestigationResult)
def investigate_incident(incident_id: int, db: Session = Depends(get_db)):
    """
    Run the LangGraph multi-agent investigation pipeline for an incident.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    # Combine evidence
    evidence_texts = [e.raw_content for e in incident.evidence]
    evidence_text = "\n\n".join(evidence_texts)
    
    from app.services.agent_orchestration import investigation_graph, InvestigationState
    from app.models.domain import AgentRun
    from datetime import datetime
    
    initial_state = {
        "incident_id": incident.id,
        "incident_title": incident.title,
        "incident_desc": incident.description or "",
        "evidence_text": evidence_text,
    }
    
    final_output = None
    try:
        # Run graph and persist each node's state
        for step in investigation_graph.stream(initial_state):
            node_name = list(step.keys())[0]
            node_state = step[node_name]
            
            run_record = AgentRun(
                incident_id=incident.id,
                agent_name=node_name,
                input={"evidence_text": evidence_text} if node_name == "TriageAndAnalysis" else None, # Simplified input logging
                output=node_state,
                status="COMPLETED",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            db.add(run_record)
            db.commit()
            
            final_output = node_state
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")
        
    if not final_output:
        raise HTTPException(status_code=500, detail="Graph produced no output")
        
    return InvestigationResult(
        root_cause=final_output.get("root_cause", "Unknown"),
        confidence_score=final_output.get("confidence_score", 0.0),
        supporting_evidence=final_output.get("supporting_evidence", []),
        reasoning=final_output.get("reasoning", "")
    )


@router.post("/incidents/{incident_id}/generate-fix", response_model=FixResponse)
def generate_fix_endpoint(incident_id: int, db: Session = Depends(get_db)):
    """
    Generate a code fix for the incident using the investigation results.
    
    Produces a unified diff, applies it in an isolated copy of sample_repo,
    runs tests to validate, and retries once on failure.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    from app.services.fix_generation import generate_fix
    
    try:
        fix = generate_fix(db, incident)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fix generation failed: {str(e)}")
    
    return fix


@router.post("/incidents/{incident_id}/create-pr", response_model=PullRequestResponse)
def create_pr_endpoint(incident_id: int, db: Session = Depends(get_db)):
    """
    Create a GitHub Pull Request for the incident's generated fix.
    
    Requires a prior successful fix generation (status='applied').
    Creates a branch, commits the patched file, opens a PR with
    a rich description, and labels by confidence tier.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    from app.models.domain import Fix
    
    # Find the latest applied fix for this incident
    fix = (
        db.query(Fix)
        .filter(Fix.incident_id == incident_id, Fix.status == "applied")
        .order_by(Fix.created_at.desc())
        .first()
    )
    if not fix:
        raise HTTPException(
            status_code=400,
            detail="No applied fix found for this incident. Run generate-fix first."
        )
    
    from app.services.github_integration import create_pull_request
    
    try:
        pr_record = create_pull_request(db, incident, fix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PR creation failed: {str(e)}")
    
    return pr_record


@router.get("/incidents/{incident_id}/report", response_model=IncidentReport)
def get_incident_report(incident_id: int, db: Session = Depends(get_db)):
    """
    Generate and return a markdown postmortem report for the incident.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    from app.services.reporting import generate_report

    try:
        markdown = generate_report(db, incident)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

    return IncidentReport(incident_id=incident.id, markdown=markdown)


@router.get("/eval/summary", response_model=EvalSummary)
def get_eval_summary(db: Session = Depends(get_db)):
    """
    Return evaluation metrics across all synthetic incident runs.

    Real numbers computed from actual DB data — not hardcoded.
    Compares root cause identifications against known archetype ground truth.
    """
    from app.services.reporting import get_eval_summary as compute_eval

    try:
        return compute_eval(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eval computation failed: {str(e)}")
