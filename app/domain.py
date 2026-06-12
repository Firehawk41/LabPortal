"""Pure domain objects — no SQLAlchemy, no Flask, no database awareness."""

from dataclasses import dataclass


@dataclass
class Sample:
    sample_id: str
    chemical_matrix: str
    sample_type: str
    processing_time: str
    analyses: list[str]


@dataclass
class TestingRequest:
    user_id: str
    customer_name: str
    street_address: str
    city: str
    state: str
    country: str
    customer_contact: str
    customer_phone: str
    payment_method: str
    po_number: str
    cc_number: str
    results_list: list[str]
    results_cc_list: list[str]
    invoice_list: list[str]
    invoice_cc_list: list[str]
    samples: list[Sample]

    def is_rush(self) -> bool:
        return any(s.processing_time == "Rush" for s in self.samples)

    def sample_count(self) -> int:
        return len(self.samples)
