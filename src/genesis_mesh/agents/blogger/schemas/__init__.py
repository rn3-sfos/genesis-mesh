from operator import add
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Section(BaseModel):
    name: str = Field(
        description="Name for this section of the blog.",
    )
    description: str = Field(
        description="Brief overview of the main topics and concepts to be covered in this section.",
    )
    research: bool = Field(
        description="Whether to perform web research for this section of the blog."
    )
    content: str = Field(description="The content of the section.")


class Sections(BaseModel):
    sections: list[Section] = Field(
        description="Sections of the blog.",
    )


class SearchQuery(BaseModel):
    search_query: str = Field(description="Query for web search.")


class Queries(BaseModel):
    queries: list[SearchQuery] = Field(
        description="List of search queries.",
    )


class BlogStateInput(TypedDict):
    topic: str


class BlogStateOutput(TypedDict):
    final_blog: str


class BlogState(TypedDict):
    topic: str
    sections: list[Section]
    completed_sections: Annotated[list, add]
    blog_sections_from_research: str
    final_blog: str


class SectionState(TypedDict):
    section: Section
    search_queries: list[SearchQuery]
    source_str: str
    blog_sections_from_research: str
    completed_sections: list[Section]


class SectionOutputState(TypedDict):
    completed_sections: list[Section]
