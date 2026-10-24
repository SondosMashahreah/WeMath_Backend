from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.curriculum import router as curriculum_router
from app.api.users import router as users_router
from app.core.config import settings
from app.db.database import engine


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)


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


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(curriculum_router)


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
