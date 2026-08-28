from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.courses.router import router as courses_router
from app.documents.router import router as documents_router
from app.graph.router import router as graph_router

app = FastAPI(title="Arc API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(courses_router)
app.include_router(documents_router)
app.include_router(graph_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
