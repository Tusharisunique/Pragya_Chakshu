from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import logging
import os

from backend.database.sqlite import init_database
from backend.database.neo4j_client import init_neo4j
from backend.routers import (
    cases,
    graph,
    replay,
    analytics,
    correlation,
    infrastructure,
    coordination,
    evaluation,
    export,
    notes,
)
from backend.routers import frontend_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pragya Chakshu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(replay.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(correlation.router, prefix="/api")
app.include_router(infrastructure.router, prefix="/api")
app.include_router(coordination.router, prefix="/api")
app.include_router(evaluation.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(frontend_router.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    logger.info("Initializing SQLite database...")
    init_database()
    logger.info("Initializing Neo4j...")
    init_neo4j()
    logger.info("Startup complete.")


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/guide", response_class=HTMLResponse)
def serve_user_guide():
    """Serves the beginner-friendly HTML user guide. Open in browser and Ctrl+P to save as PDF."""
    guide_path = os.path.join(os.path.dirname(__file__), "user_guide.html")
    with open(guide_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
