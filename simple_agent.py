from langchain_openai.chat_models import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_community.tools.searx_search.tool import SearxSearchResults
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_core.messages import SystemMessage, HumanMessage
from typing import List
from rich.console import Console
from rich.markdown import Markdown
from os import environ

console = Console()

environ["OPENAI_API_KEY"] = "dummy"

llm = ChatOpenAI(
    model="qwen2.5-instruct",
    base_url="http://10.0.1.1:9080/v1",
    streaming=True,
    max_tokens=4096,
    temperature=0.3,
)

searx_wrapper = SearxSearchWrapper(searx_host="http://10.0.1.1:9081")
searx_tool = SearxSearchResults(verbose=False, wrapper=searx_wrapper, num_results=6)


@tool
def scrape_webpage(url: str) -> str:
    """Use this to scrape the provided web page for detailed information.
    Args:
        url: a valid url to scrape
    """
    try:
        loader = WebBaseLoader(f"https://r.jina.ai/{url}")
        docs = loader.load()
        return "\n\n".join(
            [
                f'<Document name="{doc.metadata.get("title", "")}" url="{doc.metadata.get("source", "")}">\n{doc.page_content}\n</Document>'
                for doc in docs
            ]
        )
    except Exception as e:
        print(f"WARN: {str(e)}")
        raise e


tools = [
    searx_tool,
    scrape_webpage
]


graph = create_react_agent(model=llm, tools=tools)


def get_agent_response(user_query: str) -> str:
    response = graph.invoke(
        input={
            "messages": [
                HumanMessage(content=user_query),
            ]
        }
    )
    return response["messages"][-1].content
