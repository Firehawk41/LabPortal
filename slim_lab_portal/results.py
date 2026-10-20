"""The host side of slim-data, the analytical results module (slim-data D-70, M6 part 2).

slim-data is a library: it sees the outside world through two ports, and the portal (its host)
implements them over its own tables and SLIM's:

* `ReferenceLookup` -- slim-data's `SlimReferenceLookup`, fed with the analysis catalog (code ->
  SLIM analysis), SLIM's elements, the portal's TR samples (`TrSampleTables`) and SLIM's spec
  limits (`SpecReader`). Built per request, on the request's session.
* `StaffDirectory` -- active staff users, found by initials (the `analyst` column of a result file).

People reach slim-data as an `Actor`: the user's UUID (what four-eyes compares; stable if initials
change), initials for display, their lab role, AUTHENTICATED (a real login).

slim-data flushes; the portal owns the transaction and commits (slim-data D-23).

Issuing a report (D-73): until the report engine renders a file, the "file" is a canonical JSON
form of the report view; its sha256 is what slim-data records, and `report_view(as_of=...)`
rebuilds it exactly. The TR moves to partial or complete report in the same transaction (D-71).
"""

import json
from collections.abc import Mapping
from hashlib import sha256
from enum import StrEnum
from functools import cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from slim_data.adapters.slim import SlimReferenceLookup, TrSampleInfo
from slim_data.domain.actor import Actor
from slim_data.domain.enums import IdentitySource, Role
from slim_data.domain.policy import DEMO_POLICY
from slim_data.domain.results import ReportLine
from slim_data.domain.values import AnalyteRef, SampleRef
from slim_data.domain.workflow import WorkflowError
from slim_data.engine.ruleset import Ruleset
from slim_data.persistence import migrate
from slim_data.persistence.results import issues_for_tr
from slim_data.persistence.rulesets import publish_policy, publish_ruleset
from slim_data.pipeline.generic_csv import GenericCsv
from slim_data.rulesets import ruleset_text
from slim_data.service.imports import ImportReceipt, import_run
from slim_data.service import workflow as wf
from slim_data.service.views import ReportView, report_view
from slim_data.service.workflow import EvaluationReceipt, evaluate_batch

from slim_lab_portal import slim_tables as t
from slim_lab_portal.domain import TRStatus
from slim_lab_portal.models import ROLE_STAFF, TRSampleRow, TRSubmissionRow, User
from slim_lab_portal.reference import ReferenceData
from slim_lab_portal.schemas import StatusChangeIn

# A TR's samples take readings once received, until invoiced (corrections may need reruns).
STATUSES_TAKING_RESULTS = frozenset(
    {TRStatus.RECEIVED, TRStatus.IN_PROGRESS, TRStatus.PARTIAL_REPORT, TRStatus.COMPLETE_REPORT}
)

# The demo metals ruleset is bound to this catalog analysis when published (D-70): by code, never
# by ID, so it stays right whatever IDs the SLIM demo seed hands out.
DEMO_RULESET = "demo_metals"
DEMO_RULESET_ANALYSIS = "10_elements_icpms"


def actor_for(user: User) -> Actor:
    """A logged-in staff user as slim-data sees them."""
    return Actor(
        id=str(user.id),
        display=user.initials or user.email,
        roles=frozenset({Role(user.lab_role)}) if user.lab_role else frozenset(),
        identity_source=IdentitySource.AUTHENTICATED,
    )


