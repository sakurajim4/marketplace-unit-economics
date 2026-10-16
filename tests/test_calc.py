from __future__ import annotations

import json
import random

import pytest

from marketplace_unit_economics import (
    Costs,
    Tariff,
    Tax,
    Tier,
    break_even_price,
    dead_zones,
    load_tariff,
    ozon_fbs_2026_08,
    price_for_margin,
    tiers,
    unit_economics,
    wb,
    wb_logistics,
)

OZON = ozon_fbs_2026_08()


def test_tiers_select_by_price():
    assert OZON.commission_at(100) == 17
    assert OZON.commission_at(100.01) == 23
    assert OZON.commission_at(300) == 23
    assert OZON.commission_at(301) == 49
    assert ozon_fbs_2026_08(slot_discount=False).commission_at(301) == 52
    assert OZON.logistics_at(300) == 32 and OZON.logistics_at(301) == 100


def test_last_mile_cap():
    assert OZON.last_mile_at(100) == pytest.approx(20)
    assert OZON.last_mile_at(125) == pytest.approx(25)
    assert OZON.last_mile_at(5000) == 25
    assert 125 in OZON.breakpoints()


def test_breakdown_matches_hand_formula():
    # прибыль = цена − закуп − цена×0.49 − цена×0.01 − логистика − 25 − 0.04×(логистика + 25)
    t = ozon_fbs_2026_08(logistics_high=136.5)
    b = unit_economics(1800, t, Costs(cost=300, return_rate_pct=4))
    expected = 1800 - 300 - 1800 * 0.49 - 1800 * 0.01 - 136.5 - 25 - 0.04 * (136.5 + 25)
    assert b.profit == pytest.approx(expected)
    assert b.margin_pct == pytest.approx(24.0, abs=0.01)
    assert b.payout == pytest.approx(1800 - 882 - 136.5 - 25 - 18)
    assert b.markup == 6
    assert break_even_price(t, Costs(cost=300, return_rate_pct=4)) == 936


@pytest.mark.parametrize(
    "tax, price",
    [
        (Tax.none(), 1654),   # 0.5p − 430 ≥ 0.24p
        (Tax.usn6(), 2150),   # 0.44p − 430 ≥ 0.24p
        (Tax.npd(), 1955),    # 0.46p − 430 ≥ 0.24p
        (Tax.usn15(), 1976),  # 0.85·(0.5p − 430) ≥ 0.24p
        (Tax.usn6(vat_pct=5), 2770),
    ],
)
def test_price_for_margin_taxes(tax, price):
    costs = Costs(cost=300, return_rate_pct=4)
    sol = price_for_margin(24, OZON, costs, tax)
    assert sol is not None and sol.price == price
    assert sol.breakdown.margin_pct >= 24
    assert unit_economics(price - 1, OZON, costs, tax).margin_pct < 24


def test_cheap_shelf_wins_and_jump_over_threshold():
    costs = Costs(cost=50, return_rate_pct=4)
    assert price_for_margin(20, OZON, costs).price == 196
    # 40 % на полке до 300 ₽ недостижимо — следующая подходящая цена сильно выше порога
    assert price_for_margin(40, OZON, costs).price == 1800


def test_unreachable_margin():
    assert price_for_margin(60, OZON, Costs(cost=10)) is None


def test_dead_zones():
    zones = dead_zones(OZON, Costs(cost=300, return_rate_pct=4))
    assert [(z.start, z.end) for z in zones] == [(100, 111), (300, 598)]
    z = zones[1]
    assert z.profit_at_start == pytest.approx(-131.28)
    assert z.profit_after_start == pytest.approx(-279.5)


def test_drr_and_extra_costs():
    base = unit_economics(1000, OZON, Costs(cost=200))
    with_ads = unit_economics(1000, OZON, Costs(cost=200, extra=15, drr_pct=8))
    assert base.profit - with_ads.profit == pytest.approx(80 + 15)


def test_usn15_no_tax_on_loss():
    b = unit_economics(400, OZON, Costs(cost=500), Tax.usn15())
    assert b.tax == 0 and b.profit < 0


def test_solver_matches_brute_force():
    rnd = random.Random(7)
    for _ in range(40):
        t = Tariff(
            name="rnd",
            commission_pct=tiers([[rnd.choice([100, 150]), rnd.uniform(5, 20)],
                                  [rnd.choice([300, 500]), rnd.uniform(15, 30)],
                                  [None, rnd.uniform(25, 50)]]),
            logistics=tiers([[300, rnd.uniform(10, 60)], [None, rnd.uniform(60, 200)]]),
            last_mile_pct=rnd.choice([0, 20]),
            last_mile_max=25,
            acquiring_pct=rnd.uniform(0, 2),
        )
        costs = Costs(cost=rnd.uniform(10, 400), drr_pct=rnd.uniform(0, 10), return_rate_pct=rnd.uniform(0, 10))
        tax = rnd.choice([Tax.none(), Tax.usn6(), Tax.usn15(), Tax.npd()])
        target = rnd.uniform(0, 30)
        sol = price_for_margin(target, t, costs, tax, max_price=6000)
        brute = next((p for p in range(1, 6001) if unit_economics(p, t, costs, tax).margin_pct >= target - 1e-9), None)
        assert (sol.price if sol else None) == brute


def test_tier_validation():
    with pytest.raises(ValueError):
        tiers([[300, 20], [100, 30], [None, 40]])
    with pytest.raises(ValueError):
        tiers([[300, 20]])
    assert tiers(15) == (Tier(None, 15.0),)


def test_json_roundtrip(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(OZON.to_dict(), ensure_ascii=False), encoding="utf-8")
    assert load_tariff(path) == OZON


def test_wb():
    assert wb_logistics(3, first_liter=40, extra_liter=10, coefficient=1.25) == 75
    assert wb_logistics(0.5, 40, 10) == 40
    t = wb(commission_pct=25, logistics=75, reverse_logistics=50)
    b = unit_economics(1000, t, Costs(cost=300, return_rate_pct=10), Tax.usn6())
    assert b.profit == pytest.approx(1000 - 250 - 75 - 300 - 0.1 * 50 - 60)
    with pytest.raises(ValueError):
        wb_logistics(0, 40, 10)
