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
from uuid import uuid4

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
    max_concurrent: int = 5
    download_path: str = gettempdir()
    semaphore: asyncio.Semaphore = asyncio.Semaphore()
    md_transformer: MarkdownifyTransformer = MarkdownifyTransformer()
    __content: List[str] = []

    def __handle_navigation(self, page: Page):
        async def get_and_append_content():
            try:
                page_content = await page.content()
                markdown_content = self.md_transformer.transform_documents(
                    [Document(page_content=page_content)]
                )
                page_content = "\n".join([doc.page_content for doc in markdown_content])
                self.__content.append(page_content)
            except Exception as e:
                logger.error(msg="Failed to parse", exc_info=True)
                return f"Failed to parse content: {str(e)}"

        return get_and_append_content()

    def __handle_download(self, download: Download):
        async def download_and_append_content():
            try:
                suggested_filename = download.suggested_filename
                download_path = os.path.join(self.download_path, suggested_filename)
                await download.save_as(download_path)
                print("Download successful")
            except Exception as e:
                logger.error(msg="Failed to download", exc_info=True)

        return download_and_append_content()

    # playwright._impl._errors.Error: Download.save_as: canceled
    async def __get_page_content(
        self, url: str, context: BrowserContext
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
                page.on(
                    "load",
                    self.__handle_navigation,
                )

                page.on("download", self.__handle_download)

                try:
                    await page.goto(url)
                except Exception as e:
                    pass

                await page.close()

            except Exception as e:
                logger.error(msg="Failed to get page content", exc_info=True)
                return PageContent(url=url, content=f"Error: {str(e)}")
        logger.warning(f"Done {url}")

    def _run(self, urls: List[str]) -> List[PageContent]:
        # Synchronous version of the scraper, if needed
        return asyncio.run(self._arun(urls))

    async def _arun(self, urls: List[str]) -> List[PageContent]:
        self.__content = []
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        async with async_playwright() as playwright:
            browser_contexts = []
            results = []

            try:
                # Create multiple browser contexts for parallel processing
                for _ in range(min(self.max_concurrent, len(urls))):
                    browser = await playwright.firefox.launch(headless=True, timeout=0)
                    context = await browser.new_context(
                        viewport={"height": 1080, "width": 1920},
                        ignore_https_errors=True,
                        java_script_enabled=True,
                        accept_downloads=True,
                    )
                    browser_contexts.append((browser, context))

                # Distribute URLs across browser contexts
                tasks = [
                    self.__get_page_content(
                        url, browser_contexts[i % len(browser_contexts)][1]
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

            return self.__content


# Create scraper instance
scraper = WebScraper()

# Run the scraper with your URLs
urls_to_scrape = [
    # "https://python.langchain.com/docs/integrations/document_transformers/markdownify/",
    "https://videos.pexels.com/video-files/3209663/3209663-uhd_3840_2160_25fps.mp4",
    "https://github.com/microsoft/playwright-python/issues/1557",
    "https://microsoft.github.io/autogen/0.2/docs/Gallery",
    "https://huggingface.co/Qwen/Qwen2.5-72B-Instruct",
    "https://weather.com/en-IN/weather/hourbyhour/l/1c687804fd0b8b846d064a66060d69ad2458db1680904b0e45b7a072bae32513",
]

# Execute the scraper
results = asyncio.run(scraper._arun(urls_to_scrape))

# Process the results
for page_content in results:
    # print(f"URL: {page_content.url}")
    # print(f"Content: {page_content.content}")
    file_name = f"{str(uuid4())[:4]}.md"
    logger.warning(f"Writing {file_name}")
    with open(os.path.join(gettempdir(), file_name), "w") as f:
        f.write(page_content)
print("done")
