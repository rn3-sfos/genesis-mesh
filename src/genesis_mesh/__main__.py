from argparse import ArgumentParser
from logging import Logger

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from uvicorn import run

from genesis_mesh.agents.blogger import Blogger


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8080"


def get_http_client(ws: WebSocket):
    return ws.app.state.http_client_session


logger = Logger(name=__file__)


class GenesisMesh:
    def __init__(self):
        self.ws_api = APIRouter(prefix="/ws")

    def setup(self):
        @self.ws_api.websocket(path="/blogger")
        async def invoke_browser_agent(
            ws: WebSocket, http_client: ClientSession = Depends(get_http_client)
        ):
            blogger = Blogger(http_client=http_client)
            await ws.accept()
            try:
                topic = await ws.receive_text()
                async for state_update in blogger.invoke_agent(topic=topic):
                    await ws.send_json(state_update)
            except Exception as e:
                logger.exception(msg="Error getting agent response", exc_info=True)
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
