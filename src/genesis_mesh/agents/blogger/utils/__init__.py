from asyncio import gather
from inspect import cleandoc

from aiohttp import ClientSession

from genesis_mesh.agents.blogger.schemas import SearchQuery, Section
from genesis_mesh.tools.crawler import WebCrawlerTool
from genesis_mesh.tools.search_engine import SearxNGTool


class UtilityFunctions:
    def __init__(self, http_client: ClientSession):
        self.search_tool = SearxNGTool(http_client=http_client)
        self.crawler_tool = WebCrawlerTool()

    def deduplicate_and_format_sources(
        self,
        search_response: list[dict[str, str]],
        max_tokens_per_source: int,
        *,
        include_raw_content: bool,
    ):
        unique_sources: dict[str, dict[str, str]] = {}
        for source in search_response:
            if source["url"] not in unique_sources:
                unique_sources[source["url"]] = source

        formatted_text = "Sources:\n\n"
        for source in unique_sources.values():
            formatted_text += f"Source {source['title']}:\n===\n"
            formatted_text += f"URL: {source['url']}\n===\n"
            formatted_text += f"Content summary from source: {source['summary']}\n===\n"
            if include_raw_content:
                # Using rough estimate of 4 characters per token
                char_limit = max_tokens_per_source * 4
                # Handle None content
                content = source.get("content")
                if content is None:
                    content = ""
                if len(content) > char_limit:
                    content = content[:char_limit] + "... [truncated]"
                formatted_text += f"Content from source: {content}\n\n"

        return formatted_text.strip()

    def format_sections(self, sections: list[Section]) -> str:
        formatted_str = ""
        for idx, section in enumerate(sections, 1):
            formatted_str += cleandoc(
                f"""
                {"=" * 60}
                Section {idx}: {section.name}
                {"=" * 60}
                Description:
                {section.description}
                Requires Research:
                {section.research}

                Content:
                {section.content if section.content else "[Not yet written]"}

                """
            )
        return formatted_str

    async def search(self, search_queries: list[SearchQuery]):
        search_results: list[dict[str, str]] = []

        async def get_search_results(query: str):
            results = await self.search_tool.ainvoke(input={"query": query})
            search_results.extend(results)

        async def enrich_results_with_web_content() -> list[dict[str, str]]:
            urls = [result["url"] for result in search_results]
            web_crawler_results: list[dict[str, str]] = await self.crawler_tool.ainvoke(
                input={"urls": urls}
            )
            return [
                {**d1, **d2}
                for d1 in search_results
                for d2 in web_crawler_results
                if d1["url"] == d2["url"]
            ]

        await gather(
            *[get_search_results(query.search_query) for query in search_queries]
        )
        return await enrich_results_with_web_content()
