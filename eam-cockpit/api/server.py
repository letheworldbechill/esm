"""
EAM Knowledge Cockpit — FastAPI Server

Endpoints:
    POST /ask           → Hauptendpoint: Frage stellen
    POST /search        → Rohe Vektorsuche
    GET  /domains       → Alle 6 Domänen
    GET  /domains/{id}  → Domäne mit Konzepten, Papers, Triggers
    GET  /concepts/{id} → Konzept mit Knowledge-Graph-Traversal
    GET  /papers        → Alle Papers
    GET  /papers/{id}   → Paper-Details
    GET  /triggers      → Alle Decision Triggers
    GET  /stats         → Statistiken
    GET  /health        → Health Check
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from api.engine import (
    ask, embed, search_papers, search_concepts, search_triggers,
    search_unified, explore_concept, explore_domain,
    get_paper_meta, sb,
)

app = FastAPI(
    title="EAM Knowledge Cockpit",
    description="Forschungsbasiertes Wissenssystem für SaaS-Produktentwicklung",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Models
# ============================================================
class AskRequest(BaseModel):
    query: str
    mode: str = "learn"           # learn, decide, explore
    product: Optional[str] = None  # klar-seite, sitebuildr, qa-system

class SearchRequest(BaseModel):
    query: str
    scope: str = "all"            # all, papers, concepts, triggers
    top_k: int = 8
    domain: Optional[str] = None
    product: Optional[str] = None


# ============================================================
# Endpoints
# ============================================================
@app.get("/health")
async def health():
    """Health Check."""
    return {"status": "ok", "service": "eam-knowledge-cockpit"}


@app.post("/ask")
async def ask_endpoint(req: AskRequest):
    """Hauptendpoint: Stelle eine Frage an das Cockpit."""
    if not req.query.strip():
        raise HTTPException(400, "Query darf nicht leer sein")
    if req.mode not in ("learn", "decide", "explore"):
        raise HTTPException(400, "Mode muss 'learn', 'decide' oder 'explore' sein")

    result = ask(query=req.query, mode=req.mode, product=req.product)
    return result


@app.post("/search")
async def search_endpoint(req: SearchRequest):
    """Rohe Vektorsuche ohne LLM-Antwort."""
    query_embedding = embed(req.query)

    if req.scope == "papers":
        results = search_papers(query_embedding, top_k=req.top_k, domain=req.domain)
    elif req.scope == "concepts":
        results = search_concepts(query_embedding, top_k=req.top_k)
    elif req.scope == "triggers":
        results = search_triggers(query_embedding, product=req.product, top_k=req.top_k)
    else:
        results = search_unified(query_embedding, top_k=req.top_k)

    return {"query": req.query, "scope": req.scope, "results": results, "count": len(results)}


@app.get("/domains")
async def list_domains():
    """Alle 6 Wissens-Domänen."""
    result = sb.table("eam_domains").select("*").order("sort_order").execute()
    return {"domains": result.data or []}


@app.get("/domains/{domain_id}")
async def get_domain(domain_id: str):
    """Domäne mit allen Inhalten (Konzepte, Papers, Triggers)."""
    data = explore_domain(domain_id)
    if not data.get("domain"):
        raise HTTPException(404, f"Domäne {domain_id} nicht gefunden")
    return data


@app.get("/concepts/{concept_id}")
async def get_concept_endpoint(concept_id: str):
    """Konzept mit Knowledge-Graph-Traversal (verknüpfte Papers + Triggers)."""
    data = explore_concept(concept_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return data


@app.get("/papers")
async def list_papers(
    domain: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    downloaded: Optional[bool] = Query(None),
):
    """Alle Papers, optional gefiltert."""
    query = sb.table("eam_papers").select("*")
    if domain:
        query = query.eq("domain_id", domain)
    if tier:
        query = query.eq("quality_tier", tier)
    if downloaded is not None:
        query = query.eq("is_downloaded", downloaded)

    result = query.order("year", desc=True).execute()
    return {"papers": result.data or [], "count": len(result.data or [])}


@app.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    """Paper-Details mit Chunks."""
    paper = get_paper_meta(paper_id)
    if not paper:
        raise HTTPException(404, f"Paper {paper_id} nicht gefunden")

    chunks = sb.table("eam_paper_chunks").select(
        "chunk_index, section_title, content, token_count"
    ).eq("paper_id", paper_id).order("chunk_index").execute()

    return {
        "paper": paper,
        "chunks": chunks.data or [],
        "chunk_count": len(chunks.data or []),
    }


@app.get("/triggers")
async def list_triggers(
    product: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    """Alle Decision Triggers, optional gefiltert."""
    query = sb.table("eam_decision_triggers").select("*")
    if product:
        query = query.eq("product", product)
    if priority:
        query = query.eq("priority", priority)

    result = query.execute()
    return {"triggers": result.data or [], "count": len(result.data or [])}


@app.get("/stats")
async def stats():
    """Statistiken über die gesamte Wissensbasis."""
    tables = {
        "papers": "eam_papers",
        "paper_chunks": "eam_paper_chunks",
        "concepts": "eam_concepts",
        "decision_triggers": "eam_decision_triggers",
        "concept_paper_links": "eam_concept_papers",
    }

    counts = {}
    for key, table in tables.items():
        try:
            result = sb.table(table).select("id", count="exact").execute()
            counts[key] = result.count or 0
        except Exception:
            counts[key] = -1

    # Bestehende Tabellen
    for key, table in [("qa_checkpoints", "checkpoints"), ("dissertations", "dissertations")]:
        try:
            result = sb.table(table).select("id", count="exact").execute()
            counts[key] = result.count or 0
        except Exception:
            counts[key] = -1

    # Domänen-Verteilung
    domains = sb.table("eam_papers").select("domain_id").execute()
    domain_counts = {}
    for p in (domains.data or []):
        d = p.get("domain_id", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    return {
        "totals": counts,
        "papers_by_domain": domain_counts,
    }


# ============================================================
# CLI-Modus
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
