from fastapi import APIRouter

from app.data.deps import DbSession
from app.domain.item_service import ItemService

router = APIRouter()


@router.get("/health")
def read_health(session: DbSession) -> dict[str, str]:
    service = ItemService(session)
    service.ping_database()
    return {"status": "ok"}
