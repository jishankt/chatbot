import re
import json
from pathlib import Path
from typing import List, Dict, Any
from app.config import Config, BASE_DIR


def parse_markdown_kb(kb_dir: Path) -> List[Dict[str, Any]]:
    chunks = []
    md_files = sorted(list(kb_dir.glob("*.md")))

    chunk_idx = 1
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")

        # Extract source url and model from header comments if present
        source_match = re.search(r"<!--\s*Source:\s*([^\s>]+)\s*-->", content, re.IGNORECASE)
        source_url = source_match.group(1).strip() if source_match else "https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/"

        raw_source_match = re.search(r"<!--\s*RawSource:\s*([^>]+)\s*-->", content, re.IGNORECASE)
        raw_sources = [s.strip() for s in raw_source_match.group(1).split(",")] if raw_source_match else []

        model_match = re.search(r"<!--\s*Model:\s*([^\s>]+)\s*-->", content, re.IGNORECASE)
        model_name = model_match.group(1).strip() if model_match else "CX-02"

        # Split by ## heading
        sections = re.split(r"\n##\s+", content)
        for i, sec in enumerate(sections):
            text_block = sec.strip()
            if not text_block:
                continue

            lines = text_block.splitlines()
            # If the block itself started with ##, heading is line 0 without ##
            if text_block.startswith("## "):
                heading = lines[0].replace("## ", "").strip()
                body = "\n".join(lines[1:]).strip()
            else:
                heading = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

            if not body and not heading:
                continue

            # Remove any comment lines from heading or body
            heading = re.sub(r"<!--.*?-->", "", heading).strip()
            body = re.sub(r"<!--.*?-->", "", body).strip()

            if not heading:
                continue

            full_text = f"## {heading}\n{body}"
            chunk = {
                "chunk_id": f"chunk_{chunk_idx:03d}",
                "file": md_file.name,
                "section": heading,
                "title": heading,
                "text": full_text,
                "model": model_name,
                "source_url": source_url,
                "raw_sources": raw_sources
            }
            chunks.append(chunk)
            chunk_idx += 1

    return chunks


def build_chunks(kb_dir: Path = Config.KB_DIR, output_path: Path = Path(BASE_DIR / "data" / "chunks.json")) -> List[Dict[str, Any]]:
    chunks = parse_markdown_kb(kb_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    return chunks


if __name__ == "__main__":
    c = build_chunks()
    print(f"Built {len(c)} chunks.")
