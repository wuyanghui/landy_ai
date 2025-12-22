import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # pragma: no cover - defensive path injection
    sys.path.insert(0, str(ROOT))


from utility.property_listing_init import (  # noqa: E402  # pylint: disable=C0413
    _ensure_client,
    get_property_listing,
    reset_client_for_tests,
)


class DummyCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, query):  # pragma: no cover - simple passthrough
        assert query == {}
        return self.documents


class DummyDB(dict):
    def __getitem__(self, item):
        if item not in self:
            raise KeyError(item)
        return super().__getitem__(item)


class DummyClient:
    def __init__(self, documents):
        self.documents = documents

    def __getitem__(self, item):
        if item != "property":
            raise KeyError(item)
        db = DummyDB()
        db["property-listing"] = DummyCollection(self.documents)
        return db

    class admin:
        @staticmethod
        def command(command):  # pragma: no cover - unused in tests but kept for compatibility
            if command != "ping":
                raise ValueError("Unsupported command")


@pytest.fixture(autouse=True)
def _reset_client():
    reset_client_for_tests()
    yield
    reset_client_for_tests()


def test_get_property_listing_returns_documents(monkeypatch):
    monkeypatch.setattr(
        "utility.property_listing_init._ensure_client",
        lambda: DummyClient([{"_id": 1}, {"_id": 2}]),
    )

    documents = get_property_listing()
    assert documents == [{"_id": 1}, {"_id": 2}]


def test_ensure_client_raises_without_env(monkeypatch):
    monkeypatch.delenv("MONGODB_PW", raising=False)
    with pytest.raises(RuntimeError):
        _ensure_client()
