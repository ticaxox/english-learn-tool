from pydantic import BaseModel


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str
    api_version: str = "v1"
