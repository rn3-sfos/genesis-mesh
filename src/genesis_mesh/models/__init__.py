from pydantic import BaseModel, Field


class BloggerRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=500)
