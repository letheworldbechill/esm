#!/usr/bin/env python3
"""
EAM Knowledge Cockpit — Ingestion
Liest PDFs, erstellt Chunks + Embeddings, schreibt alles in Supabase.

Verwendung:
    python ingest.py --all              # Alles: Papers + Konzepte + Triggers
    python ingest.py --papers-only      # Nur PDFs verarbeiten
    python ingest.py --seed-only        # Nur Seed-Daten (Konzepte, Triggers, Paper-Metadaten)
    python ingest.py --stats            # Statistiken anzeigen
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Projektpfade
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY,
    EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, CHUNK_SIZE, CHUNK_OVERLAP, PAPERS_DIR,
)
from data.seed_data import PAPERS, CONCEPTS, DECISION_TRIGGERS

from supabase import create_client
from openai import OpenAI

# ============================================================
# Initialisierung
# ============================================================
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def embed(text: str) -> list[float]:
    """Erstellt einen Embedding-Vektor für einen Text."""
    resp = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000],  # Sicherheitslimit
    )
    return resp.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    """Erstellt Embeddings für eine Liste von Texten in Batches."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch = [t[:8000] for t in batch]
        resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend([d.embedding for d in resp.data])
        if i + batch_size < len(texts):
            time.sleep(0.5)  # Rate limiting
            print(f"  Embedded {i+batch_size}/{len(texts)}...")
    return all_embeddings


# ============================================================
# PDF → Text → Chunks
# ============================================================
def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrahiert Text aus einer PDF-Datei."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except ImportError:
        print("  ⚠️  PyMuPDF nicht installiert. Versuche pdftotext...")
        import subprocess
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True
        )
        return result.stdout.strip()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Teilt Text in überlappende Chunks auf. Versucht an Absatzgrenzen zu trennen."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    current_section = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Erkennung von Kapitelüberschriften (einfache Heuristik)
        if len(para) < 100 and (para.isupper() or para[0].isdigit()):
            current_section = para[:200]

        # Wörter zählen als Token-Approximation (1 Token ≈ 0.75 Wörter)
        word_count = len(current_chunk.split())
        para_words = len(para.split())

        if word_count + para_words > chunk_size * 0.75:
            if current_chunk.strip():
                chunks.append({
                    "content": current_chunk.strip(),
                    "section_title": current_section or None,
                })
            # Überlappung: letzte N Wörter mitnehmen
            words = current_chunk.split()
            overlap_words = words[-int(overlap * 0.75):] if len(words) > overlap else []
            current_chunk = " ".join(overlap_words) + "\n\n" + para
        else:
            current_chunk += "\n\n" + para

    # Letzter Chunk
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "section_title": current_section or None,
        })

    return chunks


# ============================================================
# Seed: Paper-Metadaten
# ============================================================
def seed_papers():
    """Schreibt Paper-Metadaten in Supabase."""
    print("\n📄 Seeding Papers...")
    for p in PAPERS:
        row = {
            "id": p["id"],
            "title": p["title"],
            "authors": p["authors"],
            "year": p["year"],
            "source": p.get("source"),
            "doi": p.get("doi"),
            "filename": p.get("filename"),
            "domain_id": p.get("domain_id"),
            "quality_tier": p.get("quality_tier"),
            "key_findings": p.get("key_findings"),
            "relevance_product": p.get("relevance_product"),
            "relevance_qa": p.get("relevance_qa"),
            "is_downloaded": p.get("is_downloaded", False),
        }
        sb.table("eam_papers").upsert(row).execute()
        tier = p.get("quality_tier", "?")
        print(f"  ✅ [{tier}] {p['id']}: {p['title'][:60]}...")
    print(f"  → {len(PAPERS)} Papers geseedet")


