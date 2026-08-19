import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.sync_kb as sync_kb_module


def test_sync_copies_wiki_excluding_images(tmp_path):
    source = tmp_path / "source_wiki"
    dest = tmp_path / "dest_kb"

    (source / "summaries").mkdir(parents=True)
    (source / "summaries" / "doc.md").write_text("# Summary", encoding="utf-8")
    (source / "sources" / "images" / "doc").mkdir(parents=True)
    (source / "sources" / "images" / "doc" / "p1.png").write_bytes(b"fake-image-data")
    (source / "sources" / "doc.json").write_text("[]", encoding="utf-8")
    (source / "index.md").write_text("# Index", encoding="utf-8")

    sync_kb_module.sync_kb(source, dest)

    assert (dest / "index.md").read_text(encoding="utf-8") == "# Index"
    assert (dest / "summaries" / "doc.md").exists()
    assert (dest / "sources" / "doc.json").exists()
    assert not (dest / "sources" / "images").exists()


def test_sync_replaces_existing_dest(tmp_path):
    source = tmp_path / "source_wiki"
    dest = tmp_path / "dest_kb"
    source.mkdir()
    (source / "index.md").write_text("new content", encoding="utf-8")

    dest.mkdir()
    (dest / "stale.md").write_text("old file that should be removed", encoding="utf-8")

    sync_kb_module.sync_kb(source, dest)

    assert (dest / "index.md").read_text(encoding="utf-8") == "new content"
    assert not (dest / "stale.md").exists()


def test_sync_raises_if_source_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        sync_kb_module.sync_kb(tmp_path / "does-not-exist", tmp_path / "dest")
