from aiohttp import ClientSession
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from genesis_mesh.agents.blogger.graph.section_builder import SectionWriterGraphBuilder
from genesis_mesh.agents.blogger.prompts import (
    blog_planner_instructions,
    blog_planner_query_writer_instructions,
    final_section_writer_instructions,
)
from genesis_mesh.agents.blogger.schemas import (
    BlogState,
    BlogStateInput,
    BlogStateOutput,
    Queries,
    Sections,
    SectionState,
)
from genesis_mesh.agents.blogger.utils import UtilityFunctions
from genesis_mesh.configs.agents.blogger import BloggerConfig
from genesis_mesh.configs.llm import OpenAICompatibleAPIConfig


class BloggerGraphBuilder:
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
        self.util_functions = UtilityFunctions(http_client=http_client)
        self.section_writer_graph_builder = SectionWriterGraphBuilder(
            http_client=http_client
        )

    async def generate_blog_plan(self, state: BlogState):
        # Inputs
        topic = state["topic"]

        # Generate search query
        structured_llm = self.planner_llm.with_structured_output(
            Queries, method="function_calling", strict=True
        )

        # Format system instructions
        system_instructions_query = blog_planner_query_writer_instructions.format(
            topic=topic,
            blog_organization=self.blogger_config.blog_structure,
            number_of_queries=self.blogger_config.number_of_queries,
        )

        # Generate queries
        results = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_instructions_query),
                HumanMessage(
                    content="Generate search queries that will help with planning the sections of the blog.",
                ),
            ]
        )

        # Search web
        search_docs = await self.util_functions.search(results.queries)  # type: ignore

        # Deduplicate and format sources
        source_str = self.util_functions.deduplicate_and_format_sources(
            search_docs, max_tokens_per_source=1000, include_raw_content=False
        )

        # Format system instructions
        system_instructions_sections = blog_planner_instructions.format(
            topic=topic,
            blog_organization=self.blogger_config.blog_structure,
            context=source_str,
        )

        # Generate sections
        structured_llm = self.planner_llm.with_structured_output(
            Sections, method="function_calling", strict=True
        )
        blog_sections = structured_llm.invoke(
            [
                SystemMessage(content=system_instructions_sections),
                HumanMessage(
                    content="Generate the sections of the blog. Your response must include a 'sections' field containing a list of sections. Each section must have: name, description, plan, research, and content fields."
                ),
            ]
        )

        return {"sections": blog_sections.sections}  # type: ignore

    def initiate_section_writing(self, state: BlogState):
        """This is the "map" step when we kick off web research for some sections of the blog"""

        # Kick off section writing in parallel via Send() API for any sections that require research
        return [
            Send("build_section_with_web_research", {"section": s})
            for s in state["sections"]
            if s.research
        ]

    async def write_final_sections(self, state: SectionState):
        """Write final sections of the blog, which do not require web search and use the completed sections as context"""

        # Get state
        section = state["section"]
        completed_blog_sections = state["blog_sections_from_research"]

        # Format system instructions
        system_instructions = final_section_writer_instructions.format(
            section_title=section.name,
            section_topic=section.description,
            context=completed_blog_sections,
        )

        # Generate section
        section_content = await self.planner_llm.ainvoke(
            [
                SystemMessage(content=system_instructions),
                HumanMessage(
                    content="Generate a blog section based on the provided sources."
                ),
            ]
        )

        # Write content to section
        section.content = section_content.content  # type: ignore

        # Write the updated section to completed sections
        return {"completed_sections": [section]}

    def gather_completed_sections(self, state: BlogState):
        """Gather completed sections from research and format them as context for writing the final sections"""

        # List of completed sections
        completed_sections = state["completed_sections"]

        # Format completed section to str to use as context for final sections
        completed_blog_sections = self.util_functions.format_sections(
            completed_sections
        )

        return {"blog_sections_from_research": completed_blog_sections}

    def initiate_final_section_writing(self, state: BlogState):
        """Write any final sections using the Send API to parallelize the process"""

        # Kick off section writing in parallel via Send() API for any sections that do not require research
        return [
            Send(
                "write_final_sections",
                {
                    "section": s,
                    "blog_sections_from_research": state["blog_sections_from_research"],
                },
            )
            for s in state["sections"]
            if not s.research
        ]

    def compile_final_blog(self, state: BlogState):
        """Compile the final blog"""

        # Get sections
        sections = state["sections"]
        completed_sections = {s.name: s.content for s in state["completed_sections"]}

        # Update sections with completed content while maintaining original order
        for section in sections:
            section.content = completed_sections[section.name]

        # Compile final blog
        all_sections = "\n\n".join([s.content for s in sections])

        return {"final_blog": all_sections}

    def build(self):
        # Add nodes and edges
        builder = StateGraph(BlogState, input=BlogStateInput, output=BlogStateOutput)
        builder.add_node("generate_blog_plan", self.generate_blog_plan)
        builder.add_node(
            "build_section_with_web_research", self.section_writer_graph_builder.build()
        )
        builder.add_node("gather_completed_sections", self.gather_completed_sections)
        builder.add_node("write_final_sections", self.write_final_sections)
        builder.add_node("compile_final_blog", self.compile_final_blog)
        builder.add_edge(START, "generate_blog_plan")
        builder.add_conditional_edges(
            "generate_blog_plan",
            self.initiate_section_writing,
            ["build_section_with_web_research"],
        )
        builder.add_edge("build_section_with_web_research", "gather_completed_sections")
        builder.add_conditional_edges(
            "gather_completed_sections",
            self.initiate_final_section_writing,
            ["write_final_sections"],
        )
        builder.add_edge("write_final_sections", "compile_final_blog")
        builder.add_edge("compile_final_blog", END)

        return builder.compile()
