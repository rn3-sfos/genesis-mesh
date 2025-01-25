from typing import Any

from aiohttp import ClientSession
from langchain_core.tools import BaseTool

from genesis_mesh.configs.tools.searxng import SearxNGConfig
from genesis_mesh.models.tools.search_engine import SearxNGInputSchema, SearxNGResponse


class SearxNGTool(BaseTool):
    name: str = "Web Search Tool"
    description: str = (
        "A tool to search for relevant URLs for a query. You can also use this tool to search about current events."
    )
    args_schema: Any = SearxNGInputSchema
    searxng_config: SearxNGConfig = SearxNGConfig()
    http_client: ClientSession

    def _run(self, *args, **kwargs):
        raise NotImplementedError

    async def _arun(self, query: str):
        req_params = {
            "q": query,
            "engines": self.searxng_config.engines,
            "language": "en",
            "format": "json",
        }
        async with self.http_client.get(
            f"{self.searxng_config.base_url}{self.searxng_config.search_path}",
            params=req_params,
        ) as response:
            search_response: SearxNGResponse = await response.json()
            return [
                {
                    "url": result["url"],
                    "title": result["title"],
                    "summary": result["content"],
                }
                for result in search_response["results"]
                if result["score"] >= self.searxng_config.min_score
            ]
