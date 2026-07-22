"""
Reusable column mixins for SQLAlchemy models.

These eliminate repetition across models. Every model in the system
needs an ID and timestamps, so we define them once here.

Usage:
    class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
        __tablename__ = "users"
        email = mapped_column(String, unique=True)
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """
    Adds a UUID primary key column named 'id'.
    """
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """
    Adds created_at and updated_at columns.
    
    - created_at: Set by PostgreSQL when the row is inserted (server_default)
    - updated_at: Set by PostgreSQL on every update (onupdate)
    
    Using server_default (database-side) instead of default (Python-side)
    because:
    1. The timestamp comes from the database clock, not the app server clock
    2. Multiple app servers will use the same clock source
    3. Bulk inserts via raw SQL still get timestamps
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),     # PostgreSQL's NOW() function
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),     # Set on creation
        onupdate=func.now(),           # Auto-update on every change
        nullable=False,
    )
    