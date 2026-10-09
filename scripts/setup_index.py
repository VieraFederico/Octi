"""Create Octi's Pinecone index if it does not exist yet.

Run from the repository root:  python -m scripts.setup_index

This is the only code allowed to create the index (BR-004); the app only checks it. Running it
again is safe: an existing index with the right shape is left alone, and one with the wrong shape is
reported, never deleted. Exit code 0 means the index is ready; anything else means it is not.
Error output is always the leaf error's `user_message`, never raw library text (BR-007).
"""

import sys

from services.errors import AppError
from services.logging_setup import configure_logging
from services.settings import Settings, get_settings
from services.vector_store import PINECONE_CLOUD, PINECONE_METRIC, PINECONE_REGION, IndexClient, ensure_index


def main(settings: Settings | None = None, client: IndexClient | None = None) -> int:
    """Run the setup and return the exit code. Tests pass fake `settings` and a stub `client`."""
    try:
        settings = settings if settings is not None else get_settings()
        configure_logging(settings)
        result = ensure_index(settings, client)
    except AppError as exc:
        print(exc.user_message, file=sys.stderr)
        return 1

    name = settings.PINECONE_INDEX_NAME
    if result == "created":
        print(
            f"Index '{name}' created: {settings.EMBEDDING_DIMENSION} dimensions, {PINECONE_METRIC}, "
            f"{PINECONE_CLOUD}/{PINECONE_REGION}."
        )
    else:
        print(f"Index '{name}' already exists with the expected shape. Nothing changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
