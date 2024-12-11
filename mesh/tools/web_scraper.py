from mesh.utils.playwright_scraper import PlaywrightScraper
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type
from inspect import cleandoc
import asyncio
from logging import Logger

logger = Logger(name=__file__)


class WebScraperInput(BaseModel):
    urls: list[str] = Field(description="A list of URLs to scrape from the internet.")


class WebScraper(BaseTool):
    name: str = "web_scraping_tool"
    description: str = cleandoc(
        """
        The WebScraper tool to perform efficient, asynchronous web scraping.
        It extracts website content and downloads. Ideal for gathering information and files from web pages.
        """
    )
    args_schema: Type[BaseModel] = WebScraperInput
    web_parser: PlaywrightScraper = PlaywrightScraper()

    def _run(self, urls: list[str]) -> str:
        return asyncio.run(self._arun(urls))

    async def _arun(self, urls: list[str]) -> str:
        return await self.web_parser.get_content(urls)
