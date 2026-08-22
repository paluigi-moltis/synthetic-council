"""MPD item catalogue tests."""

from __future__ import annotations

from synthetic_council.collectors import mpd_items


def test_catalogue_covers_all_data_items():
    """Every item with EA annual data must be in the catalogue (regression for
    the PYR/SAX/UTAX gap found on 2026-08-22)."""
    import polars as pl

    df = pl.read_parquet("data/raw/mpd_projections.parquet")
    ea = df.filter(
        (pl.col("REF_AREA") == "U2")
        & (pl.col("FREQ") == "A")
        & pl.col("TIME_PERIOD").str.contains(r"^\d{4}$")
    )
    avail = set(ea["PD_ITEM"].unique().to_list())
    missing = avail - set(mpd_items.ITEMS)
    assert not missing, f"items in data but not catalogued: {missing}"


def test_category_order_covers_catalogue():
    order = mpd_items.category_order()
    assert sorted(order) == sorted(mpd_items.ITEMS)
    assert order[:3] == ["HIC", "YER", "URX"]  # headline first


def test_official_meanings():
    # DDR is domestic demand, NOT unemployment (resolved doubt)
    assert "domestic demand" in mpd_items.label("DDR").lower()
    assert mpd_items.label("URX") == "Unemployment rate"
    assert mpd_items.label("YER") == "Real GDP growth"
    assert mpd_items.label("HIC") == "HICP inflation"


def test_contrib_and_level_sets():
    assert {"SCR", "NER"} == mpd_items.CONTRIB_ITEMS
    assert "LTN" in mpd_items.LEVEL_ITEMS
    assert "HIC" not in mpd_items.LEVEL_ITEMS
