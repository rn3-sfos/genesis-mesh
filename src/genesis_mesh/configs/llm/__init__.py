from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAICompatibleAPIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENAI_", case_sensitive=False)
    llm_name: str = Field(default="marco-o1", min_length=1, max_length=100)
    api_base_url: str = Field(default="http://localhost:8080", min_length=1, max_length=100)
    api_key: SecretStr = Field(default=SecretStr("dummy"))
