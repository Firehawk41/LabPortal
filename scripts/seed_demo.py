"""Seeds a DEMO database with the fictional SLIM reference data from the OSS repos.

    python scripts/seed_demo.py [--oss-report-engine ../slim-report-engine-oss]

What it does, in order:
  1. Runs the portal's migrations.
  2. If SLIM's reference tables are missing or empty, creates and fills them by running
     slim-report-engine-oss's own `demo/demo.py` seed() — fictional customers "A".."Z",
     "Chemical 01".."05", "Water", the periodic table and the supported analyses. If they
     already hold data they are LEFT UNTOUCHED: this script never writes into a populated
     SLIM database.
  3. Syncs the portal-owned analysis_catalog from slim_lab_portal/data/analysis_catalog.csv.

Requires slim-domain and slim-report-engine (the OSS packages) to be installed, e.g.
    pip install -e ../slim-domain-oss[postgres] -e ../slim-report-engine-oss
The target is SLIM_DATABASE_URL, else DATABASE_URL — point it at a demo database only.
"""

import argparse
import importlib.util
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url

import slim_lab_portal
from slim_lab_portal import slim_tables as t
from slim_lab_portal.catalog import sync_analysis_catalog
from slim_lab_portal.config import load_settings
from slim_lab_portal.db import make_engine, make_session_factory

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OSS_DIR = REPO_ROOT.parent / "slim-report-engine-oss"


def _load_oss_demo(oss_dir: Path):
    demo_path = oss_dir / "demo" / "demo.py"
    if not demo_path.is_file():
        raise SystemExit(f"OSS demo seed not found at {demo_path}; pass --oss-report-engine")
    spec = importlib.util.spec_from_file_location("slim_oss_demo", demo_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses in demo.py look their module up here
    try:
        spec.loader.exec_module(module)
    except ImportError as e:
        raise SystemExit(f"{e}\nInstall the OSS packages first: pip install -e ../slim-domain-oss[postgres] "
                         "-e ../slim-report-engine-oss") from e
    return module


def _slim_tables_have_data(engine) -> bool:
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        for table in (t.customers, t.chemicals, t.elements, t.analyses):
            if table.name in existing and conn.scalar(select(func.count()).select_from(table)):
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--oss-report-engine", type=Path,
                        default=Path(os.environ.get("SLIM_REPORT_ENGINE_OSS_DIR", DEFAULT_OSS_DIR)),
                        help="checkout of slim-report-engine-oss (default: %(default)s)")
    args = parser.parse_args(argv)

    settings = load_settings()
    slim_url = settings.slim_database_url or settings.database_url
    print(f"Portal database: {make_url(settings.database_url).render_as_string(hide_password=True)}")
    print(f"SLIM database:   {make_url(slim_url).render_as_string(hide_password=True)}")

    config = Config(str(Path(slim_lab_portal.__file__).parent / "alembic.ini"))
    config.attributes["database_url"] = settings.database_url
    command.upgrade(config, "head")

    portal_engine = make_engine(settings.database_url)
    slim_engine = make_engine(slim_url) if slim_url != settings.database_url else portal_engine

    if _slim_tables_have_data(slim_engine):
        print("SLIM reference tables already hold data -- left untouched.")
    else:
        demo = _load_oss_demo(args.oss_report_engine.resolve())
        if slim_engine.dialect.name == "postgresql":
            with slim_engine.begin() as conn:  # slim-domain's unique names are CITEXT on Postgres
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        demo.seed(slim_url)
        print(f"Seeded SLIM demo reference data from {args.oss_report_engine}.")

    with make_session_factory(portal_engine)() as session:
        report = sync_analysis_catalog(slim_engine, session)
        session.commit()
    print(f"analysis_catalog: {report.matched} analyses offered or mapped.")
    if report.not_in_slim:
        print(f"  {len(report.not_in_slim)} catalog entries not in this SLIM database (skipped): "
              + ", ".join(report.not_in_slim))
    if report.not_in_catalog:
        print(f"  {len(report.not_in_catalog)} SLIM analyses with no catalog entry (not offered): "
              + ", ".join(report.not_in_catalog))
    return 0


if __name__ == "__main__":
    sys.exit(main())
