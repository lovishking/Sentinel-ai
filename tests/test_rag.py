import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_rag_seed_and_query():
    # 1. Seed the database (mocking embeddings is hard since we depend on Gemini API)
    # This test Assumes GEMINI_API_KEY is configured in the environment.
    seed_response = client.post("/rag/seed")
    if seed_response.status_code != 200:
        print(seed_response.json())
    assert seed_response.status_code == 200
    data = seed_response.json()
    assert data["status"] == "success"
    
    # 2. Query the exact crash_loop error message
    query_text = "AttributeError: 'NoneType' object has no attribute 'name'"
    query_response = client.post("/rag/query", json={"text": query_text})
    assert query_response.status_code == 200
    results = query_response.json()
    
    # We should get some results back
    assert len(results) > 0
    
    # Check if the process_user function from auth_service.py is in the top results
    found_target = False
    for res in results[:3]:  # Top 3
        if res["source_type"] == "code_chunk":
            if res["metadata"].get("file") == "auth_service.py" and res["metadata"].get("name") == "process_user":
                found_target = True
                break
                
    assert found_target, "process_user function from auth_service.py not found in top 3 RAG results for crash_loop error"
