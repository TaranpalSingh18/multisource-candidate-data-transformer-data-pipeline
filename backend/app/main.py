from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .api.candidates import router as candidates_router
from .api.configs import router as configs_router
from .api.uploads import router as uploads_router


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates_router)
app.include_router(configs_router)
app.include_router(uploads_router)


@app.get("/health", tags=["internal"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.environment}


@app.get("/")
def root() -> dict:
    return {"message": "Candidate data pipeline backend", "version": "0.1.0"}

