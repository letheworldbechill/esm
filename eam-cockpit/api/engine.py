"""
EAM Knowledge Cockpit — RAG Engine
Retrieval + Context Building + LLM-Antwort.

3 Suchmodi:
  - "learn"    → Severin lernt EAM, erklärt Konzepte mit Produktbezug
  - "decide"   → Produktentscheidung, liefert Decision Triggers + Papers
  - "explore"  → Freie Suche über alles (Paper-Chunks, Konzepte, Triggers)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    EMBEDDING_MODEL, LLM_MODEL, LLM_MAX_TOKENS,
    RETRIEVAL_TOP_K, RETRIEVAL_THRESHOLD,
)

from supabase import create_client
from openai import OpenAI
from anthropic import Anthropic

# ============================================================
# Clients
# ============================================================
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)


def embed(text: str) -> list[float]:
    """Embedding für Suchanfrage."""
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
    return resp.data[0].embedding


# ============================================================
# Retrieval
# ============================================================
def search_papers(query_embedding: list, top_k: int = RETRIEVAL_TOP_K,
                  domain: str = None) -> list[dict]:
    """Sucht in Paper-Chunks."""
    params = {
        "query_embedding": query_embedding,
        "match_threshold": RETRIEVAL_THRESHOLD,
        "match_count": top_k,
    }
    if domain:
        params["filter_domain"] = domain

    result = sb.rpc("match_paper_chunks", params).execute()
    return result.data or []


def search_concepts(query_embedding: list, top_k: int = 5) -> list[dict]:
    """Sucht in Konzepten."""
    result = sb.rpc("match_concepts", {
        "query_embedding": query_embedding,
        "match_threshold": RETRIEVAL_THRESHOLD,
        "match_count": top_k,
    }).execute()
    return result.data or []


def search_triggers(query_embedding: list, product: str = None,
                    top_k: int = 5) -> list[dict]:
    """Sucht in Decision Triggers."""
    params = {
        "query_embedding": query_embedding,
        "match_threshold": RETRIEVAL_THRESHOLD,
        "match_count": top_k,
    }
    if product:
        params["filter_product"] = product

    result = sb.rpc("match_decision_triggers", params).execute()
    return result.data or []


def search_unified(query_embedding: list, top_k: int = 10) -> list[dict]:
    """Sucht über alles: Papers, Konzepte, Triggers."""
    result = sb.rpc("eam_unified_search", {
        "query_embedding": query_embedding,
        "match_threshold": RETRIEVAL_THRESHOLD,
        "match_count": top_k,
    }).execute()
    return result.data or []


def get_paper_meta(paper_id: str) -> dict | None:
    """Holt Paper-Metadaten."""
    result = sb.table("eam_papers").select("*").eq("id", paper_id).execute()
    return result.data[0] if result.data else None


def get_concept(concept_id: str) -> dict | None:
    """Holt ein Konzept."""
    result = sb.table("eam_concepts").select("*").eq("id", concept_id).execute()
    return result.data[0] if result.data else None


def get_linked_papers(concept_id: str) -> list[dict]:
    """Holt Papers die mit einem Konzept verknüpft sind."""
    links = sb.table("eam_concept_papers").select("paper_id, relevance_score").eq("concept_id", concept_id).execute()
    papers = []
    for link in (links.data or []):
        paper = get_paper_meta(link["paper_id"])
        if paper:
            paper["relevance_score"] = link["relevance_score"]
            papers.append(paper)
    return papers


# ============================================================
# Context Building
# ============================================================
def build_context_learn(query: str, query_embedding: list) -> str:
    """Baut Kontext für Lern-Modus: Konzepte + Papers."""
    concepts = search_concepts(query_embedding, top_k=3)
    papers = search_papers(query_embedding, top_k=5)

    ctx = "=== RELEVANTE KONZEPTE ===\n"
    for c in concepts:
        ctx += f"\n## {c['name_de']} (Similarity: {c['similarity']:.2f})\n"
        ctx += f"{c['description_de']}\n"
        if c.get('why_it_matters'):
            ctx += f"**Warum wichtig:** {c['why_it_matters']}\n"
        if c.get('saas_relevance'):
            ctx += f"**SaaS-Relevanz:** {c['saas_relevance']}\n"

    if papers:
        ctx += "\n\n=== RELEVANTE PAPER-ABSCHNITTE ===\n"
        for p in papers:
            ctx += f"\n--- [{p['paper_title']}] ({p.get('section_title', 'n/a')}) ---\n"
            ctx += f"{p['content'][:800]}\n"

    return ctx


def build_context_decide(query: str, query_embedding: list,
                         product: str = None) -> str:
    """Baut Kontext für Entscheidungs-Modus: Triggers + Konzepte + Papers."""
    triggers = search_triggers(query_embedding, product=product, top_k=3)
    concepts = search_concepts(query_embedding, top_k=3)
    papers = search_papers(query_embedding, top_k=3)

    ctx = "=== PASSENDE DECISION TRIGGERS ===\n"
    for t in triggers:
        ctx += f"\n🎯 **{t['decision_de']}** [Produkt: {t['product']}, Priorität: {t['priority']}]\n"
        ctx += f"   Empfehlung: {t.get('action_hint_de', 'n/a')}\n"
        ctx += f"   Domäne: {t.get('domain_id', 'n/a')}\n"
        if t.get('concept_ids'):
            ctx += f"   Konzepte: {', '.join(t['concept_ids'])}\n"
        if t.get('paper_ids'):
            ctx += f"   Papers: {', '.join(t['paper_ids'])}\n"

    if concepts:
        ctx += "\n\n=== RELEVANTE KONZEPTE ===\n"
        for c in concepts:
            ctx += f"\n## {c['name_de']}\n{c['description_de']}\n"
            if c.get('saas_relevance'):
                ctx += f"→ SaaS: {c['saas_relevance']}\n"

    if papers:
        ctx += "\n\n=== FORSCHUNGSBASIS ===\n"
        for p in papers:
            ctx += f"\n[{p['paper_title']}]: {p['content'][:500]}\n"

    return ctx


def build_context_explore(query: str, query_embedding: list) -> str:
    """Baut Kontext für Explore-Modus: Unified Search."""
    results = search_unified(query_embedding, top_k=10)

    ctx = "=== SUCHERGEBNISSE (Unified) ===\n"
    for r in results:
        type_icon = {"paper_chunk": "📄", "concept": "🧠", "decision_trigger": "🎯"}.get(r['source_type'], "❓")
        ctx += f"\n{type_icon} [{r['source_type']}] **{r['title']}** (Similarity: {r['similarity']:.2f})\n"
        ctx += f"   Domäne: {r.get('domain_id', 'n/a')}\n"
        if r.get('content'):
            ctx += f"   {r['content'][:600]}\n"

    return ctx


# ============================================================
# System Prompts
# ============================================================
SYSTEM_PROMPTS = {
    "learn": """Du bist das EAM Knowledge Cockpit — ein Lernsystem für Severin.

