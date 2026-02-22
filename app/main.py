import logging
import warnings

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.managers import router as managers_router
from app.api.processing import router as processing_router
from app.api.tickets import router as tickets_router
from app.api.upload import router as upload_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

warnings.filterwarnings(
    "ignore",
    message=r"(?s).*PydanticSerializationUnexpectedValue.*field_name='parsed'.*",
    category=UserWarning,
    module=r"pydantic(\..*)?",
)

app = FastAPI(
    title="Ticket Auto-Distribution Service",
    description="Automated ticket processing, AI enrichment, and manager assignment",
    version="1.0.0",
)

app.include_router(upload_router)
app.include_router(processing_router)
app.include_router(tickets_router)
app.include_router(managers_router)
app.include_router(dashboard_router)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
