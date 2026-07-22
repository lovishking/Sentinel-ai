from fastapi import FastAPI
from app.api.routes import router as api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous AI incident resolution platform API",
    version="0.1.0"
)

app.include_router(api_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
