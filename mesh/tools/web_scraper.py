from mesh.utils.unstructured_parser import UnstructuredParser
from langchain.tools import BaseTool
from langchain.schema import Document
from langchain_community.document_transformers import MarkdownifyTransformer
from playwright.async_api import async_playwright, BrowserContext, Download, Page
from pydantic import BaseModel, Field
from typing import Type, List, Union, TypedDict
from inspect import cleandoc
import asyncio
from tempfile import gettempdir
from logging import Logger
from json import dumps
import re

logger = Logger(name=__file__)


class PageState(TypedDict):
    url: str
    page_reference: Union[Page, Download, None]
    is_loading: bool
    extracted_content: Union[str, None]
    error: Union[str, None]


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

    def __fill_state_and_handle(
        self, partial_state: PageState, event: Union[Download, Page]
    ):
        partial_state["page_reference"] = event
        if isinstance(event, Page):
            return self.__handle_navigation(partial_state)
        else:
            return self.__handle_download(partial_state)

    def __handle_navigation(self, state: PageState):
        async def run():
            try:
                if not isinstance(state["page_reference"], Page):
                    state["error"] = "Invalid state for handler"
                    return
                state["is_loading"] = True
                raw_page_content = await state["page_reference"].content()
                state["is_loading"] = False
                markdown_content = self.md_transformer.transform_documents(
                    [Document(page_content=raw_page_content)]
                )
                state["extracted_content"] = "\n".join(
                    [doc.page_content for doc in markdown_content if doc.page_content]
                )
            except Exception as e:
                state["error"] = str(e)
                logger.error(msg="Failed to parse", exc_info=True)

        return run()

    def __handle_download(self, state: PageState):
        async def run():
            try:
                if not isinstance(state["page_reference"], Download):
                    state["error"] = "Invalid state for handler"
                    return
                state["is_loading"] = True
                path = await state["page_reference"].path()
                state["is_loading"] = False
                state["extracted_content"] = self.unstructured_parser.parse_document(
                    path
                )
            except Exception as e:
                state["error"] = str(e)
                logger.error(msg="Failed to download", exc_info=True)

        return run()

    async def __extract_content(
        self, partial_state: PageState, context: BrowserContext
    ):
        logger.warning(f"Scraping {partial_state["url"]}")
        async with self.semaphore:
            page = await context.new_page()
            page.set_default_timeout(0)

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
                "download",
                lambda download: self.__fill_state_and_handle(partial_state, download),
            )
            page.on(
                "domcontentloaded",
                lambda page: self.__fill_state_and_handle(partial_state, page),
            )
            try:
                await page.goto(partial_state["url"])
            except Exception as e:
                logger.warning(msg=str(e))
                pass
            finally:
                # Wait till download completes
                while partial_state["is_loading"]:
                    await asyncio.sleep(1)
                await page.close()

        logger.warning(f"Done {partial_state['url']}")

    def _run(self, urls: List[str]) -> str:
        # Synchronous version of the scraper, if needed
        return asyncio.run(self._arun(urls))

    async def _arun(self, urls: List[str]) -> str:
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        async with async_playwright() as playwright:
            browser_contexts: List[BrowserContext] = []
            page_states: List[PageState] = [
                {
                    "url": url,
                    "error": None,
                    "extracted_content": None,
                    "is_loading": False,
                    "page_reference": None,
                }
                for url in urls
            ]

            try:
                browsers = await asyncio.gather(
                    *(
                        playwright.firefox.launch(headless=True, timeout=0)
                        for _ in range(min(self.max_concurrent, len(urls)))
                    )
                )
                browser_contexts = await asyncio.gather(
                    *(
                        browser.new_context(
                            viewport={"height": 1080, "width": 1920},
                            ignore_https_errors=True,
                            java_script_enabled=True,
                            accept_downloads=True,
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.80",
                            extra_http_headers={
                                "Sec-CH-UA": r'"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"'
                            },
                            color_scheme="dark",
                        )
                        for browser in browsers
                    )
                )

                # Distribute URLs across browser contexts
                tasks = [
                    self.__extract_content(partial_state, context)
                    for partial_state, context in zip(
                        page_states,
                        browser_contexts * (len(urls) // len(browser_contexts) + 1),
                    )
                ]
                await asyncio.gather(*tasks)
            except Exception as e:
                logger.warning(msg=f"Failed to get content, {str(e)}", exc_info=True)

            finally:
                for context in browser_contexts:
                    await context.close()
                    (await context.browser.close()) if context.browser else None

            return dumps(
                [
                    {"url": state["url"], "content": state["extracted_content"]}
                    for state in page_states
                    if (state["extracted_content"] and not state["error"])
                ],
                indent=4,
            )
