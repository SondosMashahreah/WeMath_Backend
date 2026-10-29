from time import perf_counter

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.domain.learning import DomainError
from app.api.family import router as family_router
from app.api.learning import router as learning_router
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.platform.api import install_platform
from app.api.curriculum import router as curriculum_router
from app.api.users import router as users_router
from app.core.config import settings
from app.db.database import engine


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)


@app.middleware("http")
async def request_timing(request, call_next):
    started = perf_counter()
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth", "/api/parents")):
        elapsed_ms = (perf_counter() - started) * 1000
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


install_platform(app)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(curriculum_router)
app.include_router(family_router)
app.include_router(learning_router)


@app.exception_handler(DomainError)
async def domain_error_handler(_request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.get("/")
def root():
    return {
        "name": "WeMath API",
        "status": "running",
    }


@app.get("/api/health")
def health_check():
    return {
        "success": True,
        "message": "WeMath API is running",
    }


@app.get("/api/db-health")
def database_health_check():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database(), current_user, NOW()")
            ).fetchone()

        return {
            "success": True,
            "database": result[0],
            "user": result[1],
            "time": result[2],
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
