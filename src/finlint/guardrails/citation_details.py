"""Build a citation from a retrieved hit only after checking its quote."""

from finlint.guardrails.citations import verify_quote


def citation_details(hit, quote: str) -> dict:
    """Take citation metadata from the stored chunk, not from model output."""
    if not verify_quote(quote, hit):
        raise ValueError("Quote was not found in the retrieved evidence")
    chunk = hit.chunk
    if not chunk.url:
        raise ValueError("Evidence has no source URL")
    return {
        "source": chunk.source,
        "title": chunk.title,
        "url": chunk.url,
        "page": chunk.page,
        "section": chunk.section,
        "quote": quote,
    }
