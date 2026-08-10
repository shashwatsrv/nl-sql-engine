from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.rag import retrieve_relevant_schema
from app.intent import classify_intent
from app.validator import validate_sql, score_confidence
import os
import re

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)
engine = create_engine(os.getenv("DATABASE_URL"))

def clean_sql(raw: str) -> str:
    raw = re.sub(r"```sql|```", "", raw)
    raw = raw.replace("`", '"')
    return raw.strip()

def query(user_input: str) -> dict:
    intent = classify_intent(user_input)
    print(f"Intent: {intent['intent']} (confidence: {intent['score']})")

    schema = retrieve_relevant_schema(user_input, top_k=6)
    print(f"Retrieved schema:\n{schema}\n")

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {"role": "system", "content": f"""You are a PostgreSQL expert. Given this schema:
{schema}

Query hint: {intent['hint']}

Use PostgreSQL syntax only. Quote table/column names with double quotes if needed. Return only the SQL query, nothing else."""},
            {"role": "user", "content": user_input}
        ]
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
if __name__ == "__main__":
    test_queries = [
        "show me the top 5 customers by company name",
        "drop the customers table",
        "show me total sales by region"
    ]
    for q in test_queries:
        print(f"\n{'='*50}")
        print(f"Query: {q}")
        print('='*50)
        output = query(q)
        if output.get("error"):
            print(f"Error: {output['error']}")
        else:
            print("Results:")
            for row in output["rows"]:
                print(row)