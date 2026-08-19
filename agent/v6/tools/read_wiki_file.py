from langchain_core.tools import tool

from agent.v6.config import KB_ROOT


@tool
def read_wiki_file(path: str) -> str:
    """
    Read a Markdown file from the planning-guideline knowledge base wiki.

    Args:
        path: File path relative to the wiki root, e.g. "index.md",
            "summaries/PEQ-Perindustrian.md", "concepts/buffer-zone-requirements.md".
    """
    full_path = (KB_ROOT / path).resolve()
    if not full_path.is_relative_to(KB_ROOT):
        return "Access denied: path escapes wiki root."
    if not full_path.exists():
        return f"File not found: {path}"
    return full_path.read_text(encoding="utf-8")
