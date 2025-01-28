from json import JSONDecodeError, loads
from logging import getLogger
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError

logger = getLogger()


def convert_to_json(obj: Any):
    if isinstance(obj, dict):
        return [{k: convert_to_json(v)} for k, v in obj.items()]
    if isinstance(obj, list):
        return [convert_to_json(itm) for itm in obj]
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, str):
        try:
            return convert_to_json(loads(obj))
        except JSONDecodeError:
            return obj
    return obj


async def build_request(ws: WebSocket, request_type: type[BaseModel]):
    try:
        json_request = await ws.receive_json()
        return request_type.model_validate(json_request)
    except (ValidationError, JSONDecodeError):
        logger.exception(msg="Failed to extract request")
        raise
