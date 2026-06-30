"""Commission transcript source discovery and retrieval."""

from commission_ingestion.env import load_dotenv

# Make a repo-root .env the single source of truth for credentials so a fresh
# shell never silently drops NEO4J_PASSWORD / ANTHROPIC_API_KEY. Shell exports win.
load_dotenv()

__version__ = "0.1.0"
