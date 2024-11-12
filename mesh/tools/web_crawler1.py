import asyncio
from playwright.async_api import async_playwright


async def download_file(url, download_path):
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # Trigger the navigation and wait for the download to start
        async with page.expect_download() as download_info:
            await page.goto(url)
        download = await download_info.value

        # Save the download to the specified path
        await download.save_as(download_path)

        await browser.close()
        print(f"File downloaded successfully and saved as {download_path}")


# Example usage:
url = "https://www.tataaig.com/s3/Medicare_Plus_bc171907df.pdf"
download_path = "downloaded_file"
asyncio.run(download_file(url, download_path))
