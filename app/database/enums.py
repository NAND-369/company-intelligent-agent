"""Database enum types and processing state definitions."""

from enum import Enum


class CompanyStatus(str, Enum):
    """Lifecycle processing states for a target company."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ENRICHED = "ENRICHED"
    JUDGED = "JUDGED"
    SYNCED = "SYNCED"
    FAILED = "FAILED"


class SignalType(str, Enum):
    """Independent enrichment provider signal categories."""

    HTTP_WEBSITE = "HTTP_WEBSITE"
    BROWSER_CAREERS = "BROWSER_CAREERS"
    EXTERNAL_METADATA = "EXTERNAL_METADATA"


class SignalStatus(str, Enum):
    """Status outcomes for an individual signal extraction attempt."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class FitDecision(str, Enum):
    """Structured LLM evaluation categorical verdict."""

    YES = "YES"
    NO = "NO"
    UNCERTAIN = "UNCERTAIN"


class SyncDirection(str, Enum):
    """Synchronization data flow direction."""

    SHEET_TO_DB = "SHEET_TO_DB"
    DB_TO_SHEET = "DB_TO_SHEET"


class SyncStatus(str, Enum):
    """Outcome status for synchronization actions."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PipelineRunStatus(str, Enum):
    """Overall execution status of a batch pipeline run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"


class TriggerType(str, Enum):
    """Trigger origin for initiating a pipeline run."""

    SCHEDULED = "SCHEDULED"
    ON_DEMAND_API = "ON_DEMAND_API"
    GITHUB_ACTIONS = "GITHUB_ACTIONS"
