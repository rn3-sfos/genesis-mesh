from langchain_openai.chat_models import ChatOpenAI
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool
from langchain_community.tools.searx_search.tool import SearxSearchResults
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langfuse.callback import CallbackHandler
from typing import Type
from pydantic import BaseModel, Field
from rich.console import Console
from rich.markdown import Markdown
from os import environ

console = Console()

environ["OPENAI_API_KEY"] = "dummy"

langfuse_handler = CallbackHandler()

llm = ChatOpenAI(
    model="qwen2.5-instruct",
    base_url="http://10.0.1.1:9080/v1",
    streaming=True,
    max_tokens=4096,
    temperature=0.3,
    callbacks=[langfuse_handler]
)

searx_wrapper = SearxSearchWrapper(searx_host="http://10.0.1.1:9081")
searx_tool = SearxSearchResults(verbose=False, wrapper=searx_wrapper, num_results=6, callbacks=[langfuse_handler])

class WebScraperToolInput(BaseModel):
    url: str = Field(description="A valid url to scrape.")

class WebScraperTool(BaseTool):
    name: str = "scrape_webpage"
    description: str = "Use this to scrape the content of a webpage for detailed information."
    args_schema: Type[BaseModel] = WebScraperToolInput

    def _run(self, url: str) -> str:
        print("using browser!")
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
    WebScraperTool(callbacks=[langfuse_handler])
]


graph = create_react_agent(model=llm, tools=tools, debug=True)


def get_agent_response(user_query: str) -> str:
    response = graph.invoke(
        input={
            "messages": [
                HumanMessage(content=f"Write a brief summary on {user_query}"),
            ]
        },
        config=RunnableConfig(callbacks=[langfuse_handler])
    )
    return response["messages"][-1].content
