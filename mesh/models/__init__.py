from os import environ
from typing import Literal, Optional
from pydantic import BaseModel, Field, SecretStr
from langchain.chat_models.base import BaseChatModel
from langchain_ollama.chat_models import ChatOllama
from langchain_openai.chat_models import ChatOpenAI
from langchain_groq.chat_models import ChatGroq


class LLMConfig(BaseModel):
    provider: Literal["ollama", "openai", "groq"] = Field(
        default="ollama", description="LLM provider to use"
    )
    model: str = Field(
        default="qwen2.5-coder:7b-instruct-q8_0", description="Model name to use"
    )
    base_url: str = Field(
        default="http://localhost:11434", description="Base URL for the LLM provider"
    )
    temperature: float = Field(
        default=0.3, description="Temperature for text generation", ge=0.0, le=1.0
    )
    seed: int = Field(default=46, description="Seed for reproducible results")
    api_key: str = Field(default="dummy", description="API Key for provider")
    streaming: bool = Field(
        default=True, description="Should enable straming for model"
    )


def get_llm(
    provider: Optional[Literal["ollama", "openai", "groq"]],
    model: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
) -> BaseChatModel:
    config = LLMConfig(
        provider=provider if provider else environ.get("LLM_PROVIDR", "ollama"),
        model=(
            model
            if model
            else environ.get("LLM_MODEL_NAME", "qwen2.5-coder:7b-instruct-q8_0")
        ),
        base_url=(
            base_url
            if base_url
            else environ.get("LLM_PROVIDER_BASE_URL", "http://localhost:11434")
        ),
        api_key=api_key if api_key else environ.get("LLM_PROVIDER_API_KEY", "dummy"),
    )

    match (config.provider):
        case "ollama":
            return ChatOllama(
                model=config.model,
                temperature=config.temperature,
                seed=config.seed,
                base_url=config.base_url,
            )
        case "openai":
            return ChatOpenAI(
                model=config.model,
                temperature=config.temperature,
                seed=config.seed,
                base_url=config.base_url,
                api_key=SecretStr(config.api_key),
                streaming=config.streaming,
            )
        case "groq":
            return ChatGroq(
                model=config.model,
                temperature=config.temperature,
                base_url=config.base_url,
                api_key=SecretStr(config.api_key),
                streaming=config.streaming,
            )
