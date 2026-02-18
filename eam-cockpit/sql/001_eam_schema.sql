-- ============================================================
-- EAM Knowledge Cockpit — Supabase Schema
-- Erweitert das bestehende gasserwerk-rag System
-- Einmal ausführen im Supabase SQL Editor
-- ============================================================

-- pgvector sollte bereits aktiv sein, falls nicht:
create extension if not exists vector;

-- ============================================================
-- 1) PAPERS — Die 18+ akademischen Arbeiten
-- ============================================================
create table if not exists eam_papers (
    id text primary key,                              -- z.B. "paper_01_wao"
    title text not null,
    authors text not null,
    year integer not null,
    source text,                                       -- Journal/Konferenz
    doi text,
    url text,
    filename text,                                     -- PDF-Dateiname
    domain_id text,                                    -- Verweis auf eam_domains
    abstract text,
    key_findings text,                                 -- Kernerkenntnisse
    relevance_product text,                            -- Relevanz für SaaS-Produkt
    relevance_qa text,                                 -- Relevanz für QA-System
    quality_tier text check (quality_tier in ('S','A','B','C')),  -- S=Top-Tier, A=Gut, B=OK, C=Ergänzend
    is_downloaded boolean default false,
    created_at timestamptz default now()
);

-- ============================================================
-- 2) PAPER CHUNKS — Vektorisierte Textabschnitte
-- ============================================================
create table if not exists eam_paper_chunks (
    id bigint generated always as identity primary key,
    paper_id text references eam_papers(id) on delete cascade,
    chunk_index integer not null,                      -- Position im Paper
    content text not null,                             -- Der Textabschnitt
    section_title text,                                -- Kapitelüberschrift
    embedding vector(1536),                            -- OpenAI text-embedding-3-small
    token_count integer,
    created_at timestamptz default now()
);

-- Index für Vektorsuche
create index if not exists idx_paper_chunks_embedding
    on eam_paper_chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 20);

-- ============================================================
-- 3) DOMAINS — Die 6 Wissens-Domänen
-- ============================================================
create table if not exists eam_domains (
    id text primary key,                              -- z.B. "domain_a_frameworks"
    code char(1) not null,                            -- A, B, C, D, E, F
    name_de text not null,
    name_en text not null,
    description_de text,
    icon text,                                        -- Emoji
    sort_order integer default 0
);

-- Seed-Daten
insert into eam_domains (id, code, name_de, name_en, description_de, icon, sort_order) values
    ('domain_a_frameworks', 'A', 'Frameworks & Methoden', 'Frameworks & Methods', 'TOGAF, ArchiMate, Zachman, BizDevOps — verstehen, nicht auswendig lernen', '🏗️', 1),
    ('domain_b_ai_ea', 'B', 'AI × EA', 'AI × EA', 'GenAI als Co-Pilot: RAG, Automatisierung, Szenarioplanung, Multi-Agent Systems', '🤖', 2),
    ('domain_c_quality', 'C', 'Qualität messen', 'Quality Metrics', 'GQM-Methodik, Dynamic EA Evaluation, Maturity Models, ROI-Messung', '📊', 3),
    ('domain_d_data', 'D', 'Datenarchitektur', 'Data Architecture', 'Data Mesh, Data Products, Federated Governance, Data Lakehouse', '🗄️', 4),
    ('domain_e_cloud', 'E', 'Cloud & Microservices', 'Cloud & Microservices', 'Cloud-Native, Multi-Cloud, API-Driven, DDD, DevOps', '☁️', 5),
    ('domain_f_security', 'F', 'Sicherheit & Nachhaltigkeit', 'Security & Sustainability', 'Zero Trust, Privacy by Design, Green EA, ESG', '🔒', 6)
on conflict (id) do nothing;

-- ============================================================
-- 4) CONCEPTS — Die 30 Kernkonzepte (6 Domänen × 5)
-- ============================================================
create table if not exists eam_concepts (
    id text primary key,                              -- z.B. "concept_togaf_adm"
    domain_id text references eam_domains(id),
    name_de text not null,
    name_en text not null,
    description_de text,                              -- Erklärung in 2-3 Sätzen
    description_en text,
    why_it_matters text,                              -- Warum wichtig für Severin
    saas_relevance text,                              -- Konkrete SaaS-Produktrelevanz
    difficulty integer check (difficulty between 1 and 5),  -- 1=einfach, 5=komplex
    embedding vector(1536),                           -- Für semantische Suche
    sort_order integer default 0
);

-- Index für Vektorsuche auf Konzepten
create index if not exists idx_concepts_embedding
    on eam_concepts using ivfflat (embedding vector_cosine_ops)
    with (lists = 10);

-- ============================================================
-- 5) DECISION TRIGGERS — Produktentscheidung → Wissen
-- ============================================================
create table if not exists eam_decision_triggers (
    id text primary key,                              -- z.B. "dt_dashboard_metrics"
    product text not null check (product in ('klar-seite', 'sitebuildr', 'qa-system', 'general')),
    decision_de text not null,                        -- "Welche Metriken zeige ich im Dashboard?"
    decision_en text,
    domain_id text references eam_domains(id),
    concept_ids text[] default '{}',                  -- Verknüpfte Konzepte
    paper_ids text[] default '{}',                    -- Empfohlene Papers
    checkpoint_ids text[] default '{}',               -- Verknüpfte QA-Checkpoints
    priority text check (priority in ('HIGH','MEDIUM','LOW')),
    action_hint_de text,                              -- "Lies Paper X, Kapitel 3-4"
    embedding vector(1536),
    created_at timestamptz default now()
);

