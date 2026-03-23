from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_tenant_db
from app.schemas.snapshot import SnapshotResponse
from app.services.snapshot_service import build_current_snapshot

router = APIRouter(prefix="", tags=["snapshot"])


@router.get("/snapshot", response_model=SnapshotResponse)
def get_snapshot(db: Session = Depends(get_tenant_db)):
    return build_current_snapshot(db)