# ============================================================
# Seed: Konzepte (mit Embeddings)
# ============================================================
def seed_concepts():
    """Schreibt Konzepte in Supabase mit Embeddings."""
    print("\n🧠 Seeding Concepts...")

    # Embedding-Texte vorbereiten
    texts = []
    for c in CONCEPTS:
        embed_text = f"{c['name_de']} — {c['name_en']}: {c['description_de']} {c.get('why_it_matters', '')} {c.get('saas_relevance', '')}"
        texts.append(embed_text)

    print(f"  Erstelle {len(texts)} Embeddings...")
    embeddings = embed_batch(texts)

    for c, emb in zip(CONCEPTS, embeddings):
        row = {
            "id": c["id"],
            "domain_id": c["domain_id"],
            "name_de": c["name_de"],
            "name_en": c["name_en"],
            "description_de": c.get("description_de"),
            "description_en": c.get("description_en"),
            "why_it_matters": c.get("why_it_matters"),
            "saas_relevance": c.get("saas_relevance"),
            "difficulty": c.get("difficulty"),
            "embedding": emb,
            "sort_order": c.get("sort_order", 0),
        }
        sb.table("eam_concepts").upsert(row).execute()
        print(f"  ✅ {c['id']}: {c['name_de']}")
    print(f"  → {len(CONCEPTS)} Konzepte geseedet (mit Embeddings)")


# ============================================================
# Seed: Decision Triggers (mit Embeddings)
# ============================================================
def seed_triggers():
    """Schreibt Decision Triggers in Supabase mit Embeddings."""
    print("\n🎯 Seeding Decision Triggers...")

    texts = []
    for dt in DECISION_TRIGGERS:
        embed_text = f"{dt['decision_de']} — Produkt: {dt['product']}. {dt.get('action_hint_de', '')}"
        texts.append(embed_text)

    print(f"  Erstelle {len(texts)} Embeddings...")
    embeddings = embed_batch(texts)

    for dt, emb in zip(DECISION_TRIGGERS, embeddings):
        row = {
            "id": dt["id"],
            "product": dt["product"],
            "decision_de": dt["decision_de"],
            "domain_id": dt.get("domain_id"),
            "concept_ids": dt.get("concept_ids", []),
            "paper_ids": dt.get("paper_ids", []),
            "priority": dt.get("priority"),
            "action_hint_de": dt.get("action_hint_de"),
            "embedding": emb,
        }
        sb.table("eam_decision_triggers").upsert(row).execute()
        icon = "🔴" if dt.get("priority") == "HIGH" else "🟡" if dt.get("priority") == "MEDIUM" else "🟢"
        print(f"  {icon} {dt['id']}: {dt['decision_de'][:60]}...")
    print(f"  → {len(DECISION_TRIGGERS)} Decision Triggers geseedet (mit Embeddings)")


# ============================================================
# Seed: Concept ↔ Paper Verknüpfungen
# ============================================================
def seed_concept_papers():
    """Erstellt die Verknüpfungen zwischen Konzepten und Papers basierend auf Decision Triggers."""
    print("\n🔗 Seeding Concept ↔ Paper Verknüpfungen...")
    count = 0
    seen = set()

    for dt in DECISION_TRIGGERS:
        for concept_id in dt.get("concept_ids", []):
            for paper_id in dt.get("paper_ids", []):
                key = (concept_id, paper_id)
                if key not in seen:
                    seen.add(key)
                    row = {
                        "concept_id": concept_id,
                        "paper_id": paper_id,
                        "relevance_score": 0.9 if dt.get("priority") == "HIGH" else 0.7,
                    }
                    try:
                        sb.table("eam_concept_papers").upsert(row).execute()
                        count += 1
                    except Exception as e:
                        pass  # Skip duplicates
    print(f"  → {count} Verknüpfungen erstellt")


