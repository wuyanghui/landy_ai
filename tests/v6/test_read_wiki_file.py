import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v6.tools.read_wiki_file as read_wiki_file_module


def test_reads_existing_file(tmp_path, monkeypatch):
    (tmp_path / "index.md").write_text("# KB Index", encoding="utf-8")
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file_module.read_wiki_file.invoke({"path": "index.md"})

    assert result == "# KB Index"


def test_reads_nested_file(tmp_path, monkeypatch):
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "buffer-zone-requirements.md").write_text(
        "# Buffer Zones", encoding="utf-8"
    )
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file_module.read_wiki_file.invoke(
        {"path": "concepts/buffer-zone-requirements.md"}
    )

    assert result == "# Buffer Zones"


def test_missing_file_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file_module.read_wiki_file.invoke({"path": "nope.md"})

    assert result == "File not found: nope.md"


def test_path_escape_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file_module.read_wiki_file.invoke({"path": "../../etc/passwd"})

    assert result == "Access denied: path escapes wiki root."


def test_directory_path_returns_message(tmp_path, monkeypatch):
    (tmp_path / "concepts").mkdir()
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file_module.read_wiki_file.invoke({"path": "concepts"})

    assert result == "File not found: concepts"
