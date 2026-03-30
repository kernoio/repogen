from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data.deps import DbSession
from app.domain.item_service import ItemService

router = APIRouter()


class ItemCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4096)


class ItemUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4096)


@router.get("")
def list_items(session: DbSession) -> list[dict]:
    service = ItemService(session)
    rows = service.list_items()
    return [service.format_summary(r) for r in rows]


@router.post("", status_code=201)
def create_item(session: DbSession, body: ItemCreateBody) -> dict:
    service = ItemService(session)
    row = service.create_item(name=body.name, description=body.description)
    return service.format_created_response(row)


@router.get("/{item_id}")
def get_item(item_id: int, session: DbSession) -> dict:
    service = ItemService(session)
    row = service.get_item(item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return service.format_summary(row)


@router.put("/{item_id}")
def update_item(item_id: int, session: DbSession, body: ItemUpdateBody) -> dict:
    service = ItemService(session)
    patch = body.model_dump(exclude_unset=True)
    row = service.update_item(item_id, patch)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return service.format_summary(row)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, session: DbSession) -> None:
    service = ItemService(session)
    if not service.delete_item(item_id):
        raise HTTPException(status_code=404, detail="not found")
