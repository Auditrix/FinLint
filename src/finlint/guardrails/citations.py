from finlint.rag.corpus import tidy
import re

def _searchable(text):
    cleaned=tidy(text)
    cleaned=re.sub(r"\s+"," ",cleaned)
    return cleaned.strip().casefold()

MIN_QUOTE_CHARS=40

def verify_quote(quote,hit):
    # Sorted by chunk_index, because the pieces have to read in document order.
    # hit.chunk is not inside hit.neighbors, so joining the chunk first gives
    # the order 2, 1, 3 for a hit at index 2, and a quote running from chunk 1
    # into chunk 2 is then never found, which rejects a correct citation.
    pieces=sorted([hit.chunk]+list(hit.neighbors),key=lambda c:c.chunk_index)
    joined_text=" ".join(c.text for c in pieces)
    if _searchable(quote) in _searchable(joined_text) and len(_searchable(quote))>=MIN_QUOTE_CHARS:
        return True
    return False