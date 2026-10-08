"""Status transitions (docs/SLIM_DOMAIN_V2.md §3, TRStatus). Pure functions over frozen objects."""

from datetime import date, datetime

from slim_lab_portal.domain.enums import ActorType, TRStatus
from slim_lab_portal.domain.tr import Actor, TRReceipt, TRStatusEvent, TRSubmission

ALLOWED_TRANSITIONS: dict[TRStatus, frozenset[TRStatus]] = {
    TRStatus.SUBMITTED: frozenset({TRStatus.RECEIVED, TRStatus.CANCELLED}),
    TRStatus.RECEIVED: frozenset({TRStatus.IN_PROGRESS, TRStatus.CANCELLED}),
    TRStatus.IN_PROGRESS: frozenset({TRStatus.PARTIAL_REPORT, TRStatus.COMPLETE_REPORT, TRStatus.CANCELLED}),
    TRStatus.PARTIAL_REPORT: frozenset({TRStatus.PARTIAL_REPORT, TRStatus.COMPLETE_REPORT}),
    TRStatus.COMPLETE_REPORT: frozenset({TRStatus.INVOICED}),
    TRStatus.INVOICED: frozenset(),
    TRStatus.CANCELLED: frozenset(),
}


class TransitionNotAllowed(ValueError):
    pass


def allowed_next_statuses(current: TRStatus, actor_type: ActorType) -> tuple[TRStatus, ...]:
    if actor_type is ActorType.CUSTOMER_USER:
        return (TRStatus.CANCELLED,) if current is TRStatus.SUBMITTED else ()
    return tuple(sorted(ALLOWED_TRANSITIONS[current]))


def transition(
    submission: TRSubmission,
    to_status: TRStatus,
    *,
    actor: Actor,
    at: datetime,
    note: str = "",
    date_received: date | None = None,
    received_by: str | None = None,
) -> TRSubmission:
    """Returns a new TRSubmission with the status changed and the event appended.

    Moving to RECEIVED records the receipt and needs `date_received` and `received_by`
    (technician initials).
    """
    current = submission.status
    if to_status not in allowed_next_statuses(current, actor.type):
        raise TransitionNotAllowed(f"cannot move {submission.tr_number or 'submission'} from "
                                   f"{current.label} to {to_status.label}")

    receipt = submission.receipt
    if to_status is TRStatus.RECEIVED:
        if date_received is None or not received_by:
            raise TransitionNotAllowed("receiving samples needs date_received and received_by")
        receipt = TRReceipt(date_received=date_received, received_by=received_by, recorded_at=at, recorded_by=actor)
    elif date_received is not None or received_by is not None:
        raise TransitionNotAllowed("date_received and received_by are only for receiving samples")

    event = TRStatusEvent(from_status=current, to_status=to_status, at=at, actor=actor, note=note)
    return replace(submission, status=to_status, receipt=receipt, status_history=(*submission.status_history, event))


def replace(model, **changes):
    """Like model_copy(update=...), but re-validates, so the invariants still hold."""
    return type(model)(**{**dict(model), **changes})
