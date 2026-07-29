from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.rag import retrieve_relevant_schema
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
    return raw.strip()

def query(user_input: str) -> dict:
    schema = retrieve_relevant_schema(user_input)
    print(f"Retrieved schema:\n{schema}\n")

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {"role": "system", "content": f"You are a SQL expert. Given this schema:\n{schema}\nReturn only the SQL query, nothing else."},
            {"role": "user", "content": user_input}
        ]
    )
    sql = clean_sql(response.choices[0].message.content)
    print(f"Generated SQL:\n{sql}\n")

    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()

    return {"sql": sql, "rows": rows}

if __name__ == "__main__":
    output = query("show me the top 5 customers by company name")
    print("Results:")
    for row in output["rows"]:
        print(row)