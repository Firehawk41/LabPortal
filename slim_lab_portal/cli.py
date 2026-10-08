"""Command-line admin tasks.

    python -m slim_lab_portal.cli create-staff --email lab@example.com --initials JM
    python -m slim_lab_portal.cli create-customer-user --email jane@acme.example --customer-id 3
    python -m slim_lab_portal.cli sync-analysis-catalog

The password comes from the PORTAL_PASSWORD environment variable, or an interactive prompt.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from slim_lab_portal.catalog import sync_analysis_catalog
from slim_lab_portal.config import load_settings
from slim_lab_portal.db import make_engine, make_session_factory
from slim_lab_portal.models import ROLE_CUSTOMER, ROLE_STAFF, User
from slim_lab_portal.security import hash_password


def _password() -> str:
    password = os.environ.get("PORTAL_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    return password


def _create_user(email: str, role: str, *, initials: str | None, customer_id: int | None) -> None:
    settings = load_settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    email = email.strip().lower()
    with session_factory() as db:
        if db.scalars(select(User).where(User.email == email)).first():
            raise SystemExit(f"A user with email {email} already exists.")
        db.add(User(
            email=email,
            password_hash=hash_password(_password()),
            role=role,
            initials=initials,
            customer_id=customer_id,
        ))
        db.commit()
    print(f"Created {role} user {email}.")


def _sync_catalog() -> int:
    settings = load_settings()
    portal_engine = make_engine(settings.database_url)
    slim_engine = make_engine(settings.slim_database_url) if settings.slim_database_url else portal_engine
    with make_session_factory(portal_engine)() as db:
        report = sync_analysis_catalog(slim_engine, db)
        db.commit()
    print(f"{report.matched} analyses mapped; {len(report.not_in_slim)} catalog entries not in SLIM; "
          f"{len(report.not_in_catalog)} SLIM analyses without a catalog entry.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slim_lab_portal.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    staff = sub.add_parser("create-staff", help="Create a lab staff (admin) user")
    staff.add_argument("--email", required=True)
    staff.add_argument("--initials", required=True)

    customer = sub.add_parser("create-customer-user", help="Create a user for an existing SLIM customer")
    customer.add_argument("--email", required=True)
    customer.add_argument("--customer-id", required=True, type=int)

    sub.add_parser("sync-analysis-catalog", help="Refill analysis_catalog from data/analysis_catalog.csv")

    args = parser.parse_args(argv)
    if args.command == "sync-analysis-catalog":
        return _sync_catalog()
    if args.command == "create-staff":
        _create_user(args.email, ROLE_STAFF, initials=args.initials.strip().upper(), customer_id=None)
    else:
        _create_user(args.email, ROLE_CUSTOMER, initials=None, customer_id=args.customer_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
