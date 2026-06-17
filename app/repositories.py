"""Repository layer — translates between domain objects and SQLAlchemy models.

Route handlers and business logic never touch the ORM directly; they go
through SubmissionRepository.
"""

import uuid
from datetime import date, timedelta

from app.domain import TestingRequest
from app.extensions import db
from app.models import Sample as SampleModel
from app.models import Submission as SubmissionModel
from app.models import VALID_STATUSES


class SubmissionRepository:
    def save(self, request: TestingRequest) -> str:
        submission = SubmissionModel(
            user_id=uuid.UUID(str(request.user_id)),
            customer_name=request.customer_name,
            street_address=request.street_address,
            city=request.city,
            state=request.state,
            country=request.country,
            customer_contact=request.customer_contact,
            customer_phone=request.customer_phone,
            payment_method=request.payment_method,
            po_number=request.po_number,
            cc_number=request.cc_number,
            results_list=request.results_list,
            results_cc_list=request.results_cc_list,
            invoice_list=request.invoice_list,
            invoice_cc_list=request.invoice_cc_list,
        )

        for sample in request.samples:
            submission.samples.append(
                SampleModel(
                    sample_id=sample.sample_id,
                    chemical_matrix=sample.chemical_matrix,
                    sample_type=sample.sample_type,
                    processing_time=sample.processing_time,
                    analyses=sample.analyses,
                )
            )

        db.session.add(submission)
        db.session.commit()

        # TODO: write an audit_log entry here once submission editing is supported

        return str(submission.id)

    def get_all(self) -> list[SubmissionModel]:
        return SubmissionModel.query.order_by(SubmissionModel.submitted_at.desc()).all()

    def get_filtered(
        self,
        status: str | None = None,
        customer: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[SubmissionModel]:
        q = SubmissionModel.query.order_by(SubmissionModel.submitted_at.desc())
        if status:
            q = q.filter(SubmissionModel.status == status)
        if customer:
            q = q.filter(SubmissionModel.customer_name.ilike(f"%{customer}%"))
        if date_from:
            q = q.filter(SubmissionModel.submitted_at >= date_from)
        if date_to:
            q = q.filter(SubmissionModel.submitted_at < date_to + timedelta(days=1))
        return q.all()

    def get_by_id(self, submission_id: str) -> SubmissionModel | None:
        try:
            sid = uuid.UUID(str(submission_id))
        except ValueError:
            return None
        return SubmissionModel.query.get(sid)

    def get_by_user(self, user_id: str) -> list[SubmissionModel]:
        try:
            uid = uuid.UUID(str(user_id))
        except ValueError:
            return []
        return (
            SubmissionModel.query.filter_by(user_id=uid)
            .order_by(SubmissionModel.submitted_at.desc())
            .all()
        )

    def update_status(self, submission_id: str, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        submission = self.get_by_id(submission_id)
        if submission is None:
            raise ValueError(f"Submission not found: {submission_id}")

        # TODO: write an audit_log entry here recording the status change

        submission.status = status
        db.session.commit()
