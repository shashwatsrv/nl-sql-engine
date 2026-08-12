from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.rag import retrieve_relevant_schema
from app.intent import classify_intent
from app.validator import validate_sql, score_confidence
import redis
import json
import os
import re

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)
engine = create_engine(os.getenv("DATABASE_URL"))
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def clean_sql(raw: str) -> str:
    raw = re.sub(r"```sql|```", "", raw)
    raw = raw.replace("`", '"')
    return raw.strip()

def query(user_input: str, session_id: str = "default") -> dict:
    session_key = f"session:{session_id}"
    raw_history = redis_client.get(session_key)
    history = json.loads(raw_history) if raw_history else []

    intent = classify_intent(user_input)
    print(f"Intent: {intent['intent']} (confidence: {intent['score']})")

    schema = retrieve_relevant_schema(user_input, top_k=6)
    print(f"Retrieved schema:\n{schema}\n")

    messages = [
        {"role": "system", "content": f"""You are a PostgreSQL expert. Given this schema:
{schema}

Query hint: {intent['hint']}

Use PostgreSQL syntax only. Quote table/column names with double quotes if needed. Return only the SQL query, nothing else."""}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=messages
    )
    sql = clean_sql(response.choices[0].message.content)
    print(f"Generated SQL:\n{sql}\n")

    validation = validate_sql(sql)
    if not validation["valid"]:
        print(f"Validation failed: {validation['error']}")
        return {
            "sql": sql,
            "rows": [],
            "intent": intent["intent"],
            "intent_confidence": intent["score"],
            "confidence": 0.0,
            "warning": None,
            "error": validation["error"]
        }

    confidence = score_confidence(sql, schema, validation["valid"])

    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()

    return {
        "sql": sql,
        "rows": rows,
        "intent": intent["intent"],
        "intent_confidence": intent["score"],
        "confidence": confidence,
        "warning": "Low confidence — verify results" if confidence < 0.5 else None,
        "error": None
    }