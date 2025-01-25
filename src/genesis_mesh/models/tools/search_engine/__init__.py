from typing import TypedDict

from pydantic import BaseModel, Field


class SearxNGInputSchema(BaseModel):
    query: str = Field(description="Query to search for")


class SearchResult(TypedDict):
    url: str
    title: str
    content: str
    score: float


class SearxNGResponse(TypedDict):
    results: list[SearchResult]
