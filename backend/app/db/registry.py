"""Import every ORM model module so the metadata is complete in any process.

SQLAlchemy resolves foreign keys (e.g. `documents.uploaded_by -> users.id`) across the whole
metadata. A process that imports only some model modules (the Celery worker imports processing and
documents, never identity) fails at the first flush with `NoReferencedTableError`. Entry points that
are not the web app import this module once.
"""

from app.modules.chat import models as chat_models
from app.modules.documents import models as documents_models
from app.modules.identity import models as identity_models
from app.modules.processing import models as processing_models
from app.modules.tenancy import models as tenancy_models

__all__ = [
    "chat_models",
    "documents_models",
    "identity_models",
    "processing_models",
    "tenancy_models",
]