class TrSampleTables:
    """slim-data's `TrSamples` over the portal's TR tables (until they move to slim-domain, D-45)."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._found: dict[SampleRef, TrSampleInfo | None] = {}

    def find(self, ref: SampleRef) -> TrSampleInfo | None:
        if ref not in self._found:
            row = self._session.execute(
                select(TRSampleRow, TRSubmissionRow)
                .join(TRSubmissionRow, TRSampleRow.submission_id == TRSubmissionRow.id)
                .where(TRSubmissionRow.tr_number == ref.tr_number, TRSampleRow.position == ref.position)
            ).one_or_none()
            if row is None or TRStatus(row.TRSubmissionRow.status) not in STATUSES_TAKING_RESULTS:
                self._found[ref] = None
            else:
                sample, submission = row
                self._found[ref] = TrSampleInfo(
                    customer_id=submission.customer_id,
                    chemical_id=sample.chemical_id,
                    location=submission.location,
                    analysis_ids=frozenset(a.analysis_id for a in sample.analyses),
                )
        return self._found[ref]


class SpecReader:
    """Spec limits (element -> upper limit) from SLIM's `specifications`, as slim-domain's
    `SpecificationService.get_specs` gives them: kind "specification", exact location."""

    def __init__(self, slim_engine: Engine) -> None:
        self._engine = slim_engine

    def __call__(self, customer_id: int, chemical_id: int, location: str) -> Mapping[str, float]:
        s = t.specifications
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(s.c.element_symbol, s.c.value).where(
                    s.c.kind == "specification",
                    s.c.customer_id == customer_id,
                    s.c.chemical_id == chemical_id,
                    s.c.location == (location or ""),
                )
            )
            return {r.element_symbol: r.value for r in rows}


def reference_lookup(session: Session, reference: ReferenceData, specs) -> SlimReferenceLookup:
    """slim-data's ReferenceLookup for one request (specs read at most once per customer/chemical)."""
    analyses = reference.catalog_analyses()
    return SlimReferenceLookup(
        catalog={a.code: a.name for a in analyses},
        analyses=analyses,
        elements=reference.element_choices(),
        samples=TrSampleTables(session),
        specs=cache(specs),
    )


class StaffDirectory:
    """slim-data's `StaffDirectory`: active staff by initials (case-insensitive)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, staff_id: str) -> Actor | None:
        user = self._session.scalars(
            select(User).where(
                User.role == ROLE_STAFF, User.is_active.is_(True), User.initials == staff_id.strip().upper()
            )
        ).first()
        return actor_for(user) if user else None


# ---------------------------------------------------------------- setup (seed, migrations)

SEED_ACTOR = Actor(
    id="demo-seed",
    display="Demo seed",
    roles=frozenset({Role.SUPERVISOR}),
    identity_source=IdentitySource.ASSERTED,
)


def migrate_slim_data(engine: Engine) -> None:
    """slim-data's own tables, in the shared database, with its own Alembic version table."""
    with engine.begin() as connection:
        migrate.upgrade(connection)


def publish_demo_rules(session: Session, reference: ReferenceData) -> int:
    """Publishes the demo metals ruleset, bound to DEMO_RULESET_ANALYSIS, and the demo policy;
    both are content-hashed, so publishing again changes nothing. Returns the analysis ID."""
    analysis = next((a for a in reference.catalog_analyses() if a.code == DEMO_RULESET_ANALYSIS), None)
    if analysis is None:
        raise LookupError(f"analysis {DEMO_RULESET_ANALYSIS!r} is not in the analysis catalog; "
                          "sync the catalog against SLIM first")
    body = json.loads(ruleset_text(DEMO_RULESET))
    body["analysis_id"] = analysis.id
    publish_ruleset(session, Ruleset.model_validate(body), SEED_ACTOR)
    publish_policy(session, DEMO_POLICY, SEED_ACTOR)
    return analysis.id


# ---------------------------------------------------------------- data in

def import_and_evaluate(
    session: Session, content: bytes, filename: str, actor: Actor, lookup: SlimReferenceLookup, staff
) -> tuple[ImportReceipt, dict[str, EvaluationReceipt], tuple[str, ...]]:
    """Imports a result file (all or nothing; refused with `ImportRefused`), then evaluates every
    prep batch it touches, so the batch page shows decided results straight away. A batch with no
    published ruleset raises slim-data's NotFound: the caller rolls the whole upload back.
    Also returns the TR numbers the file has readings for (the caller starts work on them, D-71)."""
    receipt = import_run(session, content, filename, actor, lookup, staff)
    rows = GenericCsv().parse(content).rows
    codes = sorted({row.prep_batch for row in rows})
    trs = tuple(sorted({row.sample.tr_number for row in rows if row.sample is not None}))
    return receipt, {code: evaluate_batch(session, code, actor, lookup) for code in codes}, trs


def start_work(service, tr_numbers, user: User) -> list[str]:
    """D-71: a received TR moves to in progress when its first readings are imported, in the
    import's transaction. Forward only: TRs already further along are left alone."""
    started = []
    for tr_number in tr_numbers:
        if service.get(tr_number, user).status is TRStatus.RECEIVED:
            service.change_status(
                tr_number, StatusChangeIn(to_status=TRStatus.IN_PROGRESS, note="first results imported"), user
            )
            started.append(tr_number)
    return started


