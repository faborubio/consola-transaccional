from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    service: str


@router.get("/health", operation_id="getHealth", summary="Liveness probe")
async def get_health() -> HealthStatus:
    return HealthStatus(status="ok", service=get_settings().service_name)