Severin ist Schweizer Entrepreneur, baut SaaS-Produkte für deutsche Handwerker (klar-seite.de, SiteBuildr).
Er kann keinen Code schreiben und nutzt AI als Engineering-Team.
Er hat ein Schwizer Quality System mit 292 Checkpoints und 75+ Dissertationen als Wissensbasis.

DEINE ROLLE: Erkläre EAM-Konzepte so, dass Severin sie sofort auf seine Produktentwicklung übertragen kann.
- Benutze Analogien zu seinem Alltag (Handwerk, Schweizer Qualität)
- Verbinde jedes Konzept mit konkreten Produktentscheidungen
- Nenne relevante Papers mit Dateinamen (z.B. "Paper #10 Piest")
- Sprich Deutsch (Schweizer Stil, "du")
- Sei direkt, praktisch, keine Akademiker-Sprache

KONTEXT AUS DER WISSENSBASIS:
{context}""",

    "decide": """Du bist das EAM Decision Cockpit für Severin.

Severin steht vor einer Produktentscheidung und braucht forschungsbasierte Unterstützung.
Seine Produkte: klar-seite.de (Analytics SaaS), SiteBuildr (Website Builder), Schwizer Quality System (QA).
Server: Hetzner 4GB RAM, Node.js, PostgreSQL, nginx.

