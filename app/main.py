import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .database import engine, SessionLocal
from .models import Base, Stage
from .routers import (
    auth_router, kpi_router, prospects_router, plans_router,
    problem_zones_router, imports_router, versions_router, results_router,
)

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Olympiad Preparation Dashboard")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

app.include_router(results_router, prefix="/api", tags=["results"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(kpi_router, prefix="/api", tags=["kpi"])
app.include_router(prospects_router, prefix="/api", tags=["prospects"])
app.include_router(plans_router, prefix="/api", tags=["plans"])
app.include_router(problem_zones_router, prefix="/api", tags=["problem-zones"])
app.include_router(imports_router, prefix="/api", tags=["imports"])

app.include_router(versions_router, prefix="/api", tags=["versions"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def seed_stages():
    db = SessionLocal()
    try:
        for code, order, name in (
            ("school", 1, "Школьный"),
            ("municipal", 2, "Муниципальный"),
            ("regional", 3, "Региональный"),
        ):
            if not db.get(Stage, code):
                db.add(Stage(code=code, order=order, name=name))
        db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))