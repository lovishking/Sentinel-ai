from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_investigate_incident():
    # 1. Simulate an incident
    response = client.post("/incidents/simulate?archetype=crash_loop")
    assert response.status_code == 200
    incident = response.json()
    incident_id = incident["id"]
    
    assert incident["title"] == "Auth Service CrashLoopBackOff"
    
    # 2. Run investigation
    response = client.post(f"/incidents/{incident_id}/investigate")
    
    # Can take some time since it hits the API 2 times
    if response.status_code != 200:
        print(response.json())
        
    assert response.status_code == 200
    result = response.json()
    
    # We expect confidence_score and root_cause to be populated
    assert "confidence_score" in result
    assert "root_cause" in result
    assert "supporting_evidence" in result
    assert "reasoning" in result
    
    print("\n--- FINAL SYNTHESIZED ROOT CAUSE ---")
    print(f"Confidence: {result['confidence_score']}")
    print(f"Root Cause: {result['root_cause']}")
    print(f"Reasoning: {result['reasoning']}")
