from finlint.rag.chunk import Chunk
from pydantic import BaseModel
from psycopg.rows import dict_row
from finlint.rag.store import search

class Hit(BaseModel):
    chunk:Chunk
    score:float
    neighbors:list[Chunk]
    
# One search question per rule, keyed by the rule_id in rules/checks.py.
#
# The question describes the ACCOUNTING CONCEPT, never the cell. A finding
# says "Cell C15 holds a typed number", but searching the corpus for "C15"
# finds nothing: federal accounting standards do not mention your spreadsheet.
#
# This mapping is deliberately fixed rather than generated. When an examiner
# asks how FinLint finds the governing rule, the answer is a fixed mapping
# plus a similarity search, not a model guessing.
QUESTIONS = {
    "error_cells":
        "controls over the accuracy and completeness of information used in "
        "financial reporting",
    "circular_reference":
        "controls over the reliability of calculations and information "
        "processing",
    "dead_input":
        "using relevant and reliable data in financial reporting processes",
    "hardcoded_value":
        "documentation and review of assumptions and manual inputs used in "
        "financial estimates",
    "broken_link":
        "completeness and integrity of data obtained from other systems or "
        "sources",
    "formula_drift":
        "controls to detect inconsistent or erroneous processing of financial "
        "data",
}

# A rule with no question falls back to its own plain message, which is better
# than returning nothing. Covers any new check added before this dict is.
def question_for(finding):
    return QUESTIONS.get(finding.rule_id, finding.message)

def _neighbor_ids(chunk_id):
    page_id,chunk_index=chunk_id.rsplit(":",1)
    return [f"{page_id}:{i}" for i in range(int(chunk_index)-1,int(chunk_index)+2,2) if i>=0]

def neighbors(conn,chunk_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT chunk_id,source,title,url,page,section,text,chunk_index FROM chunks WHERE chunk_id= ANY(%s) ORDER BY chunk_index;",
            (_neighbor_ids(chunk_id),)
        )
        return [Chunk(**row) for row in cur.fetchall()]

def retrieve(conn,finding,limit=5):
    hits=[]
    question=question_for(finding)
    rows=search(conn,question,limit)
    for row in rows:
        score=row["score"]
        chunk=Chunk(**{k:v for k,v in row.items() if k!="score"})
        hits.append(Hit(chunk=chunk,score=score,neighbors=neighbors(conn,chunk.chunk_id)))
    return hits
        
