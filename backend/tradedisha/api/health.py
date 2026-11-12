"""Health endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

from tradedisha import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    """What the health endpoint returns."""

    status: str
    app: str
    version: str
    milestone: int


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the backend is up."""
    return HealthResponse(status="ok", app="tradedisha", version=__version__, milestone=0)
