import json
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import google.generativeai as genai

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.rag import query_knowledge_base

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    
class InvestigationState(TypedDict):
    incident_id: int
    incident_title: str
    incident_desc: str
    evidence_text: str
    
    incident_type: Optional[str]
    error_signature: Optional[str]
    
    retrieved_context: Optional[List[Dict[str, Any]]]
    min_distance: Optional[float]
    
    root_cause: Optional[str]
    confidence_score: Optional[float]
    supporting_evidence: Optional[List[str]]
    reasoning: Optional[str]

def get_gemini_response(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    # gemini-flash-latest
    model = genai.GenerativeModel("gemini-flash-latest")
    response = model.generate_content(prompt)
    return response.text

def triage_and_analyze(state: InvestigationState) -> InvestigationState:
    prompt = f"""
    You are an expert SRE Triager. Analyze the following incident and evidence.
    Title: {state.get('incident_title')}
    Description: {state.get('incident_desc')}
    Evidence: {state.get('evidence_text')}
    
    Provide your output STRICTLY as a JSON object with exactly two keys:
    "incident_type": string (one of "crash", "latency", "resource", "other")
    "error_signature": string (a concise 1-2 sentence plain-text summary of the exact error pattern, anomaly, or stack trace found in the evidence, useful for semantic search).
    """
    try:
        response_text = get_gemini_response(prompt)
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].strip()
        else:
            json_str = response_text.strip()
            
        data = json.loads(json_str)
        return {
            "incident_type": data.get("incident_type", "other"),
            "error_signature": data.get("error_signature", "")
        }
    except Exception as e:
        return {
            "incident_type": "other",
            "error_signature": state.get('incident_title')
        }

def code_context(state: InvestigationState) -> InvestigationState:
    query = state.get('error_signature') or state.get('incident_title')
    db = SessionLocal()
    try:
        results = query_knowledge_base(db, query, top_k=3)
        min_dist = min([r['distance'] for r in results]) if results else 999.0
        return {
            "retrieved_context": results,
            "min_distance": min_dist
        }
    finally:
        db.close()

def root_cause_synthesizer(state: InvestigationState) -> InvestigationState:
    min_dist = state.get('min_distance', 999.0)
    # Hard fallback for insufficient evidence
    if min_dist > 1.2:
        return {
            "root_cause": "insufficient evidence",
            "confidence_score": 0.0,
            "supporting_evidence": [],
            "reasoning": f"Max similarity threshold breached. Minimum L2 distance was {min_dist:.2f} (> 1.2)."
        }
    
    context_str = json.dumps(state.get('retrieved_context', []), indent=2)
    prompt = f"""
    You are an expert Root Cause Synthesizer. Analyze the incident, evidence, and retrieved knowledge base context.
    
    Incident Title: {state.get('incident_title')}
    Evidence: {state.get('evidence_text')}
    Extracted Signature: {state.get('error_signature')}
    Retrieved Context (from codebase/past incidents):
    {context_str}
    
    Provide your output STRICTLY as a JSON object with exactly four keys:
    "root_cause": string (the identified root cause)
    "confidence_score": float (between 0.0 and 1.0, based on evidence agreement and similarity. Document the calculation in reasoning)
    "supporting_evidence": list of strings (citations from the logs/metrics or code context)
    "reasoning": string (how you calculated the confidence score and arrived at the conclusion)
    """
    
    try:
        response_text = get_gemini_response(prompt)
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].strip()
        else:
            json_str = response_text.strip()
            
        data = json.loads(json_str)
        return {
            "root_cause": data.get("root_cause", "Unknown"),
            "confidence_score": float(data.get("confidence_score", 0.0)),
            "supporting_evidence": data.get("supporting_evidence", []),
            "reasoning": data.get("reasoning", "")
        }
    except Exception as e:
        return {
            "root_cause": "Error synthesizing root cause",
            "confidence_score": 0.0,
            "supporting_evidence": [],
            "reasoning": str(e)
        }

# Build LangGraph
workflow = StateGraph(InvestigationState)

workflow.add_node("TriageAndAnalysis", triage_and_analyze)
workflow.add_node("CodeContext", code_context)
workflow.add_node("RootCauseSynthesizer", root_cause_synthesizer)

workflow.set_entry_point("TriageAndAnalysis")
workflow.add_edge("TriageAndAnalysis", "CodeContext")
workflow.add_edge("CodeContext", "RootCauseSynthesizer")
workflow.add_edge("RootCauseSynthesizer", END)

investigation_graph = workflow.compile()
