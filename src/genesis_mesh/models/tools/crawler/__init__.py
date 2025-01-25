from pydantic import BaseModel, Field


class WebCrawlerInputSchema(BaseModel):
    urls: list[str] = Field(description="A list of URLs to be scraped")
