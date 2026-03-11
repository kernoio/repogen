from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import os

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def item_to_dict(item: Item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/items")
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return [item_to_dict(i) for i in result.scalars().all()]


@app.post("/items", status_code=201)
async def create_item(body: dict, db: AsyncSession = Depends(get_db)):
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    item = Item(name=name, description=body.get("description"))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item_to_dict(item)


@app.get("/items/{item_id}")
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return item_to_dict(item)


@app.put("/items/{item_id}")
async def update_item(item_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    item.name = body.get("name", item.name)
    item.description = body.get("description", item.description)
    await db.commit()
    await db.refresh(item)
    return item_to_dict(item)


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(item)
    await db.commit()
