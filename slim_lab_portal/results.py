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
"""

import json
from collections.abc import Mapping
from functools import cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from slim_data.adapters.slim import SlimReferenceLookup, TrSampleInfo
from slim_data.domain.actor import Actor
from slim_data.domain.enums import IdentitySource, Role
from slim_data.domain.policy import DEMO_POLICY
from slim_data.domain.values import SampleRef
from slim_data.engine.ruleset import Ruleset
from slim_data.persistence import migrate
from slim_data.persistence.rulesets import publish_policy, publish_ruleset
from slim_data.pipeline.generic_csv import GenericCsv
from slim_data.rulesets import ruleset_text
from slim_data.service.imports import ImportReceipt, import_run
from slim_data.service.workflow import EvaluationReceipt, evaluate_batch

from slim_lab_portal import slim_tables as t
from slim_lab_portal.domain import TRStatus
from slim_lab_portal.models import ROLE_STAFF, TRSampleRow, TRSubmissionRow, User
from slim_lab_portal.reference import ReferenceData

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
) -> tuple[ImportReceipt, dict[str, EvaluationReceipt]]:
    """Imports a result file (all or nothing; refused with `ImportRefused`), then evaluates every
    prep batch it touches, so the batch page shows decided results straight away. A batch with no
    published ruleset raises slim-data's NotFound: the caller rolls the whole upload back."""
    receipt = import_run(session, content, filename, actor, lookup, staff)
    codes = sorted({row.prep_batch for row in GenericCsv().parse(content).rows})
    return receipt, {code: evaluate_batch(session, code, actor, lookup) for code in codes}
