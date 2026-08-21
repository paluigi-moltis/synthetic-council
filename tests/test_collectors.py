"""Tests for collectors: parsers on fixture HTML, vintage logic, join logic."""

from __future__ import annotations

import polars as pl
import pytest

from synthetic_council.collectors.macro import _parse_vtg_tsv
from synthetic_council.collectors.members import normalise_role, parse_members_page
from synthetic_council.collectors.persons import canonicalise, person_id
from synthetic_council.collectors.speeches import parse_pipe_csv

# ---------------------------------------------------------------------------
# members page parser (three layouts)
# ---------------------------------------------------------------------------

LEGACY_HTML = """
<li><div><strong>Jean-Claude Trichet</strong> <a href="x">CV</a><br/> ECB Pres</div></li>
<li><div><strong>Axel A. Weber</strong> <a href="x">CV</a><br/> Bundesbank</div></li>
"""

IMGTITLE_HTML = """
<p class="ecb-imgTitle">Mario Draghi</p><p class="ecb-imgDesc">President of the ECB</p>
<p class="ecb-imgTitle">Jens Weidmann</p><p class="ecb-imgDesc">President, Deutsche Bundesbank</p>
"""

CARD_HTML = """
<a href="cv" class="box"><div class="header"><div class="title">Christine Lagarde</div></div>
<div class="content-box"><p>President of the ECB</p></div></a>
"""


@pytest.mark.parametrize(
    "html,names",
    [
        (LEGACY_HTML, ["Jean-Claude Trichet", "Axel A. Weber"]),
        (IMGTITLE_HTML, ["Mario Draghi", "Jens Weidmann"]),
        (CARD_HTML, ["Christine Lagarde"]),
    ],
)
def test_parse_members_layouts(html, names):
    entries = parse_members_page(html)
    assert [e[0] for e in entries] == names


def test_normalise_role():
    assert normalise_role("X", "President of the ECB") == ("ECB President", None)
    assert normalise_role("X", "Vice-President of the ECB")[0] == "ECB Vice-President"
    role, iso = normalise_role("X", "Governor, Banco de Espa&ntilde;a")
    assert iso == "ES"
    role, iso = normalise_role("X", "President, Deutsche Bundesbank")
    assert iso == "DE"


def test_canonicalise_variants():
    assert canonicalise("Vítor Manuel Ribeiro Constâncio") == "Vítor Constâncio"
    assert canonicalise("Lucas D. Papademos") == "Lucas Papademos"
    assert person_id("Vítor Constâncio") == "vitor-constancio"


# ---------------------------------------------------------------------------
# speeches CSV parser
# ---------------------------------------------------------------------------


def test_parse_pipe_csv():
    raw = (
        b"date|speakers|title|subtitle|contents\r\n"
        b"2020-01-16|Christine Lagarde|Title A|Subtitle A|First line\nsecond line\r\n"
        b"2020-01-09|Philip R. Lane|Title B|Sub B|text\r\n"
    )
    df = parse_pipe_csv(raw)
    assert df.height == 2
    assert df["speakers"].to_list() == ["Christine Lagarde", "Philip R. Lane"]
    assert "second line" in df["contents"][0]
    assert str(df["date"][0]) == "2020-01-16"


# ---------------------------------------------------------------------------
# PEEI vintage TSV parser
# ---------------------------------------------------------------------------


def test_parse_vtg_tsv():
    tsv = (
        b"freq,revdate,unit,geo\\TIME_PERIOD\t2020-Q1 \t2020-Q2 \r\n"
        b"Q,2020-04-15,CLV05_MEUR,EA\t2500.5 b \t :\r\n"
        b"Q,2020-07-15,CLV05_MEUR,EA\t2500.5 \t2510.0 p\r\n"
    )
    df = _parse_vtg_tsv(tsv)
    # ' :' flag -> missing; flags stripped from numbers
    assert df.height == 3
    q1 = df.filter(pl.col("period") == "2020-Q1")
    assert q1["value"].to_list() == [2500.5, 2500.5]
    q2 = df.filter(pl.col("period") == "2020-Q2")
    assert q2["value"].to_list() == [2510.0]
