from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.pipeline import query as run_query
from openai import OpenAI
import redis
import hashlib
import json
import os

load_dotenv()

app = FastAPI(title="NL SQL Engine")

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
engine = create_engine(os.getenv("DATABASE_URL"))

API_KEY = os.getenv("APP_API_KEY", "dev-key-123")

# --- Auth ---
def verify_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# --- Cache ---
def normalize(query: str) -> str:
    return " ".join(query.lower().strip().split())

def cache_key(query: str) -> str:
    return "nlsql:" + hashlib.md5(normalize(query).encode()).hexdigest()

# --- History ---
def log_history(nl_query: str, sql: str, row_count: int, error: str = None):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO query_history (nl_query, generated_sql, row_count, error)
            VALUES (:nl, :sql, :rows, :error)
        """), {"nl": nl_query, "sql": sql, "rows": row_count, "error": error})
        conn.commit()

def ensure_history_table():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS query_history (
                id SERIAL PRIMARY KEY,
                nl_query TEXT,
                generated_sql TEXT,
                row_count INTEGER,
                error TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_history_created_at 
            ON query_history(created_at)
        """))
        conn.commit()

# --- Models ---
class QueryRequest(BaseModel):
    query: str

# --- Startup ---
@app.on_event("startup")
async def startup():
    ensure_history_table()

# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/query")
def query_endpoint(request: QueryRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)

    # cache check
    key = cache_key(request.query)
    cached = redis_client.get(key)
    if cached:
        result = json.loads(cached)
        result["cached"] = True
        return result

    # run pipeline
    output = run_query(request.query)

    result = {
        "query": request.query,
        "sql": output["sql"],
        "rows": [list(r) for r in output["rows"]],
        "intent": output["intent"],
        "intent_confidence": output["intent_confidence"],
        "confidence": output.get("confidence", 0.0),
        "warning": output.get("warning"),
        "error": output.get("error"),
        "cached": False
    }

    # log history
    log_history(
        request.query,
        output["sql"],
        len(output["rows"]),
        output.get("error")
    )

    # cache if successful
    if not output.get("error"):
        redis_client.setex(key, 3600, json.dumps(result))

    return result

@app.get("/history")
def history_endpoint(x_api_key: str = Header(...), limit: int = 20):
    verify_key(x_api_key)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT nl_query, generated_sql, row_count, error, created_at
            FROM query_history
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return {"history": [dict(r._mapping) for r in rows]}

@app.delete("/history")
def clear_history(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    with engine.connect() as conn:
        conn.execute(text("""
            DELETE FROM query_history 
            WHERE created_at < NOW() - INTERVAL '30 days'
        """))
        conn.commit()
    return {"status": "old records cleared"}

class ExplainRequest(BaseModel):
    sql: str

@app.post("/explain")
def explain_endpoint(request: ExplainRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {"role": "system", "content": "You are a SQL expert. Explain what the following SQL query does in plain English. Be concise — 2-3 sentences max."},
            {"role": "user", "content": request.sql}
        ]
    )
    return {"explanation": response.choices[0].message.content}