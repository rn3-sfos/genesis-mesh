from asyncio import Semaphore, gather
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # type: ignore
from langchain_core.tools import BaseTool

from genesis_mesh.models.tools.crawler import WebCrawlerInputSchema


class WebCrawlerTool(BaseTool):
    name: str = "Web Crawler"
    description: str = "Use this tool to extract the content from a list of URLs."
    args_schema: Any = WebCrawlerInputSchema
    max_concurrency: int = 4
    browser_config: BrowserConfig = BrowserConfig(text_mode=True, light_mode=True)
    crawler_config: CrawlerRunConfig = CrawlerRunConfig(
        excluded_tags=["header", "footer", "nav"],
    )

    def _run(self, *args, **kwargs):
        raise NotImplementedError

    async def _arun(self, urls: list[str]):
        semaphore = Semaphore(value=self.max_concurrency)
        async with AsyncWebCrawler(config=self.browser_config) as crawler:

            async def get_crawler_result(url):
                async with semaphore:
                    result = await crawler.arun(url=url, config=self.crawler_config)
                    return {"content": result.markdown, "url": result.url}

            return await gather(*[get_crawler_result(url) for url in urls])
