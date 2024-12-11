from langchain.schema import Document
from langchain_community.document_transformers import MarkdownifyTransformer
from playwright.async_api import async_playwright, BrowserContext
import asyncio
from logging import Logger
import re

logger = Logger(name=__file__)


class PlaywrightScraper:
    def __init__(self, max_concurrent: int = 4) -> None:
        self.max_concurrent = max_concurrent
        self.md_transformer = MarkdownifyTransformer(
            strip=[
                "script",
            ]
        )

    async def __extract_content(self, url: str, context: BrowserContext):
        logger.warning(f"Scraping {url}")
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

        try:
            await page.goto(url, wait_until="domcontentloaded")
            html_content = await page.content()
            transfored_parts = self.md_transformer.transform_documents(
                [Document(html_content)]
            )
            return (url, "\n\n".join([part.page_content for part in transfored_parts]))
        except Exception as e:
            logger.warning(str(e))
            pass
        finally:
            await page.close()

        logger.warning(f"Done {url}")
        return url, None

    async def get_content(self, urls: list[str]):
        concurrency = min(self.max_concurrent, len(urls))
        async with async_playwright() as playwright:
            browser_contexts: list[BrowserContext] = []

            try:
                browsers = await asyncio.gather(
                    *(
                        playwright.firefox.launch(headless=True, timeout=0)
                        for _ in range(concurrency)
                    )
                )
                browser_contexts = await asyncio.gather(
                    *(
                        browser.new_context(
                            viewport={"height": 1080, "width": 1920},
                            ignore_https_errors=True,
                            java_script_enabled=True,
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
                    self.__extract_content(url, context)
                    for url, context in zip(
                        urls,
                        browser_contexts * (len(urls) // len(browser_contexts) + 1),
                    )
                ]
                results = await asyncio.gather(*tasks)
            except Exception as e:
                logger.warning(msg=f"Failed to get content, {str(e)}", exc_info=True)

            finally:
                for context in browser_contexts:
                    await context.close()
                    (await context.browser.close()) if context.browser else None

            return [
                {"url": result[0], "content": result[1]}
                for result in results
                if (result[1] != None)
            ]
