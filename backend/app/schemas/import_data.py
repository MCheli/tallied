from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportPayload(BaseModel):
    source: str
    capture_mode: str
    captured_at: datetime | None = None
    raw_data: dict | list | str


class ImportResponse(BaseModel):
    import_id: int
    status: str
    records_created: int
    parsed_summary: dict | None = None


class ImportLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    capture_mode: str
    status: str
    records_created: int
    error_message: str | None = None
    created_at: datetime
