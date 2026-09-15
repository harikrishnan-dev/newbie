import click

from src.backfill.backfill_gitlab import GITLAB_COLLECTION, backfill_gitlab_handbook
from src.retriever.retrieve_docs import retrieve_docs as retrieve_docs_handler


@click.group()
def cli() -> None:
    pass


@cli.command("backfill-gitlab")
@click.option(
    "--collection",
    default=GITLAB_COLLECTION,
    show_default=True,
    help="Weaviate collection to backfill the handbook into.",
)
def backfill_gitlab(collection: str) -> None:
    """Download the GitLab handbook and backfill its sections into Weaviate."""
    inserted = backfill_gitlab_handbook(collection_name=collection)
    click.echo(f"Backfilled {inserted} records into the '{collection}' collection.")


@cli.command("retrieve-docs")
@click.argument("query")
@click.option(
    "--collection",
    default=GITLAB_COLLECTION,
    show_default=True,
    help="Weaviate collection to search.",
)
@click.option("--limit", default=5, show_default=True, help="Maximum number of results to return.")
@click.option(
    "--alpha",
    default=0.5,
    show_default=True,
    help="Hybrid search weighting, 0-1: 0 is pure BM25, 1 is pure vector search.",
)
def retrieve_docs(query: str, collection: str, limit: int, alpha: float) -> None:
    """Run a hybrid (BM25 + vector) search to test the RAG retriever."""
    results = retrieve_docs_handler(query, collection_name=collection, limit=limit, alpha=alpha)
    if not results:
        click.echo("No results found.")
        return
    for i, result in enumerate(results, start=1):
        properties = result["properties"]
        click.echo(f"{i}. [{result['score']:.4f}] {properties.get('title')} — {properties.get('heading')}")
        click.echo(f"   {properties.get('content', '')[:200]}")
        click.echo()
