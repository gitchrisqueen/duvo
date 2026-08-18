"""A deliberately unhelpful stand-in for the customer's upstream system.

The mock is generic: it serves whatever JSON fixture it is given, so the domain
written during the exercise supplies its own data without this file changing.

Three behaviours are intentional, because they are the behaviours real
integrations actually have and the ones a submission is most likely to get
wrong:

1. **It authenticates every request** against a key read from disk on each call,
   so a key rotation can be demonstrated end to end against a running stack.
2. **It is not idempotent.** Posting the same payload twice creates two records.
   Deduplication is our server's job, and a mock that quietly deduplicated would
   hide whether we actually do it.
3. **It returns only the fields in the fixture.** Nothing is invented, so code
   that reads a field the upstream never sends fails here rather than in front
   of a reviewer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

__all__ = ["build_app"]


def _load_fixtures(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Load collections from a fixture file.

    Args:
        path: Fixture file containing an object mapping collection names to
            lists of records. ``None`` yields empty collections.

    Returns:
        The loaded collections.
    """
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(name): list(records) for name, records in data.items()}


def _read_expected_key() -> str | None:
    """Read the API key the mock currently expects.

    The key is re-read on every request so that rotating the file is observable
    from outside the process, which is what makes the rotation runbook testable.

    Returns:
        The expected key, or ``None`` when authentication is disabled.
    """
    key_path = os.environ.get("MOCK_UPSTREAM_API_KEY_FILE")
    if key_path:
        try:
            return Path(key_path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return os.environ.get("MOCK_UPSTREAM_API_KEY") or None


def build_app() -> FastAPI:
    """Construct the mock application.

    Returns:
        A FastAPI application serving the configured fixtures.
    """
    fixtures_path = os.environ.get("MOCK_UPSTREAM_FIXTURES")
    collections = _load_fixtures(Path(fixtures_path) if fixtures_path else None)
    writes: dict[str, list[dict[str, Any]]] = {}

    app = FastAPI(title="Mock upstream", docs_url=None, redoc_url=None)

    def _authenticate(supplied: str | None) -> None:
        """Reject a request whose key does not match the current expected key.

        Args:
            supplied: The value of the ``X-API-Key`` header.

        Raises:
            HTTPException: With status 401 when the key is missing or wrong.
        """
        expected = _read_expected_key()
        if expected is None:
            return
        if supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid API key.")

    @app.get("/__health")
    def health() -> dict[str, str]:
        """Report that the mock is serving.

        Returns:
            A static status payload. Unauthenticated by design.
        """
        return {"status": "ok"}

    @app.get("/{collection}")
    def list_records(
        collection: str, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List the records in a collection.

        Args:
            collection: Collection name.
            x_api_key: Caller-supplied API key.

        Returns:
            The records plus the number written since startup.

        Raises:
            HTTPException: With status 404 when the collection is unknown.
        """
        _authenticate(x_api_key)
        if collection not in collections:
            raise HTTPException(status_code=404, detail="Unknown collection.")
        return {"items": collections[collection] + writes.get(collection, [])}

    @app.get("/{collection}/{record_id}")
    def get_record(
        collection: str, record_id: str, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one record by id.

        Args:
            collection: Collection name.
            record_id: Identifier of the record.
            x_api_key: Caller-supplied API key.

        Returns:
            The matching record.

        Raises:
            HTTPException: With status 404 when the record does not exist.
        """
        _authenticate(x_api_key)
        for record in collections.get(collection, []) + writes.get(collection, []):
            if str(record.get("id")) == record_id:
                return record
        raise HTTPException(status_code=404, detail="Unknown record.")

    @app.post("/{collection}", status_code=201)
    async def create_record(
        collection: str, request: Request, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Create a record. Deliberately not idempotent.

        Args:
            collection: Collection name.
            request: The incoming request, read as JSON.
            x_api_key: Caller-supplied API key.

        Returns:
            The created record, including the id the mock assigned.
        """
        _authenticate(x_api_key)
        payload = await request.json()
        bucket = writes.setdefault(collection, [])
        record = {"id": f"{collection}-{len(bucket) + 1}", **payload}
        bucket.append(record)
        return record

    return app


app = build_app()