DEINE ROLLE: Liefere eine klare Entscheidungsgrundlage.
1. Identifiziere den passenden Decision Trigger
2. Erkläre die relevanten Konzepte (kurz, praktisch)
3. Empfehle spezifische Papers mit konkreten Lesehinweisen
4. Gib eine Handlungsempfehlung

KONTEXT AUS DER WISSENSBASIS:
{context}""",

    "explore": """Du bist das EAM Knowledge Cockpit — durchsuchst das gesamte EAM-Wissen.

Severin sucht nach spezifischen Informationen in 18 akademischen Papers, 30 EAM-Konzepten
und 18 Decision Triggers für seine SaaS-Produktentwicklung.

DEINE ROLLE: Liefere präzise Antworten basierend auf den Suchergebnissen.
- Zitiere Quellen (Paper-Titel, Autoren)
- Unterscheide zwischen Paper-Findings und deiner Interpretation
- Verbinde Forschung mit Praxis

KONTEXT AUS DER WISSENSBASIS:
{context}""",
}


# ============================================================
# Ask — Hauptfunktion
# ============================================================
def ask(query: str, mode: str = "learn", product: str = None) -> dict:
    """
    Stellt eine Frage an das EAM Knowledge Cockpit.

    Args:
        query: Die Frage
        mode: "learn", "decide", oder "explore"
        product: Optional: "klar-seite", "sitebuildr", "qa-system"

    Returns:
        dict mit answer, sources, context_used
    """
    # 1. Embedding
    query_embedding = embed(query)

    # 2. Context aufbauen
    if mode == "learn":
        context = build_context_learn(query, query_embedding)
    elif mode == "decide":
        context = build_context_decide(query, query_embedding, product=product)
    elif mode == "explore":
        context = build_context_explore(query, query_embedding)
    else:
        context = build_context_explore(query, query_embedding)

    # 3. System Prompt mit Context
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["explore"])
    system_prompt = system_prompt.replace("{context}", context)

    # 4. Claude antworten lassen
    message = anthropic_client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": query}],
    )

    answer = message.content[0].text

    # 5. Sources zusammenstellen
    sources = []
    if mode == "learn":
        concepts = search_concepts(query_embedding, top_k=3)
        for c in concepts:
            sources.append({"type": "concept", "id": c["id"], "name": c["name_de"], "similarity": c["similarity"]})
    elif mode == "decide":
        triggers = search_triggers(query_embedding, product=product, top_k=3)
        for t in triggers:
            sources.append({"type": "trigger", "id": t["id"], "decision": t["decision_de"], "similarity": t["similarity"]})

    return {
        "answer": answer,
        "mode": mode,
        "sources": sources,
        "context_length": len(context),
        "model": LLM_MODEL,
    }


# ============================================================
# Graph Traversal — Knowledge Graph Navigation
# ============================================================
def explore_concept(concept_id: str) -> dict:
    """Traversiert den Knowledge Graph ab einem Konzept."""
    concept = get_concept(concept_id)
    if not concept:
        return {"error": f"Konzept {concept_id} nicht gefunden"}

    papers = get_linked_papers(concept_id)

    # Decision Triggers die dieses Konzept referenzieren
    all_triggers = sb.table("eam_decision_triggers").select("*").execute()
    related_triggers = [
        t for t in (all_triggers.data or [])
        if concept_id in (t.get("concept_ids") or [])
    ]

    return {
        "concept": concept,
        "linked_papers": papers,
        "decision_triggers": related_triggers,
    }


def explore_domain(domain_id: str) -> dict:
    """Zeigt alle Inhalte einer Domäne."""
    domain = sb.table("eam_domains").select("*").eq("id", domain_id).execute()
    concepts = sb.table("eam_concepts").select("*").eq("domain_id", domain_id).order("sort_order").execute()
    papers = sb.table("eam_papers").select("*").eq("domain_id", domain_id).execute()
    triggers = sb.table("eam_decision_triggers").select("*").eq("domain_id", domain_id).execute()

    return {
        "domain": domain.data[0] if domain.data else None,
        "concepts": concepts.data or [],
        "papers": papers.data or [],
        "triggers": triggers.data or [],
    }
