from openai import OpenAI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import re

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)
engine = create_engine(os.getenv("DATABASE_URL"))

SCHEMA = """
Tables:
- customers(customer_id, company_name, contact_name, country)
- orders(order_id, customer_id, order_date, shipped_date)
- order_details(order_id, product_id, unit_price, quantity)
- products(product_id, product_name, unit_price, units_in_stock)
- employees(employee_id, first_name, last_name, title)
"""

def clean_sql(raw: str) -> str:
    raw = re.sub(r"```sql|```", "", raw)
    return raw.strip()

def query(user_input: str) -> dict:
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {"role": "system", "content": f"You are a SQL expert. Given this schema:\n{SCHEMA}\nReturn only the SQL query, nothing else."},
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