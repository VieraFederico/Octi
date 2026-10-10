"""Live smoke test: the real services, with the developer's real `.env` (spec FR-035, VC-041).

Excluded from the default run (`pytest.ini` adds `-m "not live"`). Run it on purpose with:

    pytest -m live

It calls the same `run_checks()` as `python -m scripts.check_services`, so the script and this test
cannot disagree. It spends a little proxy budget: one chat call and one embedding call.
"""

import pytest

from services.health import run_checks


@pytest.mark.live
def test_every_service_check_passes() -> None:
    """VC-041: configuration, models, chat, embeddings, Pinecone and LangSmith all answer; no FAIL line.

    A `skipped` git line is fine (S00-D-014). On failure, pytest shows the FAIL lines, which hold only
    safe reasons (BR-007), never a key.
    """
    results = run_checks()
    failures = [result.line() for result in results if result.status == "FAIL"]
    assert failures == []
