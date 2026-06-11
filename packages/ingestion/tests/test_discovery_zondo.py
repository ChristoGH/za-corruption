from pathlib import Path

from commission_ingestion.discovery.zondo import ZondoDiscoveryAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "zondo_transcripts.html"


def test_zondo_discovery_from_fixture(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    monkeypatch.setattr(
        "commission_ingestion.discovery.zondo.fetch_html_resilient",
        fake_fetch,
    )
    monkeypatch.setattr(
        "commission_ingestion.discovery.zondo.zondo_session_cookies",
        lambda: {"cf_clearance": "test"},
    )
    monkeypatch.setattr(
        "commission_ingestion.discovery.zondo.ZondoDiscoveryAdapter._discover_supporting_documents",
        lambda self: [],
    )

    records = ZondoDiscoveryAdapter().discover_sources()
    assert len(records) == 2
    assert all(r.commission_slug == "zondo" for r in records)
    assert all(r.source_type == "transcript" for r in records)
    assert all(r.document_type == "Transcript" for r in records)

    by_day = {r.day_no: r for r in records}
    assert by_day[327].date == "2021-01-13"
    assert by_day[328].date == "2021-01-14"
    assert by_day[327].url.endswith("transcript_day_327.pdf")
