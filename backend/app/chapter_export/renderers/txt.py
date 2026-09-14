"""Penulis berkas TXT ekspor bab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiofiles

from app.chapter_export.renderers.base import iter_export_chapters


async def render_txt(context, payload: dict[str, Any], part_path: Path) -> None:
    """Menulis bab secara mengalir ke berkas TXT tanpa menahan dokumen di memori.

    Penyandian utf-8-sig dipertahankan karena tanda urutan bita membuat pembaca teks bawaan
    Windows tidak salah menebak penyandian pada berkas berbahasa Indonesia.
    """
    async with aiofiles.open(part_path, "w", encoding="utf-8-sig", newline="\n") as output:
        async for chapter in iter_export_chapters(context, payload):
            if not chapter.is_first:
                await output.write("\n\n")
            if chapter.volume_heading is not None:
                await output.write(f"{chapter.volume_heading}\n")
            await output.write(f"{chapter.title}\n{chapter.content}")
