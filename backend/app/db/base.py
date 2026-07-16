"""
app/db/base.py
--------------
SQLAlchemy declarative base used by all ORM models.

Import all models here so that Alembic's autogenerate can discover them.
Add each new model import below under "Model imports".
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this class."""
    pass



