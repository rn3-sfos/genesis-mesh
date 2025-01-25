from inspect import cleandoc

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BLOG_STRUCTURE = cleandoc(
    """The blog structure should focus on breaking-down the user-provided topic:

    1. Introduction (no research needed)
    - Brief overview of the topic area

    2. Main Body Sections:
    - Each section should focus on a sub-topic of the user-provided topic
    - Include any key concepts and definitions
    - Provide real-world examples or case studies where applicable

    3. Conclusion
    - Aim for 1 structural element (either a list of table) that distills the main body sections
    - Provide a concise summary of the blog"""
)


class BloggerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="blogger_", case_sensitive=False)
    blog_structure: str = Field(
        default=DEFAULT_BLOG_STRUCTURE, min_length=1, max_length=500
    )
    number_of_queries: int = Field(default=2, le=3, ge=1)
    planner_llm: str = Field(default="marco-o1", min_length=1, max_length=100)
    planner_llm_max_tokens: int = Field(default=8192, ge=256, le=32768)
    planner_llm_temperature: float = Field(default=0.5, ge=0, le=1)
    executor_llm: str = Field(
        default="qwen2.5-coder-7b-instruct", min_length=1, max_length=100
    )
    executor_llm_max_tokens: int = Field(default=8192, ge=256, le=32768)
    executor_llm_temperature: float = Field(default=0.3, ge=0, le=1)
