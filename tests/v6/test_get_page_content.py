import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v6.tools.get_page_content as get_page_content_module


def test_parse_pages_handles_ranges_and_singles():
    assert get_page_content_module.parse_pages("3-5,7,10-12") == [3, 4, 5, 7, 10, 11, 12]


def test_parse_pages_dedupes_and_sorts():
    assert get_page_content_module.parse_pages("5,3,4-5,3") == [3, 4, 5]


def test_returns_matching_page_content(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = [
        {"page": 1, "content": "Page one text"},
        {"page": 2, "content": "Page two text"},
        {"page": 3, "content": "Page three text"},
    ]
    (sources_dir / "test-doc.json").write_text(json.dumps(doc), encoding="utf-8")

    result = get_page_content_module.get_page_content.invoke(
        {"doc_name": "test-doc", "pages": "1,3"}
    )

    assert "Page one text" in result
    assert "Page three text" in result
    assert "Page two text" not in result


def test_missing_document_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)

    result = get_page_content_module.get_page_content.invoke(
        {"doc_name": "nope", "pages": "1"}
    )

    assert result == "File not found: sources/nope.json"


def test_no_matching_pages_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "test-doc.json").write_text(
        json.dumps([{"page": 1, "content": "x"}]), encoding="utf-8"
    )

    result = get_page_content_module.get_page_content.invoke(
        {"doc_name": "test-doc", "pages": "99"}
    )

    assert result == "No content found for pages 99 in test-doc."
