from pydantic import BaseModel, ConfigDict
from typing import Callable
class Tool(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    description: str
    parameters: dict
    func: Callable
