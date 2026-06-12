"""Marshmallow schemas — validate incoming JSON and produce domain objects."""

import json
import re

from marshmallow import Schema, ValidationError, fields, post_load, validates_schema
from marshmallow.validate import Length, OneOf

from app.domain import Sample, TestingRequest

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

VALID_SAMPLE_TYPES = ("chemical", "water", "wafer")
VALID_PROCESSING_TIMES = ("Standard", "Next Day", "Rush")
VALID_PAYMENT_METHODS = ("po", "cc")


def parse_tagify(raw):
    """
    Tagify serializes tags as '[{"value":"a@b.com"},...]'.
    An empty input arrives as empty string "". Returns a list of email strings.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [t["value"] for t in raw if isinstance(t, dict) and "value" in t]
    try:
        tags = json.loads(raw)
        if isinstance(tags, list):
            return [t["value"] for t in tags if isinstance(t, dict) and "value" in t]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return []


class TagifyEmailList(fields.Field):
    """Deserialises a Tagify JSON string (or list) into a list of validated email strings."""

    def __init__(self, *, required_non_empty=False, **kwargs):
        self.required_non_empty = required_non_empty
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        emails = parse_tagify(value)

        if self.required_non_empty and not emails:
            raise ValidationError("At least one email address is required.")

        bad = [e for e in emails if not EMAIL_RE.match(e)]
        if bad:
            raise ValidationError(f"Invalid email address(es): {', '.join(bad)}")

        return emails

    def _serialize(self, value, attr, obj, **kwargs):
        return value or []


def _non_blank(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Field may not be blank.")
    return value.strip()


class SampleSchema(Schema):
    sample_id = fields.String(required=True, validate=[Length(max=100), _non_blank])
    chemical_matrix = fields.String(required=True, validate=[Length(max=200), _non_blank])
    sample_type = fields.String(required=True, validate=OneOf(VALID_SAMPLE_TYPES))
    processing_time = fields.String(required=True, validate=OneOf(VALID_PROCESSING_TIMES))
    analyses = fields.List(fields.String(), required=True, validate=Length(min=1))

    @post_load
    def make_sample(self, data, **kwargs):
        return Sample(
            sample_id=data["sample_id"],
            chemical_matrix=data["chemical_matrix"],
            sample_type=data["sample_type"],
            processing_time=data["processing_time"],
            analyses=data["analyses"],
        )


class SubmissionSchema(Schema):
    customer_name = fields.String(required=True, validate=[Length(max=200), _non_blank])
    street_address = fields.String(required=True, validate=[Length(max=200), _non_blank])
    city = fields.String(required=True, validate=[Length(max=200), _non_blank])
    state = fields.String(required=True, validate=[Length(max=200), _non_blank])
    country = fields.String(required=True, validate=[Length(max=200), _non_blank])
    customer_contact = fields.String(required=True, validate=[Length(max=200), _non_blank])
    customer_phone = fields.String(required=True, validate=[Length(max=200), _non_blank])

    results_list = TagifyEmailList(required=True, required_non_empty=True)
    results_cc_list = TagifyEmailList(load_default=list)
    invoice_list = TagifyEmailList(required=True, required_non_empty=True)
    invoice_cc_list = TagifyEmailList(load_default=list)

    payment_method = fields.String(required=True, validate=OneOf(VALID_PAYMENT_METHODS))
    po_number = fields.String(load_default="", validate=Length(max=100))
    cc_number = fields.String(load_default="", validate=Length(max=100))

    samples = fields.List(fields.Nested(SampleSchema), required=True, validate=Length(min=1))

    @validates_schema
    def validate_payment_fields(self, data, **kwargs):
        if data.get("payment_method") == "po" and not str(data.get("po_number", "")).strip():
            raise ValidationError({"po_number": ["PO number is required for Purchase Order payments."]})
        if data.get("payment_method") == "cc" and not str(data.get("cc_number", "")).strip():
            raise ValidationError({"cc_number": ["Credit card info is required for Credit Card payments."]})

    @post_load
    def make_testing_request(self, data, **kwargs):
        return TestingRequest(
            user_id="",
            customer_name=data["customer_name"].strip(),
            street_address=data["street_address"].strip(),
            city=data["city"].strip(),
            state=data["state"].strip(),
            country=data["country"].strip(),
            customer_contact=data["customer_contact"].strip(),
            customer_phone=data["customer_phone"].strip(),
            payment_method=data["payment_method"],
            po_number=str(data.get("po_number", "")).strip(),
            cc_number=str(data.get("cc_number", "")).strip(),
            results_list=data["results_list"],
            results_cc_list=data["results_cc_list"],
            invoice_list=data["invoice_list"],
            invoice_cc_list=data["invoice_cc_list"],
            samples=data["samples"],
        )
