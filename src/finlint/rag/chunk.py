"""Cut the corpus pages into pieces small enough for the embedding model.

bge-small-en-v1.5 stops reading after 512 tokens and truncates silently, with
no error, so anything past that point would sit in the database looking fine
while being invisible to search. That is what this file exists to prevent.

Two stages, on purpose:

  split_text        cuts on characters. Fast, no model needed, so the logic
                    is fully testable in milliseconds.
  _fit_token_limit  then counts real tokens and splits anything still over
                    the limit.

The second stage is not optional. Characters cannot guarantee a token count:
prose runs about 4.4 characters per token, but account codes and legal
citation strings run closer to 1.7, so a 1,398 character chunk measured 844
tokens. Ten chunks in this corpus breached the limit on characters alone.
"""

from pydantic import BaseModel

from finlint.rag.corpus import Page

# The model whose limit we are respecting, from CLAUDE.md Section 5.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Its hard input limit, in tokens.
MAX_TOKENS = 512

# Loaded on first use, not at import, so this module and most of its tests
# never touch the network or wait on a model.
_tokenizer = None


def _token_count(text: str) -> int:
    """How many tokens the embedding model would see in this text."""
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    # add_special_tokens counts the two markers the model puts around every
    # input, because they use up two of the 512.
    return len(_tokenizer.encode(text, add_special_tokens=True))

def _fit_token_limit(piece: str, max_tokens: int = MAX_TOKENS) -> list[str]:
    """Split one piece in half, repeatedly, until every part fits max_tokens.

    Only the rare dense piece gets here, about one in two thousand, so a plain
    recursive halving is cheap enough and easy to follow.

    These halves carry no overlap between them. That is a deliberate trade:
    the alternative is keeping a chunk that the model would read only the
    first half of.
    """
    if _token_count(piece) <= max_tokens:
        return [piece]

    middle = len(piece) // 2
    cut = piece.rfind(". ", 0, middle)
    if cut != -1:
        cut += 1                       # keep the period with its sentence
    else:
        cut = piece.rfind(" ", 0, middle)
    if cut <= 0:
        cut = middle                   # no break anywhere, cut mid word

    left, right = piece[:cut], piece[cut:]
    if not left.strip() or not right.strip():
        # Nothing splittable left. Returning it stops the recursion rather
        # than looping on a piece that cannot be divided.
        return [piece]

    return (_fit_token_limit(left, max_tokens)
            + _fit_token_limit(right, max_tokens))


def split_text(text, target=1200, overlap=200, minimum=200):
    """Cut one page of text into pieces, measured in characters.

    Cuts at a blank line where possible, then at the end of a sentence, and
    only mid sentence when neither exists. Each piece repeats the last
    overlap characters of the one before it, so a sentence sitting on a
    boundary is still complete in one of them.

    minimum is the least NEW text a final piece may carry. See the comment
    at the bottom for why it is measured that way.

    This does not guarantee the token limit. chunk_page applies
    _fit_token_limit afterwards, which does.
    """
    pieces = []
    start = 0

    while start < len(text):
        end = min(start + target, len(text))

        if end < len(text):
            cut = text.rfind("\n\n", start, end)   # a paragraph break, the best cut
            if cut == -1:
                sentence = text.rfind(". ", start, end)
                # +1 keeps the period with the sentence it belongs to. Written
                # out rather than as rfind(...) + 1, because a miss returns -1
                # and -1 + 1 is 0, which reads like a real position.
                cut = sentence + 1 if sentence != -1 else -1
            # The next start is end - overlap, so a cut is only usable if it
            # leaves end past start + overlap. Accepting any cut after start
            # looks right and hangs: with one blank line at 1000 and none
            # after it, the piece ends at 1000, the next start is 800, that
            # same blank line is still the last one in the new window, so the
            # cut is 1000 again and start is 800 again, forever. The corpus
            # hits this and dies with MemoryError.
            if cut > start + overlap:
                end = cut

        pieces.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap

    # The final piece always begins with overlap characters copied from the
    # piece before it, so its length is never the useful measure. A 2,210
    # character page ends with a 210 character piece holding 10 characters of
    # new text. Stored on its own that is noise competing in every search, so
    # it is folded back into the piece before it. Slicing off the overlap
    # first stops the shared text being written twice.
    if len(pieces) > 1 and len(pieces[-1]) - overlap < minimum:
        tail = pieces.pop()
        pieces[-1] += tail[overlap:]

    return pieces
    

class Chunk(BaseModel):
    """One search sized piece of one page, ready to be embedded and stored.

    The five document fields are copied from the Page this piece came from
    rather than nested, so a chunk never carries a second copy of its whole
    page. The largest eCFR section becomes about 140 chunks, and nesting its
    166,000 characters inside each of them would cost roughly 23 MB for that
    one section.

    There is no embedding field here. The embedding belongs in the same
    Postgres row as the text, and store.py puts it there. Leaving it off this
    model is what lets chunk.py and its tests run without loading a 130 MB
    model first.

    Frozen shape, confirmed with Sowb alongside Page in corpus.py.
    """

    source: str          # file name, e.g. "gao_yellow_book_2024.pdf"
    title: str           # readable name, what a citation shows the reader
    url: str             # where it came from, so the reader can verify it
    page: int | None     # PDF page number, 1 based. None for the eCFR XML,
                         # which has sections instead of pages.
    section: str | None  # nearest heading above this page. None on pages that
                         # come before the document's first heading.
    text: str            # this piece only, never the whole page
    chunk_index: int     # position within its page, 0 upwards. Lets
                         # retrieve.py fetch the neighbouring pieces.
    chunk_id: str        # built in chunk_page, stable across re-runs so the
                         # same chunk is never inserted twice
    
    
def _locator(page: Page) -> str:
    """The part of a chunk_id saying which page or section a chunk came from.

    A page number is unique within a document, so the PDFs use that. The eCFR
    records have no page number, but each record is exactly one section and a
    section number appears once, so those use the section instead.

    Never the heading. A heading covers many pages: the Yellow Book's Glossary
    runs for 11, so keying on it gave 11 chunks the same id and the database
    would have kept only the last one of each.
    """
    if page.page is not None:
        return str(page.page)
    return page.section or "unknown"


def chunk_page(page: Page, max_tokens: int | None = MAX_TOKENS) -> list[Chunk]:
    """Cut one Page into Chunks, copying its document fields onto each piece.

    Pass max_tokens=None to skip the token check. Only tests do that, to keep
    the character logic quick to assert on. The pipeline always leaves it on.
    """
    locator = _locator(page)

    pieces = split_text(page.text)
    if max_tokens is not None:
        # Flattened after splitting, so chunk_index still counts the final
        # pieces 0, 1, 2 with no gaps and no duplicate ids.
        pieces = [part for piece in pieces
                  for part in _fit_token_limit(piece, max_tokens)]

    return [
        Chunk(
            source=page.source,
            title=page.title,
            url=page.url,
            page=page.page,
            section=page.section,
            text=piece,
            chunk_index=index,
            # File, then page or section, then position within it. Built from
            # the page itself, so running the loader again gives the same ids
            # and a re-insert updates rows instead of doubling them.
            chunk_id=f"{page.source}:{locator}:{index}",
        )
        for index, piece in enumerate(pieces)
    ]


def chunk_pages(pages: list[Page],
                max_tokens: int | None = MAX_TOKENS) -> list[Chunk]:
    """Cut every Page of the corpus into Chunks, in order."""
    chunks = []
    for page in pages:
        chunks += chunk_page(page, max_tokens)
    return chunks