# ---------------------------------------------------------------- people's actions on results

class ResultAction(StrEnum):
    ACCEPT = "accept"
    RERUN = "rerun"
    EXCEPTION = "exception"
    REJECT = "reject"
    CORRECT = "correct"


def act_on_result(
    session: Session, action: ResultAction, sample: SampleRef, analyte: AnalyteRef, actor: Actor,
    reason_category: str = "", note: str = "",
):
    """One person's decision on one result, under the published policy. Raises slim-data's
    WorkflowError (not allowed), NotFound, or a ValidationError (e.g. a missing reason)."""
    match action:
        case ResultAction.ACCEPT:
            return wf.accept(session, sample, analyte, actor, reason_category, note)
        case ResultAction.RERUN:
            return wf.request_rerun(session, sample, analyte, actor, note)
        case ResultAction.EXCEPTION:
            return wf.record_exception(session, sample, analyte, actor, reason_category, note)
        case ResultAction.REJECT:
            return wf.reject(session, sample, analyte, actor, note)
        case ResultAction.CORRECT:
            return wf.start_correction(session, sample, analyte, actor, note)


# ---------------------------------------------------------------- report issues (D-73)

class NothingToIssue(WorkflowError):
    """No released results, or nothing changed since the last issue."""


def report_document(view: ReportView) -> dict:
    """What the customer is shown, in a canonical form whose sha256 stands in for the report file
    until the report engine renders one (D-73). Internal facts (solo sign-off) stay out."""
    return {
        "tr_number": view.tr_number,
        "lines": [
            {
                "sample": str(line.sample), "analysis_id": line.analyte.analysis_id, "analyte": line.analyte.code,
                "version": line.version, "text": line.text,
                "unit": line.reported.unit if line.reported else None, "qualifier": line.qualifier.name,
                "uncertainty": None if line.uncertainty is None else str(line.uncertainty),
                "recovery": None if line.recovery is None else str(line.recovery),
                "notes": list(line.notes), "shown_flags": list(line.shown_flags), "amended": line.amended,
            }
            for line in view.lines
        ],
    }


def document_sha256(document: dict) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def report_complete(view: ReportView, submission) -> bool:
    """Every analysis ordered on every sample has results, all released (D-71). Analyses slim-data
    never gets readings for keep a TR partial; staff close it with the status form."""
    ordered = {(s.position, a) for s in submission.samples for a in s.analysis_ids}
    reported = {(line.sample.position, line.analyte.analysis_id) for line in view.lines}
    return not view.waiting and ordered <= reported


def issue_report(session: Session, service, tr_number: str, user: User) -> dict:
    """Records what the report shows now (every released result, latest versions) and moves the TR
    to partial or complete report (D-71, D-73). A report carrying a corrected result amends the
    latest issue. Raises NothingToIssue, or slim-data's WorkflowError."""
    submission = service.get(tr_number, user)  # 404s an unknown TR
    view = report_view(session, tr_number)
    if not view.lines:
        raise NothingToIssue(f"{tr_number} has no released results to report")
    document = report_document(view)
    digest = document_sha256(document)
    previous = issues_for_tr(session, tr_number)
    if previous and previous[-1].file_sha256 == digest:
        raise NothingToIssue(f"nothing has changed since report issue {previous[-1].id}")
    amends = previous[-1].id if previous and any(line.amended for line in view.lines) else None
    lines = tuple(ReportLine(sample=line.sample, analyte=line.analyte, version=line.version) for line in view.lines)
    issued = wf.record_issue(session, tr_number, lines, digest, actor_for(user), amends)

    target = TRStatus.COMPLETE_REPORT if report_complete(view, submission) else TRStatus.PARTIAL_REPORT
    moved = None
    if submission.status in (TRStatus.IN_PROGRESS, TRStatus.PARTIAL_REPORT):  # forward only
        note = f"report issue {issued.issue_id}" + (" (amended)" if issued.amended else "")
        service.change_status(tr_number, StatusChangeIn(to_status=target, note=note), user)
        moved = target
    return {"issue_id": issued.issue_id, "amended": issued.amended, "amends": amends, "sha256": digest,
            "lines": len(lines), "status": int(moved) if moved else None}
