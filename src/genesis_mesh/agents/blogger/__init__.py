from aiohttp import ClientSession

from genesis_mesh.agents.blogger.graph.blog_builder import BloggerGraphBuilder
from genesis_mesh.utils import convert_to_json


class Blogger:
    def __init__(self, http_client: ClientSession):
        graph_builder = BloggerGraphBuilder(http_client=http_client)
        self.graph = graph_builder.build()

    async def invoke_agent(self, topic: str):
        async for update in self.graph.astream(
            input={"topic": topic}, stream_mode="updates"
        ):
            yield convert_to_json(update)
