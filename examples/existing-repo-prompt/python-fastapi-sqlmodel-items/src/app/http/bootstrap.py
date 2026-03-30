from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.http.errors import register_exception_handlers
from app.http.routers import health, items

app = FastAPI(title="Items benchmark API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(items.router, prefix="/items")
