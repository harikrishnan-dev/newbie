"""Download the GitLab handbook repo and parse its markdown files.

The handbook (https://gitlab.com/gitlab-com/content-sites/handbook) is a Hugo
site: markdown files under `content/` start with a YAML frontmatter block
delimited by `---` lines, followed by the page body.
"""

import subprocess
from pathlib import Path

from src.backfill.synthesizer import synthesize_records
from src.backfill.util import (
    _MIN_CONTENT_LENGTH,
    MarkdownDocument,
    _is_noisy_content,
    _split_frontmatter,
    _split_sections,
)
from src.store.weaviate import WeaviateStore, default_vector_index_type, default_vectorizer

HANDBOOK_REPO_URL = "https://gitlab.com/gitlab-com/content-sites/handbook.git"
DEFAULT_CLONE_DIR = Path(".cache/handbook")

GITLAB_COLLECTION = "gitlab"
_RECORD_PROPERTIES = {"path": "text", "title": "text", "heading": "text", "content": "text"}


def download_handbook(
    dest_dir: Path | str = DEFAULT_CLONE_DIR, repo_url: str = HANDBOOK_REPO_URL
) -> Path:
    """Clone the handbook repo into `dest_dir`, or pull if it's already cloned there."""
    dest = Path(dest_dir)
    if (dest / ".git").exists():
        subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"], check=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", repo_url, str(dest)], check=True)
    return dest


def parse_markdown_files(root_dir: Path | str) -> list[MarkdownDocument]:
    """Parse every markdown file under `root_dir` into frontmatter metadata + body content."""
    root = Path(root_dir)
    documents = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, body = _split_frontmatter(text)
        sections = _split_sections(body, title=metadata.get("title", ""))
        documents.append(
            MarkdownDocument(path=str(path.relative_to(root)), metadata=metadata, content=sections)
        )
    return documents


def filter_noisy_records(
    docs: list[MarkdownDocument], min_content_length: int = _MIN_CONTENT_LENGTH
) -> list[MarkdownDocument]:
    """Drop sections whose content is too sparse/boilerplate to be worth indexing.

    Returns new `MarkdownDocument`s with noisy sections removed from each
    document's `content` (`path`/`metadata` untouched), and drops documents
    left with no sections at all once every one of theirs turned out noisy.
    """
    filtered = [
        MarkdownDocument(
            path=doc.path,
            metadata=doc.metadata,
            content=[
                section
                for section in doc.content
                if not any(_is_noisy_content(text, min_content_length) for text in section.values())
            ],
        )
        for doc in docs
    ]
    return [doc for doc in filtered if doc.content]


def backfill_gitlab_handbook(collection_name: str = GITLAB_COLLECTION) -> int:
    """Download the handbook, parse it, and dump its sections into Weaviate.

    Drops `collection_name` first if it already exists, then recreates it
    from scratch, so each run is a full reload rather than appending
    duplicate records on top of a previous run. Returns the number of
    records successfully inserted.
    """
    handbook_dir = download_handbook()
    docs = parse_markdown_files(handbook_dir / "content" / "handbook")
    docs = filter_noisy_records(docs)
    docs = synthesize_records(docs)

    records = [
        {"path": doc.path, "title": doc.metadata.get("title", ""), "heading": heading, "content": content}
        for doc in docs
        for section in doc.content
        for heading, content in section.items()
    ]

    with WeaviateStore() as store:
        if store.collection_exists(collection_name):
            store.delete_collection(collection_name)
        store.create_collection(
            collection_name,
            _RECORD_PROPERTIES,
            vectorizer=default_vectorizer(),
            vector_index_type=default_vector_index_type(),
        )
        failed = store.add_records(collection_name, records)

    return len(records) - failed


if __name__ == "__main__":
    inserted = backfill_gitlab_handbook()
    print(f"Backfilled {inserted} records into the '{GITLAB_COLLECTION}' collection")
