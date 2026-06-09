-- surveyHelper schema (implements plan.md §10, with DECISIONS.md corrections)
-- Separates immutable identity & graph (facts) from derived analysis (re-runnable)
-- from the personal layer (yours). Raw Postgres + pgvector (Insforge-swap-compatible).
--
-- EMBED_DIM: embedding dimension is bound here AND in every vector index below.
-- Phase 0-1 does not use embeddings; default to 384 (local SentenceTransformers-friendly).
-- Changing the embedding model means updating vector(384) in BOTH tables + both indexes.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── identity & graph (facts) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS papers (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title         TEXT,
    authors       JSONB,
    year          INT,
    venue         TEXT,
    abstract      TEXT,
    arxiv_id      TEXT,
    doi           TEXT,
    s2_id         TEXT,
    openalex_id   TEXT,
    url           TEXT,
    pdf_url       TEXT,
    text_coverage TEXT,                 -- full | oa_pdf | abstract_only
    status        TEXT DEFAULT 'ok',
    min_depth     INT,
    retracted     BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);
-- unique-when-present external ids (dedup authority)
CREATE UNIQUE INDEX IF NOT EXISTS papers_arxiv_uq    ON papers (arxiv_id)    WHERE arxiv_id    IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS papers_s2_uq       ON papers (s2_id)       WHERE s2_id       IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS papers_doi_uq      ON papers (doi)         WHERE doi         IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS papers_openalex_uq ON papers (openalex_id) WHERE openalex_id IS NOT NULL;

-- every external id -> canonical paper (dedup backbone, plan §10)
CREATE TABLE IF NOT EXISTS paper_aliases (
    alias_id  TEXT PRIMARY KEY,         -- e.g. "arxiv:2310.01889", "s2:abcd", "doi:10.x/y"
    paper_id  BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE
);

-- the citation graph (edges)
CREATE TABLE IF NOT EXISTS citations (
    src           BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    dst           BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    edge_type     TEXT NOT NULL DEFAULT 'reference',  -- reference | citation
    is_influential BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (src, dst, edge_type)
);
CREATE INDEX IF NOT EXISTS citations_dst_idx ON citations (dst);  -- reverse/bidirectional traversal

-- ── derived analysis (re-runnable, versioned, per-step status) ────────────────
CREATE TABLE IF NOT EXISTS paper_analysis (
    paper_id         BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    pipeline_version TEXT NOT NULL,
    step_status      JSONB,             -- {"0":"ok","1":"partial",...}
    purpose          TEXT,
    pain_point       TEXT,
    architecture     JSONB,
    method           JSONB,
    results          JSONB,
    limitations      JSONB,
    code             JSONB,
    provenance       JSONB,
    model_used       TEXT,
    analyzed_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (paper_id, pipeline_version)
);

CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_id  BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    embedding vector(384),              -- EMBED_DIM (see header)
    PRIMARY KEY (paper_id, kind)
);
CREATE INDEX IF NOT EXISTS paper_embeddings_hnsw
    ON paper_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS syntheses (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope            TEXT,
    root_or_topic    TEXT,
    paper_set        JSONB,
    lineage          JSONB,
    open_problems    JSONB,
    contradictions   JSONB,
    map              JSONB,
    pipeline_version TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- ── personal layer (you) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interests (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label      TEXT NOT NULL,
    embedding  vector(384),             -- EMBED_DIM (see header)
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_user_state (
    paper_id    BIGINT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    state       TEXT,                   -- seen | read | understood | dismissed
    why         TEXT,                   -- the triggering intent/question
    interest_id BIGINT REFERENCES interests(id) ON DELETE SET NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corrections (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paper_id        BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    field           TEXT,
    corrected_value JSONB,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── operational ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_jobs (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type            TEXT NOT NULL,      -- analyze | expand | synthesize | proactive_scan
    root_paper_id   BIGINT REFERENCES papers(id) ON DELETE SET NULL,
    requested_depth INT,
    current_depth   INT,
    status          TEXT DEFAULT 'pending',  -- pending|running|paused_budget|done|failed
    parent_job_id   BIGINT REFERENCES research_jobs(id) ON DELETE SET NULL,
    triggered_by    TEXT,
    budget          JSONB,
    run_after       TIMESTAMPTZ DEFAULT now(),   -- deferred retry (e.g. S2 throttled)
    attempts        INT DEFAULT 0,
    priority        INT DEFAULT 100,             -- lower runs first; user 50, ambient deepen 200
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS research_jobs_claim_idx ON research_jobs (status, run_after);

-- BFS frontier queue for resumable expand jobs (DECISIONS.md §D #6)
CREATE TABLE IF NOT EXISTS job_papers (
    job_id    BIGINT NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    paper_id  BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    depth     INT,
    tier      TEXT,
    status    TEXT DEFAULT 'queued',    -- queued | analyzing | done | failed
    PRIMARY KEY (job_id, paper_id)
);

CREATE TABLE IF NOT EXISTS usage_log (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id   BIGINT REFERENCES research_jobs(id) ON DELETE SET NULL,
    source   TEXT,
    calls    INT,
    tokens   INT,
    cost_usd NUMERIC,
    at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id     BIGINT REFERENCES research_jobs(id) ON DELETE SET NULL,
    kind       TEXT,
    payload    JSONB,
    digest_key TEXT,
    delivered  BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value JSONB
);

-- cross-process rate limiter (plan §9): one global per-source bucket shared by the
-- MCP server (foreground) and the worker (background), so they never collide on 429s.
CREATE TABLE IF NOT EXISTS rate_limit (
    source    TEXT PRIMARY KEY,
    next_slot TIMESTAMPTZ DEFAULT now()
);
