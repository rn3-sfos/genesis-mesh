from argparse import ArgumentParser
from logging import getLogger
from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from uvicorn import run

from genesis_mesh.agents.blogger import Blogger
from genesis_mesh.models import BloggerRequest
from genesis_mesh.utils import build_request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8080"


def get_http_client(ws: WebSocket):
    return ws.app.state.http_client_session


logger = getLogger()


class GenesisMesh:
    def __init__(self):
        self.ws_api = APIRouter(prefix="/ws")

    def setup(self):
        @self.ws_api.websocket(path="/blogger")
        async def invoke_browser_agent(
            ws: WebSocket,
            http_client: Annotated[ClientSession, Depends(get_http_client)],
        ):
            blogger = Blogger(http_client=http_client)
            await ws.accept()
            try:
                blogger_request = await build_request(ws, BloggerRequest)
                async for state_update in blogger.invoke_agent(topic=blogger_request.topic):
                    await ws.send_json(state_update)
            except Exception as e:
                logger.exception(msg="Error getting agent response")
                await ws.send_json(data={"error": str(e)})
            finally:
                await ws.close()

    def __call__(self, host: str, port: int):
        async def app_lifespan(app: FastAPI):
            app.state.http_client_session = ClientSession(raise_for_status=True)
            yield
            await app.state.http_client_session.close()

        app = FastAPI(lifespan=app_lifespan)
        app.include_router(router=self.ws_api)
        run(app=app, host=host, port=port)


def main():
    parser = ArgumentParser(description="Genesis Mesh Agent Framework")
    parser.add_argument("--host", help="Host address to use", default=DEFAULT_HOST)
    parser.add_argument("--port", help="Port to use", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()

    mesh = GenesisMesh()
    mesh.setup()
    mesh(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
