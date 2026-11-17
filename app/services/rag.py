import os
import ast
import hashlib
import re
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.domain import KnowledgeChunk, Incident, Fix, IncidentStatus
from app.core.config import settings
from datetime import datetime, timedelta
import random

try:
    import google.generativeai as genai
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
except ImportError:
    genai = None

def _local_embedding(text_content: str) -> list[float]:
    """Create a stable 3072-dimensional fallback vector without network access."""
    vector = [0.0] * 3072
    for token in _tokens(text_content):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % len(vector)
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    magnitude = sum(value * value for value in vector) ** 0.5
    return [value / magnitude for value in vector] if magnitude else vector


def _tokens(text_content: str) -> list[str]:
    # Split camel case too, so NoneType and none type can match.
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", text_content)
    return re.findall(r"[a-z0-9]+", normalized.lower())


def get_embedding(text_content: str) -> list[float]:
    """Use Gemini embeddings when available, with a deterministic local fallback."""
    if genai and settings.GEMINI_API_KEY:
        try:
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text_content,
            )
            return result["embedding"]
        except Exception:
            # Quota limits and transient network errors should not disable local use.
            pass
    return _local_embedding(text_content)

def chunk_and_embed_repo(db: Session):
    repo_path = "sample_repo"
    if not os.path.exists(repo_path):
        return 0

    chunks_added = 0
    for filename in os.listdir(repo_path):
        if not filename.endswith(".py"):
            continue
            
        filepath = os.path.join(repo_path, filename)
        with open(filepath, "r") as f:
            content = f.read()
            
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno - 1
                end_line = node.end_lineno
                
                chunk_code = "\n".join(content.splitlines()[start_line:end_line])
                
                # Check if chunk already exists
                existing = db.query(KnowledgeChunk).filter(
                    KnowledgeChunk.source_type == 'code_chunk',
                    KnowledgeChunk.metadata_json['file'].astext == filename,
                    KnowledgeChunk.metadata_json['name'].astext == node.name
                ).first()
                
                if not existing:
                    embedding = get_embedding(chunk_code)
                    chunk = KnowledgeChunk(
                        content=chunk_code,
                        embedding=embedding,
                        source_type='code_chunk',
                        metadata_json={
                            "file": filename,
                            "name": node.name,
                            "type": type(node).__name__
                        }
                    )
                    db.add(chunk)
                    chunks_added += 1
                    
    db.commit()
    return chunks_added


def seed_past_incidents(db: Session):
    # Check if we already seeded past incidents
    count = db.query(KnowledgeChunk).filter(KnowledgeChunk.source_type == 'past_incident').count()
    if count > 0:
        return 0
        
    past_incidents_data = [
        ("Auth Service crash loop", "CrashLoopBackOff caused by process_user encountering NoneType when user not found in DB. Fixed by adding None check before accessing user.name.", "auth_service.py"),
        ("Billing service latency", "High p99 latency in billing_service due to N+1 queries in calculate_total_billing. Fixed by using a bulk query get_users_balances.", "billing_service.py"),
        ("Worker OOMKilled", "Background worker OOMKilled because global_cache list grew unbounded in process_event. Fixed by adding a cache eviction policy and max size.", "worker.py"),
        ("Checkout service crash", "CrashLoopBackOff in checkout caused by process_order hitting KeyError on missing 'item_id'. Fixed by using dict.get() with default.", "checkout.py"),
        ("API gateway latency", "Latency spike in API gateway due to missing index on users table causing slow scans. Fixed by adding index on users.email.", "gateway.py"),
        ("Report generator OOM", "OOMKilled in report_generator loading entire dataset into memory at once. Fixed by streaming the database cursor.", "report.py"),
        ("Payment gateway timeout", "Latency spike in payment gateway waiting for 3rd party API without a timeout. Fixed by setting timeout=5.0 on HTTP client.", "payment.py"),
        ("User service crash", "CrashLoopBackOff caused by missing environment variable DB_PASSWORD at startup. Fixed by adding fallback or failing early with clear error.", "user_service.py")
    ]
    
    chunks_added = 0
    for idx, (title, summary, related_file) in enumerate(past_incidents_data):
        incident = Incident(
            title=title,
            description=summary,
            status=IncidentStatus.RESOLVED,
            severity="HIGH",
            source_type="past_incident",
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
            resolved_at=datetime.utcnow() - timedelta(days=random.randint(0, 5))
        )
        db.add(incident)
        db.flush()
        
        fix = Fix(
            incident_id=incident.id,
            diff_content="def process():\n    pass",
            status="MERGED",
            confidence_score=0.95
        )
        db.add(fix)
        
        embedding = get_embedding(summary)
        chunk = KnowledgeChunk(
            content=summary,
            embedding=embedding,
            source_type='past_incident',
            metadata_json={
                "incident_id": incident.id,
                "related_file": related_file
            }
        )
        db.add(chunk)
        chunks_added += 1
        
    db.commit()
    return chunks_added


def query_knowledge_base(db: Session, query: str, top_k: int = 3) -> list[dict]:
    if genai and settings.GEMINI_API_KEY:
        try:
            query_embedding = genai.embed_content(
                model="models/gemini-embedding-001",
                content=query,
            )["embedding"]
            distance_col = KnowledgeChunk.embedding.l2_distance(query_embedding).label("distance")
            vector_matches = (
                db.query(KnowledgeChunk, distance_col)
                .order_by(distance_col)
                .limit(top_k)
                .all()
            )
            return [
                {
                    "id": chunk.id,
                    "content": chunk.content,
                    "source_type": chunk.source_type,
                    "metadata": chunk.metadata_json,
                    "distance": float(distance),
                }
                for chunk, distance in vector_matches
            ]
        except Exception:
            # Fall through to local lexical retrieval on quota/network errors.
            pass

    chunks = db.query(KnowledgeChunk).all()
    query_tokens = set(_tokens(query))
    if not chunks:
        return []

    # Lexical ranking is reliable for local fallback vectors and makes exact
    # stack traces useful even when Gemini embedding quota is exhausted.
    ranked = []
    for chunk in chunks:
        content_tokens = set(_tokens(chunk.content))
        overlap = len(query_tokens & content_tokens)
        phrase_bonus = 1 if query.strip().lower() in chunk.content.lower() else 0
        score = overlap + phrase_bonus
        ranked.append((chunk, score))
    ranked.sort(key=lambda item: item[1], reverse=True)

    results = []
    for chunk, score in ranked[:top_k]:
        results.append({
            "id": chunk.id,
            "content": chunk.content,
            "source_type": chunk.source_type,
            "metadata": chunk.metadata_json,
            "distance": float(1.0 / (score + 1.0))
        })
    return results
