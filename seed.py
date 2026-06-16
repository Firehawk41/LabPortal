"""Seed the database with demo data: an admin, customer accounts, and sample submissions."""

import json
import os
import random
from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import bcrypt, db
from app.models import Sample, Submission, User

ANALYSES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "data", "analyses.json")

CHEMICAL_MATRICES = ["IPA", "DI Water", "Silicon Wafer", "HCl", "NaOH"]

CUSTOMERS = [
    {
        "email": "labmanager@apexanalytics.com",
        "password": "ApexLab123!",
        "company_name": "Apex Analytics Inc.",
        "customer_name": "Apex Analytics Inc.",
        "customer_contact": "Dana Whitfield",
        "customer_phone": "555-201-3344",
        "street_address": "4500 Innovation Pkwy",
        "city": "Austin",
        "state": "TX",
        "country": "USA",
    },
    {
        "email": "procurement@silvercreekmaterials.com",
        "password": "SilverCreek2024!",
        "company_name": "Silver Creek Materials",
        "customer_name": "Silver Creek Materials",
        "customer_contact": "Marcus Yee",
        "customer_phone": "555-477-8821",
        "street_address": "120 Foundry Road",
        "city": "Pittsburgh",
        "state": "PA",
        "country": "USA",
    },
    {
        "email": "qa@northwindsemiconductor.com",
        "password": "Northwind#2024",
        "company_name": "Northwind Semiconductor",
        "customer_name": "Northwind Semiconductor",
        "customer_contact": "Priya Raman",
        "customer_phone": "555-902-1187",
        "street_address": "8800 Fab Lane",
        "city": "Chandler",
        "state": "AZ",
        "country": "USA",
    },
]


def load_analysis_ids():
    with open(ANALYSES_PATH) as f:
        groups = json.load(f)
    ids = []
    for group in groups:
        for option in group["options"]:
            ids.append(option["id"])
    return ids


def make_sample(index, analysis_ids, sample_type, processing_time):
    return Sample(
        sample_id=f"S-{index:03d}",
        chemical_matrix=random.choice(CHEMICAL_MATRICES),
        sample_type=sample_type,
        processing_time=processing_time,
        analyses=random.sample(analysis_ids, k=min(3, len(analysis_ids))),
    )


def _seed_data():
    """Run seeding logic inside an existing app context."""
    db.create_all()

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        print("WARNING: ADMIN_EMAIL/ADMIN_PASSWORD not set in environment; using defaults.")
        admin_email = admin_email or "admin@example.com"
        admin_password = admin_password or "changeme"

    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            email=admin_email,
            password_hash=bcrypt.generate_password_hash(admin_password).decode("utf-8"),
            role="admin",
            company_name="YourLab",
        )
        db.session.add(admin)
        print(f"Created admin user: {admin_email}")
    else:
        print(f"Admin user already exists: {admin_email}")

    customer_users = []
    for customer in CUSTOMERS:
        existing = User.query.filter_by(email=customer["email"]).first()
        if existing:
            customer_users.append(existing)
            continue
        user = User(
            email=customer["email"],
            password_hash=bcrypt.generate_password_hash(customer["password"]).decode("utf-8"),
            role="customer",
            company_name=customer["company_name"],
        )
        db.session.add(user)
        customer_users.append(user)
        print(f"Created customer user: {customer['email']}")

    db.session.flush()

    analysis_ids = load_analysis_ids()
    statuses = ["received", "in_progress", "complete", "received", "in_progress"]
    sample_type_choices = ["chemical", "water", "wafer"]
    processing_choices = ["Standard", "Next Day", "Rush"]

    if Submission.query.count() == 0:
        for i, status in enumerate(statuses):
            customer = CUSTOMERS[i % len(CUSTOMERS)]
            user = customer_users[i % len(customer_users)]

            submission = Submission(
                user_id=user.id,
                submitted_at=datetime.now(timezone.utc) - timedelta(days=len(statuses) - i),
                status=status,
                customer_name=customer["customer_name"],
                street_address=customer["street_address"],
                city=customer["city"],
                state=customer["state"],
                country=customer["country"],
                customer_contact=customer["customer_contact"],
                customer_phone=customer["customer_phone"],
                payment_method="po" if i % 2 == 0 else "cc",
                po_number=f"PO-{1000 + i}" if i % 2 == 0 else "",
                cc_number="4111111111111111" if i % 2 == 1 else "",
                results_list=[customer["email"]],
                results_cc_list=[],
                invoice_list=["billing@" + customer["email"].split("@")[1]],
                invoice_cc_list=[],
            )

            num_samples = random.randint(1, 3)
            for s in range(num_samples):
                submission.samples.append(
                    make_sample(
                        index=i * 10 + s + 1,
                        analysis_ids=analysis_ids,
                        sample_type=random.choice(sample_type_choices),
                        processing_time=random.choice(processing_choices),
                    )
                )

            db.session.add(submission)
            print(f"Created submission for {customer['company_name']} ({status}, {num_samples} samples)")
    else:
        print("Submissions already exist; skipping submission seed data.")

    db.session.commit()
    print("Seeding complete.")


def seed_if_empty(app):
    """Auto-seed the database if no users exist. Safe to call at startup — never raises."""
    with app.app_context():
        try:
            from app.models import User as _User  # noqa: avoid circular at module level
            if _User.query.count() == 0:
                print("No users found — running auto-seed.")
                _seed_data()
        except Exception as exc:
            app.logger.warning("Auto-seed failed (non-fatal): %s", exc)


def main():
    app = create_app()

    with app.app_context():
        _seed_data()


if __name__ == "__main__":
    main()
