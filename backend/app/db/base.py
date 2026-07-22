"""
SQLAlchemy declarative base with PostgreSQL naming conventions.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",       # Index
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",       # Unique constraint
    "ck": "ck_%(table_name)s_%(constraint_name)s",        # Check constraint
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # Foreign key
    "pk": "pk_%(table_name)s",                            # Primary key
}

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    """
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
