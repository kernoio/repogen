from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.data.models import ItemRecord


class ItemService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ping_database(self) -> None:
        self._session.execute(text("SELECT 1"))

    def create_item(self, *, name: str, description: str | None) -> ItemRecord:
        row = ItemRecord(name=name, description=description)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_items(self) -> list[ItemRecord]:
        result = self._session.execute(select(ItemRecord).order_by(ItemRecord.id))
        return list(result.scalars().all())

    def get_item(self, item_id: int) -> ItemRecord | None:
        return self._session.get(ItemRecord, item_id)

    def update_item(self, item_id: int, patch: dict) -> ItemRecord | None:
        row = self._session.get(ItemRecord, item_id)
        if row is None:
            return None
        if "name" in patch:
            row.name = patch["name"]
        if "description" in patch:
            row.description = patch["description"]
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete_item(self, item_id: int) -> bool:
        row = self._session.get(ItemRecord, item_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    @staticmethod
    def format_created_response(row: ItemRecord) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def format_summary(row: ItemRecord) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
        }
