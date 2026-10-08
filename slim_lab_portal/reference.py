"""Read-only view of SLIM reference data (customers, chemicals, elements, analyses).

The submission service depends on the `ReferenceData` protocol only. Step 4 adds the
periodically refreshed cache over the SLIM tables; until then the app starts with an empty
`StaticReferenceData`, and tests fill one in directly.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from slim_lab_portal.domain import RequestType


@dataclass(frozen=True)
class CustomerRef:
    id: int
    name: str
    street_address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""
    parent_customer_id: int | None = None
    is_group: bool = False

    @property
    def address_line_1(self) -> str:
        return self.street_address

    @property
    def address_line_2(self) -> str:
        region = " ".join(part for part in (self.state, self.postal_code) if part)
        return ", ".join(part for part in (self.city, region, self.country) if part)


@dataclass(frozen=True)
class ChemicalRef:
    id: int
    name: str


@dataclass(frozen=True)
class ElementRef:
    id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class AnalysisRef:
    id: int
    name: str
    code: str
    group: str = ""
    description: str = ""
    sort_order: int = 0
    request_types: frozenset[RequestType] = frozenset(RequestType)
    portal_selectable: bool = True


WATER_CHEMICAL_NAME = "Water"


class ReferenceData(Protocol):
    def customer(self, customer_id: int) -> CustomerRef | None: ...
    def chemical(self, chemical_id: int) -> ChemicalRef | None: ...
    def chemical_by_name(self, name: str) -> ChemicalRef | None: ...
    def element(self, element_id: int) -> ElementRef | None: ...
    def analysis(self, analysis_id: int) -> AnalysisRef | None: ...
    def locations(self, customer_id: int) -> tuple[str, ...]: ...


@dataclass
class StaticReferenceData:
    """In-memory ReferenceData. Name lookups are case-insensitive and trimmed, like slim-domain's caches."""

    customers: dict[int, CustomerRef] = field(default_factory=dict)
    chemicals: dict[int, ChemicalRef] = field(default_factory=dict)
    elements: dict[int, ElementRef] = field(default_factory=dict)
    analyses: dict[int, AnalysisRef] = field(default_factory=dict)
    customer_locations: dict[int, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        customers: Iterable[CustomerRef] = (),
        chemicals: Iterable[ChemicalRef] = (),
        elements: Iterable[ElementRef] = (),
        analyses: Iterable[AnalysisRef] = (),
        customer_locations: dict[int, tuple[str, ...]] | None = None,
    ) -> "StaticReferenceData":
        return cls(
            customers={c.id: c for c in customers},
            chemicals={c.id: c for c in chemicals},
            elements={e.id: e for e in elements},
            analyses={a.id: a for a in analyses},
            customer_locations=dict(customer_locations or {}),
        )

    def customer(self, customer_id: int) -> CustomerRef | None:
        return self.customers.get(customer_id)

    def chemical(self, chemical_id: int) -> ChemicalRef | None:
        return self.chemicals.get(chemical_id)

    def chemical_by_name(self, name: str) -> ChemicalRef | None:
        key = name.strip().lower()
        return next((c for c in self.chemicals.values() if c.name.strip().lower() == key), None)

    def element(self, element_id: int) -> ElementRef | None:
        return self.elements.get(element_id)

    def analysis(self, analysis_id: int) -> AnalysisRef | None:
        return self.analyses.get(analysis_id)

    def locations(self, customer_id: int) -> tuple[str, ...]:
        return self.customer_locations.get(customer_id, ())
