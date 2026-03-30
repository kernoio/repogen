from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ItemRecord(SQLModel, table=True):
    __tablename__ = "items"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=512)
    description: Optional[str] = Field(default=None, max_length=4096)
    created_at: datetime = Field(default_factory=_utc_now)
