from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_core.runnables.config import RunnableConfig
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langfuse.callback import CallbackHandler

from pydantic import BaseModel, Field, ValidationError
from typing import Annotated, Type
from typing_extensions import TypedDict
import datetime
from os import environ
from uuid import uuid4

from simple_agent import get_agent_response


environ["OPENAI_API_KEY"] = "dummy"

langfuse_handler = CallbackHandler()

answer_llm = ChatOpenAI(
    model="qwen2.5-instruct",
    base_url="http://10.0.1.1:9080/v1",
    streaming=True,
    max_tokens=4096,
    temperature=0.3,
    callbacks=[langfuse_handler],
)

revision_llm = ChatOpenAI(
    model="codestral-22b-v0.1",
    base_url="http://10.0.1.1:9080/v1",
    streaming=True,
    max_tokens=4096,
    temperature=0.3,
    callbacks=[langfuse_handler]
)

class AgentSearchInput(BaseModel):
    query: str = Field(description="query to look up on web")


class AgentSearchTool(BaseTool):
    name: str = "web_search_tool"
    description: str = (
        "A search engine."
        "Useful for when you need to answer questions about current events."
        "Input should be a search query."
    )
    args_schema: Type[BaseModel] = AgentSearchInput

    def _run(self, query: str) -> str:
        return get_agent_response(query)


tool = AgentSearchTool(callbacks=[langfuse_handler])


class Reflection(BaseModel):
    missing: str = Field(description="Critique of what is missing.")
    superfluous: str = Field(description="Critique of what is superfluous")


class AnswerQuestion(BaseModel):
    """Answer the question. Provide an extremely detailed answer, reflection, and then follow up with search queries to improve the answer."""

    answer: str = Field(description="Extremely detailed answer to the question.")
    reflection: Reflection = Field(description="Your reflection on the initial answer.")
    search_queries: list[str] = Field(
        description="1-3 search queries for researching improvements to address the critique of your current answer."
    )


class ResponderWithRetries:
    def __init__(self, runnable, validator):
        self.runnable = runnable
        self.validator = validator

    def respond(self, state: list):
        response = []
        for attempt in range(3):
            response = self.runnable.invoke(
                {"messages": state["messages"]}, {"tags": [f"attempt:{attempt}"]}
            )
            try:
                self.validator.invoke(response)
                return {"messages": response}
            except ValidationError as e:
                state = state + [
                    response,
                    ToolMessage(
                        content=f"{repr(e)}\n\nPay close attention to the function schema.\n\n"
                        + self.validator.schema_json()
                        + " Respond by fixing all validation errors.",
                        tool_call_id=response.tool_calls[0]["id"],
                    ),
                ]
        return {"messages": response}


actor_prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are expert researcher.
Current time: {time}

1. {first_instruction}
2. Reflect and critique your answer. Be severe to maximize improvement.
3. Recommend search queries to research information and improve your answer.""",
        ),
        MessagesPlaceholder(variable_name="messages"),
        (
            "user",
            "\n\n<system>Reflect on the user's original question and the"
            " actions taken thus far. Respond using the {function_name} function.</reminder>",
        ),
    ]
).partial(
    time=lambda: datetime.datetime.now().isoformat(),
)
initial_answer_chain = actor_prompt_template.partial(
    first_instruction="Write an extremely detailed answer.",
    function_name=AnswerQuestion.__name__,
) | answer_llm.bind_tools(tools=[AnswerQuestion])
validator = PydanticToolsParser(tools=[AnswerQuestion])

first_responder = ResponderWithRetries(
    runnable=initial_answer_chain, validator=validator
)

revise_instructions = """Revise your previous answer using the new information.
    - You should use the previous critique to add important information to your answer.
        - You MUST include numerical citations in your revised answer to ensure it can be verified.
        - Add a "References" section to the bottom of your answer in form of:
            - [1] https://example.com
            - [2] https://example.com
    - You should use the previous critique to remove superfluous information from your answer.
    - Do not miss any details.
"""


# Extend the initial answer schema to include references.
# Forcing citation in the model encourages grounded responses
class ReviseAnswer(AnswerQuestion):
    """Revise your original answer to your question. Provide an answer, reflection,
    cite your reflection with references, and finally
    add search queries to improve the blog."""

    references: list[str] = Field(
        description="Citations motivating your updated answer."
    )


revision_chain = actor_prompt_template.partial(
    first_instruction=revise_instructions,
    function_name=ReviseAnswer.__name__,
) | revision_llm.bind_tools(tools=[ReviseAnswer])
revision_validator = PydanticToolsParser(tools=[ReviseAnswer])

revisor = ResponderWithRetries(runnable=revision_chain, validator=revision_validator)


def run_queries(search_queries: list[str], **kwargs):
    """Run the generated queries."""
    return tool.batch([{"query": query} for query in search_queries])


tool_node = ToolNode(
    [
        StructuredTool.from_function(run_queries, name=AnswerQuestion.__name__),
        StructuredTool.from_function(run_queries, name=ReviseAnswer.__name__),
    ]
)


class State(TypedDict):
    messages: Annotated[list, add_messages]


MAX_ITERATIONS = 5
builder = StateGraph(State)
builder.add_node("draft", first_responder.respond)


builder.add_node("execute_tools", tool_node)
builder.add_node("revise", revisor.respond)
# draft -> execute_tools
builder.add_edge("draft", "execute_tools")
# execute_tools -> revise
builder.add_edge("execute_tools", "revise")

# Define looping logic:


def _get_num_iterations(state: list):
    i = 0
    for m in state[::-1]:
        if m.type not in {"tool", "ai"}:
            break
        i += 1
    return i


def event_loop(state: list):
    # in our case, we'll just stop after N plans
    num_iterations = _get_num_iterations(state["messages"])
    if num_iterations > MAX_ITERATIONS:
        return END
    return "execute_tools"


# revise -> execute_tools OR end
builder.add_conditional_edges("revise", event_loop, ["execute_tools", END])
builder.add_edge(START, "draft")
graph = builder.compile(debug=True)

user_input = input("User query: ")
user_context = tool.invoke(
    {"query": user_input}, RunnableConfig(callbacks=[langfuse_handler])
)

events = graph.stream(
    {
        "messages": [
            HumanMessage(content=f"Here is some context:\n{user_context}"),
            HumanMessage(content=user_input),
        ]
    },
    config=RunnableConfig(callbacks=[langfuse_handler]),
    stream_mode="values",
    debug=True
)
for i, step in enumerate(events):
    step["messages"][-1].pretty_print()
