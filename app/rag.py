from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_schema_chunks() -> list[dict]:
    inspector = inspect(engine)
    chunks = []
    for table in inspector.get_table_names():
        columns = inspector.get_columns(table)
        col_defs = ", ".join(f"{c['name']} ({c['type']})" for c in columns)
        text_repr = f"Table {table} has columns: {col_defs}"
        chunks.append({"table": table, "text": text_repr})
    return chunks

def embed_schema():
    chunks = get_schema_chunks()
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("DROP TABLE IF EXISTS schema_embeddings"))
        conn.execute(text("""
            CREATE TABLE schema_embeddings (
                table_name TEXT,
                chunk_text TEXT,
                embedding vector(384)
            )
        """))
        for chunk in chunks:
            embedding = model.encode(chunk["text"]).tolist()
            conn.execute(text("""
                INSERT INTO schema_embeddings (table_name, chunk_text, embedding)
                VALUES (:table, :text, :embedding)
            """), {"table": chunk["table"], "text": chunk["text"], "embedding": str(embedding)})
        conn.commit()
    print(f"Embedded {len(chunks)} table chunks into pgvector")

def retrieve_relevant_schema(query: str, top_k: int = 3) -> str:
    query_embedding = model.encode(query).tolist()
    with engine.connect() as conn:
        results = conn.execute(text("""
            SELECT table_name, chunk_text
            FROM schema_embeddings
            ORDER BY embedding <-> :embedding
            LIMIT :k
        """), {"embedding": str(query_embedding), "k": top_k})
        rows = results.fetchall()
    
    if not rows:
        return None
    
    return "Relevant tables:\n" + "\n".join(f"- {r[1]}" for r in rows)

if __name__ == "__main__":
    print("Embedding schema...")
    embed_schema()
    
    test_query = "show me total sales by region"
    result = retrieve_relevant_schema(test_query)
    print(f"\nRelevant schema for '{test_query}':")
    print(result)