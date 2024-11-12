from langchain.tools import BaseTool
from langchain.schema import Document
from langchain_community.document_transformers import MarkdownifyTransformer
from playwright.async_api import async_playwright, BrowserContext, Download, Page
from pydantic import BaseModel, Field
from typing import Type, List, Optional, Dict
from inspect import cleandoc
import asyncio
import os
from tempfile import gettempdir
from logging import Logger
from uuid import uuid4
from json import dumps
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

logger = Logger(name=__file__)


class PageContent(BaseModel):
    url: str
    content: str
    method: str = "playwright"  # Track which method was used to scrape


class WebScraperInput(BaseModel):
    urls: List[str] = Field(description="A list of URLs to scrape from the internet.")


class WebScraper(BaseTool):
    name: str = "web_scraping_tool"
    description: str = cleandoc(
        """
        Enhanced WebScraper tool with multiple scraping strategies and optimizations.
        """
    )
    args_schema: Type[BaseModel] = WebScraperInput
    max_concurrent: int = 4  # Increased from 2
    download_path: str = gettempdir()
    semaphore: asyncio.Semaphore = asyncio.Semaphore()
    md_transformer: MarkdownifyTransformer = MarkdownifyTransformer()
    browser_pool: List[tuple] = []
    session: Optional[aiohttp.ClientSession] = None

    # Precompile regex patterns
    js_pattern = re.compile(r"\.js$")
    image_pattern = re.compile(r"\.(jpg|jpeg|png|gif|webp)$")

    async def initialize(self):
        """Initialize browser pool and aiohttp session"""
        if not self.browser_pool:
            async with async_playwright() as playwright:
                for _ in range(self.max_concurrent):
                    browser = await playwright.firefox.launch(
                        headless=True,
                        timeout=0,
                        firefox_user_prefs={
                            "media.autoplay.default": 5,
                            "media.autoplay.blocking_policy": 2,
                            "permissions.default.image": 2,  # Disable images
                        },
                    )
                    context = await browser.new_context(
                        viewport={"height": 1080, "width": 1920},
                        ignore_https_errors=True,
                        java_script_enabled=True,
                        accept_downloads=True,
                    )
                    self.browser_pool.append((browser, context))

        if not self.session:
            self.session = aiohttp.ClientSession()

    async def cleanup(self):
        """Cleanup resources"""
        for browser, context in self.browser_pool:
            await context.close()
            await browser.close()
        self.browser_pool = []

        if self.session:
            await self.session.close()
            self.session = None

    async def __get_simple_html(self, url: str) -> Optional[str]:
        """Attempt to fetch content using aiohttp first"""
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" in content_type:
                        html = await response.text()
                        soup = BeautifulSoup(html, "html.parser")
                        # Remove scripts, styles, and other unnecessary elements
                        for script in soup(
                            ["script", "style", "meta", "link", "noscript"]
                        ):
                            script.decompose()
                        return str(soup)
        except Exception as e:
            logger.debug(f"Simple HTML fetch failed for {url}: {str(e)}")
        return None

    async def __enhanced_page_setup(self, page: Page):
        """Setup enhanced page blocking and optimization"""
        await page.route(
            re.compile(r"\.(jpg|jpeg|png|gif|webp|css|svg|woff|woff2|ttf|eot)$"),
            lambda route: route.abort(),
        )

        # Block tracking and analytics
        await page.route(
            re.compile(
                r"(google-analytics|googletagmanager|doubleclick|facebook|analytics)\."
            ),
            lambda route: route.abort(),
        )

        # Block non-essential third-party requests
        await page.route(
            re.compile(r"^https?://(?!www\.|(?![\w-]+\.)?yourdomain\.com)"),
            lambda route: (
                route.abort()
                if any(
                    ext in route.request.url.lower()
                    for ext in [".js", ".css", ".gif", ".jpg", ".jpeg", ".png", ".webp"]
                )
                else route.continue_()
            ),
        )

    async def __get_page_content(
        self, url: str, context: BrowserContext, content: List[PageContent]
    ) -> None:
        logger.warning(f"Scraping {url}")
        async with self.semaphore:
            try:
                # Try simple HTML fetch first
                simple_html = await self.__get_simple_html(url)
                if simple_html:
                    markdown_content = self.md_transformer.transform_documents(
                        [Document(page_content=simple_html)]
                    )
                    page_content = "\n".join(
                        [doc.page_content for doc in markdown_content]
                    )
                    if len(page_content) > 0:
                        content.append(
                            PageContent(url=url, content=page_content, method="simple")
                        )
                        return

                # Fall back to Playwright if simple fetch fails or content is empty
                page = await context.new_page()
                await self.__enhanced_page_setup(page)
                page.set_default_timeout(15000)  # 15-second timeout

                try:
                    response = await page.goto(url, wait_until="domcontentloaded")
                    if response and response.ok:
                        page_content = await page.content()
                        markdown_content = self.md_transformer.transform_documents(
                            [Document(page_content=page_content)]
                        )
                        page_content = "\n".join(
                            [doc.page_content for doc in markdown_content]
                        )
                        if len(page_content) > 0:
                            content.append(
                                PageContent(
                                    url=url, content=page_content, method="playwright"
                                )
                            )
                except Exception as e:
                    logger.error(f"Page navigation failed for {url}: {str(e)}")
                finally:
                    await page.close()

            except Exception as e:
                logger.error(f"Content extraction failed for {url}: {str(e)}")

        logger.warning(f"Done {url}")

    async def _arun(self, urls: List[str]) -> str:
        await self.initialize()
        results: List[PageContent] = []

        try:
            # Distribute URLs across browser contexts
            tasks = [
                self.__get_page_content(
                    url, self.browser_pool[i % len(self.browser_pool)][1], results
                )
                for i, url in enumerate(urls)
            ]
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
        finally:
            await self.cleanup()

        return dumps(
            [
                result.model_dump(mode="python")
                for result in results
                if len(result.content) > 0
            ],
            indent=4,
        )
