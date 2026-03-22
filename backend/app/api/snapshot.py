from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.snapshot import SnapshotResponse
from app.services.snapshot_service import build_current_snapshot

router = APIRouter(prefix="/api", tags=["snapshot"])


@router.get("/snapshot", response_model=SnapshotResponse)
def get_snapshot(db: Session = Depends(get_db)):
    return build_current_snapshot(db)
