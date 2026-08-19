import json

from langchain_core.tools import tool

from agent.v6.config import KB_ROOT

# Real documents in this KB run 58-106 pages; anything past this is either a
# mistake or an attempt to force a huge in-memory page-range expansion.
MAX_PAGES = 200


def parse_pages(pages: str) -> list[int]:
    """Parse a page spec like "3-5,7,10-12" into a sorted, deduped list of page numbers."""
    result: set[int] = set()
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            result.update(range(int(start_str), int(end_str) + 1))
        else:
            result.add(int(part))
    return sorted(result)


@tool
def get_page_content(doc_name: str, pages: str) -> str:
    """
    Get the raw text content of specific pages from a long planning-guideline
    document. Only use this when a summary or concept page doesn't have
    enough detail -- prefer read_wiki_file for summaries/concepts/entities first.

    Args:
        doc_name: Document name without extension, e.g. "PEQ-alam-sekitar".
        pages: Page spec, e.g. "3-5,7,10-12".
    """
    normalized_doc_name = doc_name
    if normalized_doc_name.startswith("sources/"):
        normalized_doc_name = normalized_doc_name[len("sources/"):]
    if normalized_doc_name.endswith(".json"):
        normalized_doc_name = normalized_doc_name[: -len(".json")]

    target = (KB_ROOT / "sources" / f"{normalized_doc_name}.json").resolve()
    if not target.is_relative_to(KB_ROOT):
        return "Access denied: path escapes wiki root."
    if not target.is_file():
        return f"File not found: sources/{doc_name}.json"

    try:
        requested = set(parse_pages(pages))
    except ValueError:
        return f"Invalid page specification: {pages}"

    if len(requested) > MAX_PAGES:
        return f"Invalid page specification: {pages}"

    data = json.loads(target.read_text(encoding="utf-8"))
    matches = [entry for entry in data if entry.get("page") in requested]

    if not matches:
        return f"No content found for pages {pages} in {doc_name}."

    parts = [f"--- Page {entry['page']} ---\n{entry.get('content', '')}" for entry in matches]
    return "\n\n".join(parts)
