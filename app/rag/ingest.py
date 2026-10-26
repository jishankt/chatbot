from pathlib import Path
from app.config import Config, BASE_DIR
from app.rag.chunker import build_chunks

OUTPUT_CHUNKS_PATH = BASE_DIR / "data" / "chunks.json"


def ingest():
    """
    Ingests all KB markdown files from data/kb/, tags each with model=CX-02 and source URL,
    and writes to data/chunks.json.
    """
    chunks = build_chunks(Config.KB_DIR, OUTPUT_CHUNKS_PATH)
    print(f"Successfully ingested {len(chunks)} chunks with model=CX-02 into {OUTPUT_CHUNKS_PATH}")
    return chunks


if __name__ == "__main__":
    ingest()
