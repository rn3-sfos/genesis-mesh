from aiohttp import ClientSession
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from genesis_mesh.agents.blogger.prompts import (
    query_writer_instructions,
    section_writer_instructions,
)
from genesis_mesh.agents.blogger.schemas import (
    Queries,
    SectionOutputState,
    SectionState,
)
from genesis_mesh.agents.blogger.utils import UtilityFunctions
from genesis_mesh.configs.agents.blogger import BloggerConfig
from genesis_mesh.configs.llm import OpenAICompatibleAPIConfig


class SectionWriterGraphBuilder:
    def __init__(self, http_client: ClientSession):
        self.blogger_config = BloggerConfig()
        openai_compatible_provider_config = OpenAICompatibleAPIConfig()
        self.planner_llm = ChatOpenAI(
            model=self.blogger_config.planner_llm,
            temperature=self.blogger_config.planner_llm_temperature,
            api_key=openai_compatible_provider_config.api_key,
            base_url=openai_compatible_provider_config.api_base_url,
            seed=40,
            streaming=True,
            n=1,
            max_completion_tokens=self.blogger_config.planner_llm_max_tokens,
        )
        self.executor_llm = ChatOpenAI(
            model=self.blogger_config.executor_llm,
            temperature=self.blogger_config.executor_llm_temperature,
            api_key=openai_compatible_provider_config.api_key,
            base_url=openai_compatible_provider_config.api_base_url,
            seed=40,
            streaming=True,
            n=1,
            max_completion_tokens=self.blogger_config.executor_llm_max_tokens,
        )
        self.util_functions = UtilityFunctions(http_client=http_client)

    async def generate_queries(self, state: SectionState):
        """Generate search queries for a blog section"""

        # Get state
        section = state["section"]

        # Generate queries
        structured_llm = self.executor_llm.with_structured_output(Queries, method="function_calling", strict=True)

        # Format system instructions
        system_instructions = query_writer_instructions.format(
            section_topic=section.description,
            number_of_queries=self.blogger_config.number_of_queries,
        )

        # Generate queries
        queries = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_instructions),
                HumanMessage(content="Generate search queries on the provided topic."),
            ]
        )

        return {"search_queries": queries.queries}  # type: ignore

    async def search_web(self, state: SectionState):
        """Search the web for each query, then return a list of raw sources and a formatted string of sources."""

        # Get state
        search_queries = state["search_queries"]

        # Web search
        search_docs = await self.util_functions.search(search_queries)

        # Deduplicate and format sources
        source_str = self.util_functions.deduplicate_and_format_sources(
            search_docs, max_tokens_per_source=5000, include_raw_content=True
        )

        return {"source_str": source_str}

    async def write_section(self, state: SectionState):
        """Write a section of the blog"""

        # Get state
        section = state["section"]
        source_str = state["source_str"]

        # Format system instructions
        system_instructions = section_writer_instructions.format(
            section_title=section.name,
            section_topic=section.description,
            context=source_str,
        )

        # Generate section
        section_content = await self.planner_llm.ainvoke(
            [
                SystemMessage(content=system_instructions),
                HumanMessage(content="Generate a blog section based on the provided sources."),
            ]
        )

        # Write content to the section object
        section.content = section_content.content  # type: ignore

        # Write the updated section to completed sections
        return {"completed_sections": [section]}

    def build(self):
        section_builder = StateGraph(SectionState, output=SectionOutputState)
        section_builder.add_node("generate_queries", self.generate_queries)
        section_builder.add_node("search_web", self.search_web)
        section_builder.add_node("write_section", self.write_section)

        section_builder.add_edge(START, "generate_queries")
        section_builder.add_edge("generate_queries", "search_web")
        section_builder.add_edge("search_web", "write_section")
        section_builder.add_edge("write_section", END)
        return section_builder.compile()
