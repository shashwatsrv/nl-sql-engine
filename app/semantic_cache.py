from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import json
import os

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
model = SentenceTransformer('all-MiniLM-L6-v2')

SIMILARITY_THRESHOLD = 0.92

def ensure_semantic_cache_table():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                id SERIAL PRIMARY KEY,
                query_text TEXT,
                query_embedding vector(384),
                result JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_semantic_cache_embedding
            ON semantic_cache USING ivfflat (query_embedding vector_cosine_ops)
            WITH (lists = 10)
        """))
        conn.commit()

def semantic_cache_get(query: str) -> dict | None:
    embedding = model.encode(query).tolist()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT result, 1 - (query_embedding <=> :embedding) AS similarity
            FROM semantic_cache
            ORDER BY query_embedding <=> :embedding
            LIMIT 1
        """), {"embedding": str(embedding)})
        row = result.fetchone()
    
    if row and row[1] >= SIMILARITY_THRESHOLD:
        print(f"Semantic cache hit (similarity: {round(row[1], 3)})")
        result = row[0]
        return result if isinstance(result, dict) else json.loads(result)
    return None

def semantic_cache_set(query: str, result: dict):
    embedding = model.encode(query).tolist()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO semantic_cache (query_text, query_embedding, result)
            VALUES (:query, :embedding, :result)
        """), {
            "query": query,
            "embedding": str(embedding),
            "result": json.dumps(result)
        })
        conn.commit()