# ============================================================
# Process: PDFs → Chunks → Embeddings
# ============================================================
def process_papers(papers_dir: str):
    """Verarbeitet alle heruntergeladenen PDFs."""
    print(f"\n📚 Verarbeite PDFs aus {papers_dir}...")
    papers_dir = Path(papers_dir)

    if not papers_dir.exists():
        print(f"  ❌ Verzeichnis {papers_dir} existiert nicht!")
        return

    # Mappe Dateinamen zu Paper-IDs
    filename_to_id = {p["filename"]: p["id"] for p in PAPERS if p.get("filename")}

    pdf_files = sorted(papers_dir.glob("*.pdf"))
    print(f"  Gefunden: {len(pdf_files)} PDFs")

    for pdf_path in pdf_files:
        paper_id = filename_to_id.get(pdf_path.name)
        if not paper_id:
            print(f"  ⏭️  {pdf_path.name} — keine Paper-ID gefunden, überspringe")
            continue

        print(f"\n  📖 {pdf_path.name} → {paper_id}")

        # Bereits verarbeitet?
        existing = sb.table("eam_paper_chunks").select("id", count="exact").eq("paper_id", paper_id).execute()
        if existing.count and existing.count > 0:
            print(f"     ⏭️  Bereits {existing.count} Chunks vorhanden, überspringe")
            continue

        # Text extrahieren
        print(f"     Extrahiere Text...")
        text = extract_text_from_pdf(str(pdf_path))
        if not text or len(text) < 100:
            print(f"     ⚠️  Zu wenig Text extrahiert ({len(text)} Zeichen)")
            continue
        print(f"     {len(text)} Zeichen extrahiert")

        # Chunking
        chunks = chunk_text(text)
        print(f"     {len(chunks)} Chunks erstellt")

        # Embeddings
        chunk_texts = [c["content"] for c in chunks]
        print(f"     Erstelle Embeddings...")
        embeddings = embed_batch(chunk_texts)

        # In Supabase schreiben
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            row = {
                "paper_id": paper_id,
                "chunk_index": idx,
                "content": chunk["content"],
                "section_title": chunk.get("section_title"),
                "embedding": emb,
                "token_count": len(chunk["content"].split()),
            }
            sb.table("eam_paper_chunks").insert(row).execute()

        print(f"     ✅ {len(chunks)} Chunks + Embeddings gespeichert")

        # Paper als verarbeitet markieren
        sb.table("eam_papers").update({"is_downloaded": True}).eq("id", paper_id).execute()


# ============================================================
# Stats
# ============================================================
def show_stats():
    """Zeigt Statistiken über die Wissensbasis."""
    print("\n📊 EAM Knowledge Cockpit — Statistiken")
    print("=" * 50)

    tables = [
        ("eam_papers", "Papers"),
        ("eam_paper_chunks", "Paper Chunks"),
        ("eam_concepts", "Konzepte"),
        ("eam_decision_triggers", "Decision Triggers"),
        ("eam_concept_papers", "Concept↔Paper Links"),
    ]

    for table, label in tables:
        try:
            result = sb.table(table).select("id", count="exact").execute()
            count = result.count or 0
            print(f"  {label:.<35} {count:>5}")
        except Exception:
            print(f"  {label:.<35} (Tabelle fehlt)")

    # Auch bestehende gasserwerk-rag Tabellen prüfen
    print("\n  --- Bestehendes gasserwerk-rag ---")
    for table, label in [("checkpoints", "QA Checkpoints"), ("dissertations", "Dissertationen")]:
        try:
            result = sb.table(table).select("id", count="exact").execute()
            count = result.count or 0
            print(f"  {label:.<35} {count:>5}")
        except Exception:
            print(f"  {label:.<35} (nicht vorhanden)")


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="EAM Knowledge Cockpit — Ingestion")
    parser.add_argument("--all", action="store_true", help="Alles: Seed + PDFs verarbeiten")
    parser.add_argument("--seed-only", action="store_true", help="Nur Seed-Daten")
    parser.add_argument("--papers-only", action="store_true", help="Nur PDFs verarbeiten")
    parser.add_argument("--stats", action="store_true", help="Statistiken anzeigen")
    parser.add_argument("--papers-dir", default=PAPERS_DIR, help="Verzeichnis mit PDFs")
    args = parser.parse_args()

    if not any([args.all, args.seed_only, args.papers_only, args.stats]):
        parser.print_help()
        return

    print("🏗️  EAM Knowledge Cockpit — Ingestion")
    print(f"   Supabase: {SUPABASE_URL[:40]}...")

    if args.stats:
        show_stats()
        return

    if args.all or args.seed_only:
        seed_papers()
        seed_concepts()
        seed_triggers()
        seed_concept_papers()

    if args.all or args.papers_only:
        process_papers(args.papers_dir)

    show_stats()
    print("\n✅ Fertig!")


if __name__ == "__main__":
    main()