-- Index für Vektorsuche auf Decision Triggers
create index if not exists idx_triggers_embedding
    on eam_decision_triggers using ivfflat (embedding vector_cosine_ops)
    with (lists = 10);

-- ============================================================
-- 6) CONCEPT ↔ PAPER Verknüpfung (Knowledge Graph Edges)
-- ============================================================
create table if not exists eam_concept_papers (
    concept_id text references eam_concepts(id) on delete cascade,
    paper_id text references eam_papers(id) on delete cascade,
    relevance_score float default 0.8,                -- 0-1 wie relevant
    specific_section text,                            -- "Kapitel 3, Table 2"
    primary key (concept_id, paper_id)
);

-- ============================================================
-- 7) CONCEPT ↔ CHECKPOINT Verknüpfung (Brücke zum QA-System)
-- ============================================================
create table if not exists eam_concept_checkpoints (
    concept_id text references eam_concepts(id) on delete cascade,
    checkpoint_id text,                               -- ID aus bestehender checkpoints-Tabelle
    relationship text check (relationship in ('supports','implements','measures','validates')),
    primary key (concept_id, checkpoint_id)
);

-- ============================================================
-- 8) SUCHE: Vektorsuchfunktionen
-- ============================================================

-- Suche in Paper-Chunks
create or replace function match_paper_chunks(
    query_embedding vector(1536),
    match_threshold float default 0.7,
    match_count int default 8,
    filter_domain text default null,
    filter_paper text default null
)
returns table (
    id bigint,
    paper_id text,
    paper_title text,
    section_title text,
    content text,
    similarity float
)
language sql stable
as $$
    select
        pc.id,
        pc.paper_id,
        p.title as paper_title,
        pc.section_title,
        pc.content,
        1 - (pc.embedding <=> query_embedding) as similarity
    from eam_paper_chunks pc
    join eam_papers p on p.id = pc.paper_id
    where 1 - (pc.embedding <=> query_embedding) > match_threshold
      and (filter_domain is null or p.domain_id = filter_domain)
      and (filter_paper is null or pc.paper_id = filter_paper)
    order by pc.embedding <=> query_embedding
    limit match_count;
$$;

-- Suche in Konzepten
create or replace function match_concepts(
    query_embedding vector(1536),
    match_threshold float default 0.65,
    match_count int default 5
)
returns table (
    id text,
    domain_id text,
    name_de text,
    description_de text,
    why_it_matters text,
    saas_relevance text,
    similarity float
)
language sql stable
as $$
    select
        c.id,
        c.domain_id,
        c.name_de,
        c.description_de,
        c.why_it_matters,
        c.saas_relevance,
        1 - (c.embedding <=> query_embedding) as similarity
    from eam_concepts c
    where c.embedding is not null
      and 1 - (c.embedding <=> query_embedding) > match_threshold
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- Suche in Decision Triggers
create or replace function match_decision_triggers(
    query_embedding vector(1536),
    match_threshold float default 0.65,
    match_count int default 5,
    filter_product text default null
)
returns table (
    id text,
    product text,
    decision_de text,
    domain_id text,
    concept_ids text[],
    paper_ids text[],
    priority text,
    action_hint_de text,
    similarity float
)
language sql stable
as $$
    select
        dt.id,
        dt.product,
        dt.decision_de,
        dt.domain_id,
        dt.concept_ids,
        dt.paper_ids,
        dt.priority,
        dt.action_hint_de,
        1 - (dt.embedding <=> query_embedding) as similarity
    from eam_decision_triggers dt
    where dt.embedding is not null
      and 1 - (dt.embedding <=> query_embedding) > match_threshold
      and (filter_product is null or dt.product = filter_product)
    order by dt.embedding <=> query_embedding
    limit match_count;
$$;

-- ============================================================
-- 9) UNIFIED SEARCH — Sucht über ALLES
-- ============================================================
create or replace function eam_unified_search(
    query_embedding vector(1536),
    match_threshold float default 0.65,
    match_count int default 10
)
returns table (
    source_type text,
    source_id text,
    title text,
    content text,
    domain_id text,
    similarity float
)
language sql stable
as $$
    -- Paper Chunks
    (select
        'paper_chunk' as source_type,
        pc.paper_id as source_id,
        p.title as title,
        pc.content,
        p.domain_id,
        1 - (pc.embedding <=> query_embedding) as similarity
    from eam_paper_chunks pc
    join eam_papers p on p.id = pc.paper_id
    where 1 - (pc.embedding <=> query_embedding) > match_threshold
    order by pc.embedding <=> query_embedding
    limit match_count)

    union all

    -- Concepts
    (select
        'concept' as source_type,
        c.id as source_id,
        c.name_de as title,
        c.description_de as content,
        c.domain_id,
        1 - (c.embedding <=> query_embedding) as similarity
    from eam_concepts c
    where c.embedding is not null
      and 1 - (c.embedding <=> query_embedding) > match_threshold
    order by c.embedding <=> query_embedding
    limit 5)

    union all

    -- Decision Triggers
    (select
        'decision_trigger' as source_type,
        dt.id as source_id,
        dt.decision_de as title,
        dt.action_hint_de as content,
        dt.domain_id,
        1 - (dt.embedding <=> query_embedding) as similarity
    from eam_decision_triggers dt
    where dt.embedding is not null
      and 1 - (dt.embedding <=> query_embedding) > match_threshold
    order by dt.embedding <=> query_embedding
    limit 5)

    order by similarity desc
    limit match_count;
$$;
