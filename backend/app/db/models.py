"""
Central model import hub.

Every model in the system is imported here so that:
1. Alembic can discover all models for --autogenerate
2. SQLAlchemy relationship() back-references resolve correctly
3. You have one place to see all database tables

Add imports here as you build each module.
"""

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.documents.models import Document, DocumentChunk