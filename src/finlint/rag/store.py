import os
from datetime import datetime,timezone
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

from finlint.rag.chunk import Chunk,EMBEDDING_MODEL, _token_count

load_dotenv()

DATABASE_URL=os.getenv("DATABASE_URL")

cached_model=None
SCHEMA=[
    "CREATE EXTENSION IF NOT EXISTS vector;",
    "CREATE TABLE IF NOT EXISTS chunks(chunk_id text PRIMARY KEY, source text, title text, url text, page int NULL,section text NULL,text text, chunk_index int,token_count int, embedding vector(384), embedding_model text, ingested_at timestamptz);"
]

def _model():
    global cached_model
    if cached_model is None:
        cached_model = SentenceTransformer(EMBEDDING_MODEL)
    return cached_model

def connect():
    url=DATABASE_URL
    conn=psycopg.connect(url)
    register_vector(conn)
    return conn

def embed(texts: list[str]):
    model=_model()
    return model.encode(texts,normalize_embeddings=True,batch_size=64)

def add_chunks(conn,chunks):
    grouped_chunks={}
    for chunk in chunks:
        grouped_chunks.setdefault(chunk.source,[]).append(chunk)
    
    for source,source_chunks in grouped_chunks.items():
        embeddings=embed([c.text for c in source_chunks])
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE source = %s",(source,))
            cur.executemany(
                "INSERT INTO chunks(chunk_id,source,title,url,page,section,text,chunk_index,token_count,embedding,embedding_model,ingested_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(c.chunk_id,c.source,c.title,c.url,c.page,c.section,c.text,c.chunk_index,_token_count(c.text),embeddings[i],EMBEDDING_MODEL,datetime.now(timezone.utc)) for i,c in enumerate(source_chunks)]
            )
    conn.commit()
    
def search(conn,query,limit=5):
    query_embedding=embed([query])[0]
    # dict_row returns each row as a dict keyed by column name, so callers read
    # row["score"] rather than row[8]. Adding a column later then changes
    # nothing, where with tuples it would silently shift every index.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT chunk_id,source,title,url,page,section,text,chunk_index,1- (embedding <=> %s) AS score FROM chunks ORDER BY embedding <=> %s LIMIT %s",
            (query_embedding, query_embedding, limit)
        )
        return cur.fetchall()
    