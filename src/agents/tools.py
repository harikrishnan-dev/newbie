"""Agent-specific tool for the retrieval agent's tool-calling loop.

Wraps the generic `retrieve_docs` hybrid-search retriever (see
`src/retriever/retrieve_docs.py`) as a single-argument tool, closing over the
collection/limit/alpha defaults rather than exposing them to the LLM.
"""

from langchain_core.tools import tool

from src.retriever.retrieve_docs import retrieve_docs


@tool
def search_handbook(query: str) -> str:
    """Search the company handbook for information relevant to `query` and return matching excerpts."""
    results = retrieve_docs(query)
    if not results:
        return "No relevant handbook sections found."
    # Each result is wrapped in a <document path="..."> tag rather than just
    # joined with blank lines: several results are often near-duplicates of
    # each other (e.g. the same policy repeated per country/entity), and a
    # loose "\n\n"-separated blob makes it easy for the model to blend two
    # results' content or cite the wrong one's path. Claude in particular is
    # trained to track document boundaries reliably when they're XML tags.
    return "\n\n".join(
        f'<document path="{result["properties"].get("path")}">\n'
        f'# {result["properties"].get("heading")}\n'
        f'{result["properties"].get("content")}\n'
        f"</document>"
        for result in results
    )
