from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearxNGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="searxng_", case_sensitive=False)
    base_url: str = Field(default="http://localhost:8080", min_length=1, max_length=100)
    search_path: str = Field(default="/search", min_length=1, max_length=100)
    engines: list[str] = Field(default=["google"])
    min_score: float = Field(default=0.4, gt=0, le=1)
