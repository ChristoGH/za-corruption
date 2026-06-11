from commission_ingestion.discovery.zondo_bootstrap import (
    ZondoBootstrapDiscoveryAdapter,
    _parse_day_and_date,
)


def test_parse_day_and_date_patterns():
    assert _parse_day_and_date("DAY 322 TRANSCRIPT DD 2020-12-10.txt") == (
        322,
        "2020-12-10",
    )
    assert _parse_day_and_date("Day 197 - 2019-12-06.txt") == (197, "2019-12-06")
    assert _parse_day_and_date("01 April 2019 Sessions.txt") == (None, None)


def test_bootstrap_discovery_from_mocked_tree(monkeypatch):
    tree_response = {
        "tree": [
            {"path": "data/interim/DAY 322 TRANSCRIPT DD 2020-12-10.txt"},
            {"path": "data/interim/Day 197 - 2019-12-06.txt"},
            {"path": "data/interim/01 April 2019 Sessions.txt"},
        ]
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return tree_response

    monkeypatch.setattr(
        "commission_ingestion.discovery.zondo_bootstrap.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )

    records = ZondoBootstrapDiscoveryAdapter().discover_sources()
    assert len(records) == 2
    assert all(not r.authoritative for r in records)
    assert all(r.source_type == "transcript" for r in records)
    days = {r.day_no for r in records}
    assert days == {322, 197}
