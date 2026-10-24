"""SQLite connection and schema migration support."""

from .connection import connect
from .migrations import Migration, MigrationError, apply_migrations, discover_migrations
from .repositories import (
    ApplicationRepository,
    ApplicationStatusRepository,
    CompanyRepository,
    ContactRepository,
    DocumentRepository,
    DocumentSetRepository,
    JobPostingRepository,
    TemplateRepository,
)
from .timestamps import utc_timestamp

__all__ = [
    "Migration",
    "MigrationError",
    "ApplicationRepository",
    "ApplicationStatusRepository",
    "CompanyRepository",
    "ContactRepository",
    "DocumentRepository",
    "DocumentSetRepository",
    "JobPostingRepository",
    "TemplateRepository",
    "apply_migrations",
    "connect",
    "discover_migrations",
    "utc_timestamp",
]

