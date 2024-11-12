from mesh.tools.web_scraper import WebScraper
from uuid import uuid4
from logging import Logger
from tempfile import gettempdir
import asyncio, os

logger = Logger(__file__)

# Create scraper instance
scraper = WebScraper()

# Run the scraper with your URLs
urls_to_scrape = [
    # "https://www.axisbank.com/download-forms/accounts",
    # "https://weather.com/en-IN/weather/hourbyhour/l/1c687804fd0b8b846d064a66060d69ad2458db1680904b0e45b7a072bae32513",
    # "https://www.axisbank.com/docs/default-source/default-document-library/sb-trust-account-mid-ver-xxi.pdf",
    "https://videos.pexels.com/video-files/3209663/3209663-uhd_3840_2160_25fps.mp4"
]


# Execute the scraper
def main():
    results = asyncio.run(scraper._arun(urls_to_scrape))
    file_name = f"{str(uuid4())[:4]}.md"
    logger.warning(f"Writing {file_name}")
    with open(os.path.join(gettempdir(), file_name), "w") as f:
        f.write(results)
    print("done")


if __name__ == "__main__":
    main()
