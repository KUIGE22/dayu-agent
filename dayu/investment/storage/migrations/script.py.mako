"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """${upgrade if upgrade else "升级数据库结构。"}

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """${downgrade if downgrade else "回滚数据库结构。"}

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """
    ${downgrades if downgrades else "pass"}
