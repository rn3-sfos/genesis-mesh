from mesh.tools.web_scraper import WebScraper
from uuid import uuid4
from logging import Logger
from tempfile import gettempdir
import asyncio, os
from json import dumps

logger = Logger(__file__)

# Create scraper instance
scraper = WebScraper()

# Run the scraper with your URLs
urls_to_scrape = [
    "https://www.axisbank.com/download-forms/accounts",
    # "https://weather.com/en-IN/weather/hourbyhour/l/1c687804fd0b8b846d064a66060d69ad2458db1680904b0e45b7a072bae32513",
    "https://www.axisbank.com/docs/default-source/default-document-library/sb-trust-account-mid-ver-xxi.pdf",
    "https://www.tataaig.com/s3/Medicare_Plus_bc171907df.pdf",
    # "https://podcasts.ceu.edu/sites/podcasts.ceu.edu/files/sample.doc",
]


# Execute the scraper
def main():
    results = asyncio.run(scraper.ainvoke(input={"urls": urls_to_scrape}))  # type: ignore
    file_name = f"{str(uuid4())[:4]}.json"
    logger.warning(f"Writing {file_name}")
    with open(os.path.join(gettempdir(), file_name), "w") as f:
        f.write(dumps(results))
    print("done")


if __name__ == "__main__":
    main()
