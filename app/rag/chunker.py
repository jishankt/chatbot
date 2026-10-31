import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import Config, BASE_DIR


def parse_markdown_kb(
    kb_dir: Path,
    default_model: str = "CX-02",
    default_namespace: str = "cx02"
) -> List[Dict[str, Any]]:
    chunks = []
    if not kb_dir.exists():
        return chunks

    md_files = sorted(list(kb_dir.glob("*.md")))

    chunk_idx = 1
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")

        # Extract source url, model, raw source, namespace from header comments/metadata
        source_match = re.search(r"<!--\s*Source:\s*([^\s>]+)\s*-->", content, re.IGNORECASE)
        source_url = source_match.group(1).strip() if source_match else "https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/"

        raw_source_match = re.search(r"(?:<!--\s*RawSource:\s*([^>]+)\s*-->|-\s*RAW_SOURCE_FILE:\s*([^\n]+))", content, re.IGNORECASE)
        raw_sources = []
        if raw_source_match:
            raw_val = raw_source_match.group(1) or raw_source_match.group(2)
            raw_sources = [s.strip() for s in raw_val.split(",")]

        site_match = re.search(r"-\s*SITE:\s*([^\n]+)", content, re.IGNORECASE)
        site_val = site_match.group(1).strip() if site_match else "corporate"

        date_match = re.search(r"-\s*SOURCE_DATE:\s*([^\n]+)", content, re.IGNORECASE)
        source_date = date_match.group(1).strip() if date_match else "2026-10-26"

        ns_match = re.search(r"-\s*NAMESPACE:\s*([^\n]+)", content, re.IGNORECASE)
        namespace = ns_match.group(1).strip() if ns_match else default_namespace

        model_match = re.search(r"<!--\s*Model:\s*([^\s>]+)\s*-->", content, re.IGNORECASE)
        model_name = model_match.group(1).strip() if model_match else default_model

        # Split by ## heading
        sections = re.split(r"\n##\s+", content)
        for i, sec in enumerate(sections):
            text_block = sec.strip()
            if not text_block:
                continue

            lines = text_block.splitlines()
            if text_block.startswith("## "):
                heading = lines[0].replace("## ", "").strip()
                body = "\n".join(lines[1:]).strip()
            else:
                heading = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

            if not body and not heading:
                continue

            # Remove comment lines from heading or body
            heading = re.sub(r"<!--.*?-->", "", heading).strip()
            body = re.sub(r"<!--.*?-->", "", body).strip()

            if not heading:
                continue

            full_text = f"## {heading}\n{body}"
            prefix = "chunk" if namespace == "cx02" else "comp_chunk"
            chunk = {
                "chunk_id": f"{prefix}_{chunk_idx:03d}",
                "file": md_file.name,
                "section": heading,
                "title": heading,
                "text": full_text,
                "model": model_name,
                "namespace": namespace,
                "site": site_val,
                "source_date": source_date,
                "source_url": source_url,
                "raw_sources": raw_sources
            }
            chunks.append(chunk)
            chunk_idx += 1

    return chunks


def build_chunks(
    kb_dir: Path = Config.KB_DIR,
    output_path: Path = Path(BASE_DIR / "data" / "chunks.json")
) -> List[Dict[str, Any]]:
    # 1. Build CX-02 chunks from root kb_dir/*.md
    cx02_chunks = parse_markdown_kb(kb_dir, default_model="CX-02", default_namespace="cx02")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cx02_chunks, f, indent=2, ensure_ascii=False)

    # 2. Build Company chunks from kb_dir/company/*.md
    company_kb_dir = kb_dir / "company"
    if company_kb_dir.exists():
        build_company_chunks(company_kb_dir)

    return cx02_chunks


def build_company_chunks(
    company_kb_dir: Path = Path(Config.KB_DIR / "company"),
    output_path: Path = Path(BASE_DIR / "data" / "company_chunks.json")
) -> List[Dict[str, Any]]:
    company_chunks = parse_markdown_kb(
        company_kb_dir,
        default_model="kepler_company",
        default_namespace="company"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(company_chunks, f, indent=2, ensure_ascii=False)
    return company_chunks


if __name__ == "__main__":
    c1 = build_chunks()
    c2 = build_company_chunks()
    print(f"Built {len(c1)} CX-02 chunks and {len(c2)} Company chunks.")
