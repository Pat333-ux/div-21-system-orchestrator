from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DirectivePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class DirectiveStatus(str, Enum):
    QUEUED = "queued"
    BLOCKED_MISSING_PREREQS = "blocked_missing_prereqs"
    AWAITING_APPROVAL = "awaiting_approval"
    DISPATCHING = "dispatching"
    RETRYABLE_FAILURE = "retryable_failure"
    COMPLETED = "completed"
    HALTED = "halted"


class DivisionHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


DIRECTIVE_ALLOWED_TRANSITIONS: dict[DirectiveStatus, set[DirectiveStatus]] = {
    DirectiveStatus.QUEUED: {
        DirectiveStatus.BLOCKED_MISSING_PREREQS,
        DirectiveStatus.AWAITING_APPROVAL,
        DirectiveStatus.DISPATCHING,
        DirectiveStatus.HALTED,
    },
    DirectiveStatus.BLOCKED_MISSING_PREREQS: {
        DirectiveStatus.QUEUED,
        DirectiveStatus.AWAITING_APPROVAL,
        DirectiveStatus.HALTED,
    },
    DirectiveStatus.AWAITING_APPROVAL: {
        DirectiveStatus.DISPATCHING,
        DirectiveStatus.QUEUED,
        DirectiveStatus.HALTED,
    },
    DirectiveStatus.DISPATCHING: {
        DirectiveStatus.COMPLETED,
        DirectiveStatus.RETRYABLE_FAILURE,
        DirectiveStatus.HALTED,
    },
    DirectiveStatus.RETRYABLE_FAILURE: {
        DirectiveStatus.DISPATCHING,
        DirectiveStatus.AWAITING_APPROVAL,
        DirectiveStatus.HALTED,
    },
    DirectiveStatus.COMPLETED: set(),
    DirectiveStatus.HALTED: {DirectiveStatus.QUEUED},
}


class InvalidDirectiveTransitionError(ValueError):
    """Raised for transitions outside the allowed state table."""


class GovernanceApprovalError(PermissionError):
    """Raised when a gated directive is dispatched without approval."""


class OrchestrationAuditEntry(BaseModel):
    directive_id: str
    from_status: str
    to_status: str
    actor: str
    reason: str
    occurred_at: datetime = Field(default_factory=utc_now)


class RetryPolicyState(BaseModel):
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    last_error: str | None = None
    last_attempted_at: datetime | None = None
    retryable: bool = True


class DivisionTarget(BaseModel):
    division_code: str = Field(..., min_length=2, max_length=64)
    endpoint_or_queue: str = Field(..., min_length=2, max_length=256)
    health_status: DivisionHealthStatus = DivisionHealthStatus.HEALTHY
    requires_human_approval: bool = False


class OrchestrationDirective(BaseModel):
    directive_id: str = Field(..., min_length=3, max_length=64)
    correlation_id: str = Field(..., min_length=3, max_length=64)
    source_module: str = Field(..., min_length=2, max_length=64)
    target: DivisionTarget
    action: str = Field(..., min_length=2, max_length=120)
    priority: DirectivePriority = DirectivePriority.NORMAL
    required_prerequisites: list[str] = Field(default_factory=list)
    satisfied_prerequisites: list[str] = Field(default_factory=list)
    human_approved: bool = False
    context_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("directive_id", "correlation_id")
    @classmethod
    def validate_non_blank_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Identifier must not be blank")
        return value.strip()

    def missing_prerequisites(self) -> list[str]:
        satisfied = {
            item.strip().lower()
            for item in self.satisfied_prerequisites
            if item.strip()
        }
        return [
            req.strip()
            for req in self.required_prerequisites
            if req.strip() and req.strip().lower() not in satisfied
        ]

    def to_safe_summary(self) -> dict[str, Any]:
        redacted_keys = {
            "applicant_name",
            "date_of_birth",
            "ssn",
            "notes",
            "secret",
            "token",
        }
        safe_meta = {
            key: ("[REDACTED]" if key.lower() in redacted_keys else value)
            for key, value in self.context_metadata.items()
        }
        return {
            "directive_id": self.directive_id,
            "correlation_id": self.correlation_id,
            "source_module": self.source_module,
            "target_division": self.target.division_code,
            "action": self.action,
            "priority": self.priority.value,
            "missing_prerequisites": self.missing_prerequisites(),
            "human_approved": self.human_approved,
            "context_metadata": safe_meta,
        }


class OrchestrationDirectiveRecord(BaseModel):
    directive: OrchestrationDirective
    status: DirectiveStatus = DirectiveStatus.QUEUED
    retry: RetryPolicyState = Field(default_factory=RetryPolicyState)
    audit_log: list[OrchestrationAuditEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)

    def transition_to(
        self,
        next_status: DirectiveStatus,
        *,
        actor: str,
        reason: str,
    ) -> OrchestrationAuditEntry | None:
        if next_status == self.status:
            return None

        if next_status == DirectiveStatus.DISPATCHING:
            missing = self.directive.missing_prerequisites()
            if missing:
                raise InvalidDirectiveTransitionError(
                    f"Cannot dispatch directive with unmet prerequisites: {', '.join(missing)}"
                )
            if (
                self.directive.target.requires_human_approval
                and not self.directive.human_approved
            ):
                raise GovernanceApprovalError(
                    f"Target division '{self.directive.target.division_code}' requires explicit human_approved=True"
                )

        if next_status not in DIRECTIVE_ALLOWED_TRANSITIONS.get(self.status, set()):
            raise InvalidDirectiveTransitionError(
                f"Invalid directive transition from '{self.status.value}' to '{next_status.value}'"
            )

        entry = OrchestrationAuditEntry(
            directive_id=self.directive.directive_id,
            from_status=self.status.value,
            to_status=next_status.value,
            actor=actor,
            reason=reason,
        )
        self.status = next_status
        self.updated_at = entry.occurred_at
        self.audit_log.append(entry)
        return entry

    def record_retryable_failure(self, *, error: str, actor: str = "div21_orchestrator") -> None:
        now = utc_now()
        self.retry.attempt_count += 1
        self.retry.last_error = error
        self.retry.last_attempted_at = now
        self.retry.retryable = self.retry.attempt_count < self.retry.max_attempts

        if self.status == DirectiveStatus.DISPATCHING:
            self.transition_to(
                DirectiveStatus.RETRYABLE_FAILURE,
                actor=actor,
                reason=f"Dispatch attempt {self.retry.attempt_count} failed",
            )
        elif self.status == DirectiveStatus.RETRYABLE_FAILURE:
            self.updated_at = now
            self.audit_log.append(
                OrchestrationAuditEntry(
                    directive_id=self.directive.directive_id,
                    from_status=DirectiveStatus.RETRYABLE_FAILURE.value,
                    to_status=DirectiveStatus.RETRYABLE_FAILURE.value,
                    actor=actor,
                    reason=f"Retry attempt {self.retry.attempt_count} failed",
                    occurred_at=now,
                )
            )
