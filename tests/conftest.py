"""Shared pytest fixtures for the Convoy server (S1.7).

Point CONVOY_DB at a throwaway path *before* anything imports
server.models, then give each test a fresh DB file + fresh app lifespan.
"""

import os
import tempfile

# Must be set before server.models is imported anywhere.
os.environ["CONVOY_DB"] = os.path.join(tempfile.gettempdir(), "convoy_test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server.main import app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    """A TestClient with an isolated, freshly-initialised DB per test."""
    os.environ["CONVOY_DB"] = str(tmp_path / "convoy_test.db")
    with TestClient(app) as c:
        yield c
