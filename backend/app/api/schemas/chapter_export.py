"""Model data API ekspor bab."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.chapter_export.service import ExportFormat


class ChapterExportCreate(BaseModel):
    """Membuat tugas ekspor bab."""

    selected_volume_ids: list[str] = Field(default_factory=list)
    included_chapter_ids: list[str] = Field(default_factory=list)
    excluded_chapter_ids: list[str] = Field(default_factory=list)
    local_date: date
    # Klien lama tidak mengirim medan ini, jadi bawaannya wajib tetap TXT.
    format: ExportFormat = "txt"


class ChapterExportResponse(BaseModel):
    """Status tugas ekspor bab."""

    id: str
    status: str
    filename: str
    format: ExportFormat
    mode: str
    volume_count: int
    chapter_count: int
    word_count: int
    chapter_ids: list[str]
    current: int = 0
    total: int = 0
    stage: str | None = None
    chapter_title: str | None = None
    expires_at: datetime | None = None
    download_url: str | None = None
    error_message: str | None = None
