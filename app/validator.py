import sqlglot
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))

BLOCKED_OPERATIONS = {"DROP", "DELETE", "ALTER", "TRUNCATE", "INSERT", "UPDATE", "CREATE"}

def get_known_tables() -> set:
    inspector = inspect(engine)
    return set(inspector.get_table_names())

def validate_sql(sql: str) -> dict:
    # Step 1 — AST parse
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        return {"valid": False, "error": f"Syntax error: {e}"}

    # Step 2 — block dangerous operations
    statement_type = parsed.key.upper()
    if statement_type in BLOCKED_OPERATIONS:
        return {"valid": False, "error": f"Operation not allowed: {statement_type}"}

    # Step 3 — extract referenced tables and check they exist
    known_tables = get_known_tables()
    referenced_tables = {
        table.name.lower()
        for table in parsed.find_all(sqlglot.exp.Table)
    }
    unknown_tables = referenced_tables - known_tables
    if unknown_tables:
        return {"valid": False, "error": f"Unknown tables referenced: {unknown_tables}"}

    # Step 4 — EXPLAIN check
    try:
        with engine.connect() as conn:
            conn.execute(text(f"EXPLAIN {sql}"))
    except Exception as e:
        return {"valid": False, "error": f"Query plan failed: {e}"}

    return {"valid": True, "error": None, "referenced_tables": list(referenced_tables)}


if __name__ == "__main__":
    test_cases = [
        ("SELECT company_name FROM customers LIMIT 5", "simple select"),
        ("DROP TABLE customers", "dangerous op"),
        ("SELECT * FROM fake_table", "unknown table"),
        ("SELECT company_name FROM customers ORDER BY company_name LIMIT 5", "valid query"),
    ]
    for sql, label in test_cases:
        result = validate_sql(sql)
        print(f"[{label}]")
        print(f"Valid: {result['valid']}")
        if not result['valid']:
            print(f"Error: {result['error']}")
        print()