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

def score_confidence(sql: str, schema_retrieved: str, validation_passed: bool) -> float:
    # Signal 1 — schema coverage
    # how many referenced tables were in the retrieved schema
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
        referenced = {t.name.lower() for t in parsed.find_all(sqlglot.exp.Table)}
    except:
        referenced = set()

    retrieved_tables = set()
    for line in schema_retrieved.split("\n"):
        if line.startswith("- Table"):
            table_name = line.split(" ")[2]
            retrieved_tables.add(table_name.lower())

    coverage = len(referenced & retrieved_tables) / max(len(referenced), 1)

    # Signal 2 — query complexity
    sql_upper = sql.upper()
    join_count = sql_upper.count("JOIN")
    subquery_count = sql_upper.count("SELECT") - 1

    if join_count == 0 and subquery_count == 0:
        complexity = 1.0
    elif join_count <= 2 and subquery_count <= 1:
        complexity = 0.6
    else:
        complexity = 0.3

    # Signal 3 — validation passed
    valid_bonus = 1.0 if validation_passed else 0.0

    # Weighted average
    score = (coverage * 0.5) + (complexity * 0.3) + (valid_bonus * 0.2)
    return round(score, 2)

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

