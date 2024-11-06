from langchain_community.tools.searx_search.tool import SearxSearchResults
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_experimental.tools import PythonREPLTool
from langchain_core.tools import tool
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import create_react_agent

import functools, operator
from typing import Sequence, Literal, Annotated, List
from typing_extensions import TypedDict
from pydantic import BaseModel
from os import environ

environ["OPENAI_API_KEY"] = "dummy"

searx_wrapper = SearxSearchWrapper(searx_host="http://10.0.1.1:9081")
searx_search_tool = SearxSearchResults(
    verbose=True, wrapper=searx_wrapper, num_results=6
)

# This executes code locally, which can be unsafe
python_repl_tool = PythonREPLTool(verbose=True)


@tool
def scrape_webpage(url: str) -> str:
    """Use this to scrape the provided web page for detailed information.
    Args:
        url: a valid url to scrape
    """
    loader = WebBaseLoader(url)
    docs = loader.load()
    return "\n\n".join(
        [
            f'<Document name="{doc.metadata.get("title", "")}">\n{doc.page_content}\n</Document>'
            for doc in docs
        ]
    )


def agent_node(state, agent, name):
    result = agent.invoke(state)
    return {
        "messages": [HumanMessage(content=result["messages"][-1].content, name=name)]
    }


members = ["Researcher"]
system_prompt = (
    "You are a supervisor tasked with managing a conversation between the"
    " following workers:  {members}. Given the following user request,"
    " respond with the worker to act next. Each worker will perform a"
    " task and respond with their results and status. When finished,"
    " respond with FINISH."
)
# Our team supervisor is an LLM node. It just picks the next agent to process
# and decides when the work is completed
options = ["FINISH"] + members


class routeResponse(BaseModel):
    next: Literal[*options]


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
        (
            "system",
            "Given the conversation above, who should act next?"
            " Or should we FINISH? Select one of: {options}",
        ),
    ]
).partial(options=str(options), members=", ".join(members))


llm = ChatOpenAI(
    model="codestral-22b-v0.1",
    base_url="http://10.0.1.1:9080/v1",
    streaming=True,
    max_tokens=8192,
    verbose=True,
    temperature=0.3
)


def supervisor_agent(state):
    supervisor_chain = prompt | llm.with_structured_output(routeResponse)
    return supervisor_chain.invoke(state)


# The agent state is the input to each node in the graph
class AgentState(TypedDict):
    # The annotation tells the graph that new messages will always
    # be added to the current states
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # The 'next' field indicates where to route to next
    next: str


research_agent = create_react_agent(llm, tools=[searx_search_tool, scrape_webpage])
research_node = functools.partial(agent_node, agent=research_agent, name="Researcher")

# NOTE: THIS PERFORMS ARBITRARY CODE EXECUTION. PROCEED WITH CAUTION
# code_llm = ChatOpenAI(
#     model="codestral-22b-v0.1",
#     base_url="http://10.0.1.1:9080/v1",
#     streaming=True,
#     max_tokens=8192,
#     verbose=True,
# )
# code_agent = create_react_agent(code_llm, tools=[python_repl_tool])
# code_node = functools.partial(agent_node, agent=code_agent, name="Coder")

workflow = StateGraph(AgentState)
workflow.add_node("Researcher", research_node)
# workflow.add_node("Coder", code_node)
workflow.add_node("supervisor", supervisor_agent)

for member in members:
    # We want our workers to ALWAYS "report back" to the supervisor when done
    workflow.add_edge(member, "supervisor")
# The supervisor populates the "next" field in the graph state
# which routes to a node or finishes
conditional_map = {k: k for k in members}
conditional_map["FINISH"] = END
workflow.add_conditional_edges("supervisor", lambda x: x["next"], conditional_map)
# Finally, add entrypoint
workflow.add_edge(START, "supervisor")

graph = workflow.compile()

for s in graph.stream(
    {
        "messages": [
            HumanMessage(
                content="write a very detailed blog post on chandrayaan 3"
            )
        ]
    },
    debug=True
):
    if "__end__" not in s:
        print(s)
        print("----")
