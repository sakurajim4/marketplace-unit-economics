from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketplace_unit_economics.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ozon_fbs_tariff.json"


def test_calc_text(capsys):
    assert main(["calc", "--preset", "ozon-fbs-2026-08", "--price", "1800", "--cost", "300",
                 "--drr", "5", "--returns", "4"]) == 0
    out = capsys.readouterr().out
    assert "Комиссия 49%" in out
    assert "272.00" in out


def test_price_json(capsys):
    assert main(["price", "--preset", "ozon-fbs-2026-08", "--margin", "24", "--cost", "300",
                 "--returns", "4", "--tax", "none", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["price"] == 1654
    assert [z["start"] for z in data["dead_zones"]] == [100, 300]


def test_price_unreachable(capsys):
    assert main(["price", "--preset", "ozon-fbs-2026-08", "--margin", "70", "--cost", "10"]) == 1


def test_scan_and_tariff_file(capsys):
    assert main(["scan", "--tariff", str(EXAMPLE), "--from", "100", "--to", "400", "--by", "100",
                 "--cost", "60"]) == 0
    out = capsys.readouterr().out
    assert out.count("₽") >= 1 and "Мёртвая зона" in out


def test_wb_volume(capsys):
    assert main(["calc", "--wb", "--commission", "25", "--wb-volume", "3", "--wb-first-liter", "40",
                 "--wb-extra-liter", "10", "--wb-coef", "1.25", "--price", "1000", "--cost", "300",
                 "--tax", "none", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["logistics"] == 75
    assert data["profit"] == 1000 - 250 - 75 - 300


def test_overrides_and_errors(capsys):
    assert main(["calc", "--preset", "ozon-fbs-2026-08", "--commission", "30", "--logistics", "60",
                 "--price", "500", "--cost", "100", "--tax", "usn15", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["commission_pct"] == 30 and data["logistics"] == 60
    with pytest.raises(SystemExit):
        main(["calc", "--price", "100", "--cost", "10"])


def test_presets(capsys):
    assert main(["presets"]) == 0
    assert "ozon-fbs-2026-08" in capsys.readouterr().out
