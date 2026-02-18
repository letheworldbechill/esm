"""
EAM Knowledge Cockpit — Konfiguration
"""
import os

# --- Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # service_role key

# --- OpenAI (Embeddings) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# --- Anthropic (LLM) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 4096

# --- RAG Parameter ---
RETRIEVAL_TOP_K = 8
RETRIEVAL_THRESHOLD = 0.65
CHUNK_SIZE = 800           # Tokens pro Chunk
CHUNK_OVERLAP = 100        # Überlappung

# --- PDF Verzeichnis ---
PAPERS_DIR = os.environ.get("PAPERS_DIR", "/opt/eam-cockpit/papers")
