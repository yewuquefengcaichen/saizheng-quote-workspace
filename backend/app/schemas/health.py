from typing import Literal

from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: Literal['ok']
    service_name: str
    environment: str
    version: str
