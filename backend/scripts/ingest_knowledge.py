"""Local-only ingestion command for curated EventPilot knowledge files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag import ingest_local_knowledge, initialize_rag_storage


if __name__ == "__main__":
    initialize_rag_storage()
    for source, count in ingest_local_knowledge().items():
        print(f"{source}: indexed {count} chunks")
