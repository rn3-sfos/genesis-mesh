from mesh.utils.unstructured_parser import UnstructuredParser
from langchain.tools import BaseTool
from langchain.schema import Document
from langchain_community.document_transformers import MarkdownifyTransformer
from playwright.async_api import async_playwright, BrowserContext, Download, Page
from pydantic import BaseModel, Field
from typing import Type, List
from inspect import cleandoc
import asyncio, os
from tempfile import gettempdir
from logging import Logger
from json import dumps
import re

logger = Logger(name=__file__)


class PageContent(BaseModel):
    url: str
    content: str


class WebScraperInput(BaseModel):
    urls: List[str] = Field(description="A list of URLs to scrape from the internet.")


class WebScraper(BaseTool):
    name: str = "web_scraping_tool"
    description: str = cleandoc(
        """
        The WebScraper tool to perform efficient, asynchronous web scraping.
        It extracts website content and downloads. Ideal for gathering information and files from web pages.
        """
    )
    args_schema: Type[BaseModel] = WebScraperInput
    max_concurrent: int = 2
    download_path: str = gettempdir()
    semaphore: asyncio.Semaphore = asyncio.Semaphore()
    md_transformer: MarkdownifyTransformer = MarkdownifyTransformer(
        strip=[
            "script",
        ]
    )
    unstructured_parser: UnstructuredParser = UnstructuredParser()

    def __handle_page_load(self, page: Page, url: str, content: List[PageContent]):
        async def get_and_append_content():
            try:
                page_content = await page.content()
                markdown_content = self.md_transformer.transform_documents(
                    [Document(page_content=page_content)]
                )
                page_content = "\n".join([doc.page_content for doc in markdown_content])
                if len(page_content) > 0:
                    content.append(PageContent(url=url, content=page_content))
            except Exception as e:
                logger.error(msg="Failed to parse", exc_info=True)

        return get_and_append_content()

    def __handle_download(
        self, download: Download, url: str, content: List[PageContent]
    ):
        async def download_and_append_content():
            try:
                suggested_filename = download.suggested_filename
                download_path = os.path.join(self.download_path, suggested_filename)
                await download.save_as(download_path)
                content.append(
                    PageContent(
                        url=url,
                        content=self.unstructured_parser.parse_document(download_path),
                    )
                )
            except Exception as e:
                logger.error(msg="Failed to download", exc_info=True)

        return download_and_append_content()

    # playwright._impl._errors.Error: Download.save_as: canceled
    async def __get_page_content(
        self, url: str, context: BrowserContext, content: List[PageContent]
    ) -> PageContent:
        logger.warning(f"Scraping {url}")
        async with self.semaphore:
            try:
                page = await context.new_page()
                page.set_default_timeout(0)  # 30-second timeout

                # Block unnecessary resources to speed up scraping
                await page.route(
                    "**/*.{gif,svg,css,font,woff,woff2}",
                    lambda route: route.abort(),
                )

                await page.route(
                    re.compile(
                        r"(google-analytics|googletagmanager|doubleclick|facebook|analytics)\."
                    ),
                    lambda route: route.abort(),
                )
                page.on(
                    "domcontentloaded",
                    lambda page: self.__handle_page_load(page, url, content),
                )
                page.on(
                    "download",
                    lambda download: self.__handle_download(download, url, content),
                )

                try:
                    await page.goto(url)
                except Exception as e:
                    pass

                await page.close()

            except Exception as e:
                logger.error(msg="Failed to get page content", exc_info=True)
        logger.warning(f"Done {url}")

    def _run(self, urls: List[str]) -> str:
        # Synchronous version of the scraper, if needed
        return asyncio.run(self._arun(urls))

    async def _arun(self, urls: List[str]) -> str:
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        async with async_playwright() as playwright:
            browser_contexts = []
            results: List[PageContent] = []

            try:
                # Create multiple browser contexts for parallel processing
                for _ in range(min(self.max_concurrent, len(urls))):
                    browser = await playwright.firefox.launch(headless=True, timeout=0)
                    context = await browser.new_context(
                        viewport={"height": 1080, "width": 1920},
                        ignore_https_errors=True,
                        java_script_enabled=True,
                        accept_downloads=True,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.80",
                        extra_http_headers={
                            "Sec-CH-UA": r'"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"'
                        },
                    )
                    browser_contexts.append((browser, context))

                # Distribute URLs across browser contexts
                tasks = [
                    self.__get_page_content(
                        url, browser_contexts[i % len(browser_contexts)][1], results
                    )
                    for i, url in enumerate(urls)
                ]
                await asyncio.gather(*tasks)
            except Exception as e:
                logger.warning(msg="Failed to get content", exc_info=True)

            finally:
                # Cleanup
                for browser, context in browser_contexts:
                    await context.close()
                    await browser.close()

            return dumps(
                [
                    result.model_dump(mode="python")
                    for result in results
                    if len(result.content) > 0
                ],
                indent=4,
            )
