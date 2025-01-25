from json import JSONDecodeError, loads
from pydantic import BaseModel

from typing import Any


def convert_to_json(input: Any):
    if isinstance(input, dict):
        return [{k: convert_to_json(v)} for k, v in input.items()]
    elif isinstance(input, list):
        return [convert_to_json(itm) for itm in input]
    elif isinstance(input, BaseModel):
        return input.model_dump(mode="json")
    elif isinstance(input, str):
        try:
            return convert_to_json(loads(input))
        except JSONDecodeError:
            return input
    else:
        return input
