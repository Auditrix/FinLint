"""Load the public reference documents into the local vector database."""

from finlint.rag.chunk import chunk_pages
from finlint.rag.corpus import CORPUS, CORPUS_DIR, read_ecfr, read_pdf
from finlint.rag.store import SCHEMA, add_chunks, connect


def main():
    files = [CORPUS_DIR / name for name in CORPUS]
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing corpus files: {missing}")

    conn = connect()
    try:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()

        for number, path in enumerate(files, start=1):
            stored = conn.execute(
                "SELECT count(*) FROM chunks WHERE source = %s", (path.name,)
            ).fetchone()[0]
            if stored:
                print(f"[{number}/{len(files)}] Already saved {path.name}: {stored} chunks", flush=True)
                continue

            print(f"[{number}/{len(files)}] Reading {path.name}", flush=True)
            if path.suffix == ".pdf":
                pages = read_pdf(path)
            else:
                pages = read_ecfr(path)

            chunks = chunk_pages(pages)
            print(f"  {len(pages)} pages, {len(chunks)} chunks; embedding...", flush=True)
            add_chunks(conn, chunks)
            print(f"  Saved {path.name}", flush=True)

        total = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        print(f"Done. Database has {total} chunks.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
