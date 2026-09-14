"""add book_type to projects

Revision ID: 1022
Revises: 1021
Create Date: 2026-09-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1022"
down_revision: Union[str, Sequence[str], None] = "1021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Proyek yang sudah ada seluruhnya berupa novel dengan isi bab prosa polos, sehingga fiksi menjadi
# nilai bagi baris lama. Nilai disalin apa adanya dari app.core.book_type agar migrasi tetap dapat
# dijalankan tanpa mengimpor kode aplikasi.
DEFAULT_BOOK_TYPE = "fiction"
BOOK_TYPE_MAX_LENGTH = 20


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "book_type",
            sa.String(length=BOOK_TYPE_MAX_LENGTH),
            nullable=False,
            server_default=DEFAULT_BOOK_TYPE,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "book_type")
