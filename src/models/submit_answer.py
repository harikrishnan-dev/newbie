from pydantic import BaseModel, Field


class SubmitAnswer(BaseModel):
    """Call this once you're ready to give the final answer, instead of replying in plain text."""

    answer: str = Field(description="The final answer to the user's question, based solely on retrieved handbook content.")
    citations: list[str] = Field(
        default_factory=list,
        description=(
            'Exact `path` attributes (from the <document path="...">  tags) of the documents you actually relied '
            "on, in the order you first used them. Don't include documents you didn't use."
        ),
    )
