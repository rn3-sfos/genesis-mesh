from langchain_community.tools.searx_search.tool import SearxSearchResults
from langchain_community.utilities.searx_search import SearxSearchWrapper
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
from os import environ


class SearchToolConfig(BaseModel):
    tool_name: str = Field(default="web_search_tool")
    tool_description: str = Field(
        default="""A versatile web search tool that performs searches using search engine. Returns structured search results from across the web."""
    )
    provider: Literal["searxng"] = Field(description="Search provider to use")
    base_url: Optional[str] = Field(
        description="The base URL for the search engine",
        pattern=r"https?:\/\/[A-Za-z0-9:.]+",
    )
    max_results: int = Field(
        description="Maximum number of results to fetch", ge=1, le=50
    )
    api_key: Optional[str] = Field(description="API Key for the search provider")
    search_params: Optional[Dict[str, str]] = Field(
        description="Additional parameters to pass to search engine (Note: overrides any defaults)"
    )


def get_search_tool(**search_params):
    config = SearchToolConfig(
        provider=environ.get("SEARCH_PROVIDER", "searxng"),
        base_url=environ.get("SEARCH_PROVIDER_BASE_URL", "http://localhost:8080"),
        max_results=environ.get("SEARCH_MAX_RESULTS", 10),
        api_key=environ.get("SEARCH_PROVIDER_API_KEY", None),
        search_params=search_params,
    )
    match (config.provider):
        case "searxng":
            wrapper = SearxSearchWrapper(
                searx_host=config.base_url,
                params=config.search_params if config.search_params else None,
            )
            return SearxSearchResults(
                name=config.tool_name,
                description=config.tool_description,
                wrapper=wrapper,
                num_results=config.max_results,
            )
