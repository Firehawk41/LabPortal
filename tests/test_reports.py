"""The real report (slim-data D-79): the demo scenarios issued through slim-report-engine's own
template on the fictional OSS demo data, results filled under Results / Recovery / MDL or QL.
Skipped without the slim-report-engine-oss checkout (its demo seed), like the bridge tests."""

import importlib.util
import sys
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip("slim_report_engine")

from slim_data.persistence import migrate  # noqa: E402
from slim_data.persistence.results import issues_for_tr  # noqa: E402

from slim_lab_portal import reports  # noqa: E402
from slim_lab_portal.catalog import sync_analysis_catalog  # noqa: E402
from slim_lab_portal.db import Base, make_engine, make_session_factory  # noqa: E402
from slim_lab_portal.demo_scenarios import seed_scenarios  # noqa: E402
from slim_lab_portal.personas import sync_personas  # noqa: E402
from slim_lab_portal.reference_cache import load_reference  # noqa: E402
from slim_lab_portal.repositories import TRSubmissionRepository  # noqa: E402
from slim_lab_portal.results import SpecReader, publish_demo_rules  # noqa: E402
from slim_data.service.views import report_view  # noqa: E402

OSS_DEMO = Path(__file__).resolve().parents[2] / "slim-report-engine-oss" / "demo" / "demo.py"


@pytest.fixture(scope="module")
def issued(tmp_path_factory):
    if not OSS_DEMO.is_file():
        pytest.skip(f"OSS demo not found at {OSS_DEMO}")
    url = f"sqlite:///{tmp_path_factory.mktemp('reports') / 'demo.db'}"
    spec = importlib.util.spec_from_file_location("slim_oss_demo_for_reports", OSS_DEMO)
    demo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = demo
    spec.loader.exec_module(demo)
    demo.seed(url)  # SLIM's fictional reference data
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        migrate.upgrade(connection)
    with make_session_factory(engine)() as session:
        sync_analysis_catalog(engine, session)
        session.commit()
        reference = load_reference(engine, engine)
        publish_demo_rules(session, reference)
        sync_personas(session)
        session.commit()
        trs = seed_scenarios(session, reference, SpecReader(engine), renderer=reports.engine_renderer)
        session.commit()
        files = {name: [reports.stored(session, i.file_sha256) for i in issues_for_tr(session, tr)]
                 for name, tr in trs.items()}
        hashes = {name: [i.file_sha256 for i in issues_for_tr(session, tr)] for name, tr in trs.items()}
        # below_mdl is released but never issued: render what its report would be
        below = TRSubmissionRepository(session).get_by_tr_number(trs["below_mdl"])
        files["below_mdl"] = [reports.engine_renderer(session, below, report_view(session, below.tr_number), reference)]
    engine.dispose()
    return files, hashes


def row(html, symbol):
    """The table row of an analyte, by its symbol cell."""
    return html.split(f'<td class="c3">{symbol}</td>')[1].split("</tr>")[0]


def test_the_lab_template_carries_the_released_results_and_mdl(issued):
    files, hashes = issued
    clean = files["clean_pass"][0]  # 36 Elements, IPA
    assert "EXAMPLE LAB" in clean and "Results report TR00001" in clean and "Analysis by ICPMS" in clean
    cu = row(clean, "Cu")
    assert '<td class="c4 value">10.100</td>' in cu and '<td class="c5 value">99%</td>' in cu
    assert '<td class="c6 value">0.050</td>' in cu  # the MDL, not ±0.100 (D-79)
    assert "value" not in row(clean, "Pb")  # not measured: blank, as on the template
    assert sha256(clean.encode()).hexdigest() == hashes["clean_pass"][0]


def test_anions_print_the_ql_and_below_mdl_in_blue(issued):
    files, _ = issued
    anions = files["below_mdl"][0]  # 5 Anions, two samples: a sheet each
    assert 'href="#sheet-2"' in anions
    f = row(anions, "F")
    assert "&lt; 0.050" in f and "below-mdl" in f and '<td class="c6 value below-mdl">0.167</td>' in f


def test_the_assay_report_and_its_amendment(issued):
    files, _ = issued
    first, amended = files["amended"]
    assert '<td class="c4 value">69.74</td>' in first and "(amended)" not in first
    assert '<td class="c4 value">69.55</td>' in amended and "Results report TR00008 (amended)" in amended
    assert "Amended: corrects a result reported before" in amended
