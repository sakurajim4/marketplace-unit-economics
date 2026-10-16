"""Расчёт единицы товара, подбор цены под маржу и поиск «мёртвых зон» цены."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Breakdown, Costs, Tariff, Tax

EPS = 1e-9


def unit_economics(price: float, tariff: Tariff, costs: Costs, tax: Tax | None = None) -> Breakdown:
    """Раскладывает цену продажи на удержания площадки, расходы продавца и налог."""
    if price <= 0:
        raise ValueError("цена должна быть больше нуля")
    tax = tax or Tax.none()

    commission_pct = tariff.commission_at(price)
    commission = price * commission_pct / 100
    logistics = tariff.logistics_at(price)
    last_mile = tariff.last_mile_at(price)
    acquiring = price * tariff.acquiring_pct / 100
    fixed_fee = tariff.fixed_fee
    ads = price * costs.drr_pct / 100
    per_return = tariff.reverse_logistics_at(price) + tariff.return_fee
    if not tariff.return_refunds_last_mile:
        per_return += last_mile
    returns = costs.return_rate_pct / 100 * per_return

    vat = price * tax.vat_pct / (100 + tax.vat_pct) if tax.vat_pct else 0.0
    pre_tax = price - vat - commission - logistics - last_mile - acquiring - fixed_fee - ads - returns - costs.cost - costs.extra
    if tax.kind in ("usn_income", "npd"):
        tax_amount = (price - vat) * tax.rate_pct / 100
    elif tax.kind == "usn_income_expense":
        tax_amount = max(0.0, pre_tax) * tax.rate_pct / 100
    else:
        tax_amount = 0.0
    profit = pre_tax - tax_amount

    lines = [
        (f"Комиссия {commission_pct:g}%", commission),
        ("Логистика", logistics),
        ("Последняя миля", last_mile),
        (f"Эквайринг {tariff.acquiring_pct:g}%", acquiring),
        ("Обработка отправления", fixed_fee),
        (f"Реклама (ДРР {costs.drr_pct:g}%)", ads),
        (f"Возвраты ({costs.return_rate_pct:g} на 100 продаж)", returns),
        ("Себестоимость", costs.cost),
        ("Прочие расходы на единицу", costs.extra),
        (f"НДС {tax.vat_pct:g}%", vat),
        (_tax_label(tax), tax_amount),
    ]
    return Breakdown(
        price=float(price), commission_pct=commission_pct, commission=commission, logistics=logistics,
        last_mile=last_mile, acquiring=acquiring, fixed_fee=fixed_fee, ads=ads, returns=returns,
        cost=costs.cost, extra=costs.extra, vat=vat, tax=tax_amount, profit=profit,
        lines=tuple((n, v) for n, v in lines if v),
    )


def _tax_label(tax: Tax) -> str:
    return {
        "usn_income": f"УСН «доходы» {tax.rate_pct:g}%",
        "usn_income_expense": f"УСН «доходы − расходы» {tax.rate_pct:g}%",
        "npd": f"НПД {tax.rate_pct:g}%",
        "none": "Налог",
    }[tax.kind]


def _profit(p: float, tariff: Tariff, costs: Costs, tax: Tax) -> float:
    return unit_economics(p, tariff, costs, tax).profit


def _segments(tariff: Tariff, costs: Costs, tax: Tax, lo: float, hi: float) -> list[tuple[float, float]]:
    """Интервалы (a, b], на которых прибыль линейна по цене."""
    pts = [lo] + [b for b in tariff.breakpoints() if lo < b < hi] + [hi]
    segs = list(zip(pts[:-1], pts[1:]))
    if tax.kind != "usn_income_expense":
        return segs
    # УСН 15 % — излом там, где прибыль до налога проходит через ноль
    no_tax = Tax("none", 0.0, tax.vat_pct)
    out = []
    for a, b in segs:
        k, c = _linear(lambda p: _profit(p, tariff, costs, no_tax), a, b)
        if k and a < -c / k < b:
            out += [(a, -c / k), (-c / k, b)]
        else:
            out.append((a, b))
    return out


def _linear(f, a: float, b: float) -> tuple[float, float]:
    """Коэффициенты k, c прямой f(p) = k·p + c по двум внутренним точкам (a, b]."""
    span = b - a
    p1, p2 = a + span * 0.25, a + span * 0.75
    f1, f2 = f(p1), f(p2)
    k = (f2 - f1) / (p2 - p1)
    return k, f1 - k * p1


def _min_price(tariff: Tariff, costs: Costs, tax: Tax, *, margin: float, offset: float,
               lo: float, hi: float, step: float) -> float | None:
    """Минимальная цена p из (lo, hi], кратная step, где profit(p) ≥ margin·p + offset."""
    def ok(p: float) -> bool:
        return _profit(p, tariff, costs, tax) >= margin * p + offset - EPS

    for a, b in _segments(tariff, costs, tax, lo, hi):
        k, c = _linear(lambda p: _profit(p, tariff, costs, tax), a, b)
        coef, rhs = k - margin, offset - c  # условие: coef·p ≥ rhs
        if coef > EPS:
            start = max(a, rhs / coef)
        elif coef < -EPS and rhs / coef > a:
            start = a
        elif abs(coef) <= EPS and rhs <= EPS:
            start = a
        else:
            continue
        if start > b:
            continue
        p = math.floor(start / step) * step
        while p <= a + EPS or p < start - EPS:
            p += step
        # округление вверх может перескочить границу полки — проверяем по-честному
        for _ in range(3):
            if p <= hi + EPS and ok(p):
                return round(p, 2)
            p += step
    return None


@dataclass(frozen=True)
class PriceSolution:
    price: float
    breakdown: Breakdown


def price_for_margin(target_margin_pct: float, tariff: Tariff, costs: Costs, tax: Tax | None = None,
                     *, step: float = 1.0, max_price: float = 1_000_000.0) -> PriceSolution | None:
    """Минимальная цена (с шагом ``step``), при которой маржа ≥ цели.

    Комиссия и логистика меняются на ценовых полках, поэтому зависимость прибыли
    от цены ступенчатая: цена чуть выше порога может быть хуже цены чуть ниже.
    Решение ищется аналитически на каждом линейном участке, без перебора.
    Возвращает ``None``, если цель недостижима до ``max_price``.
    """
    tax = tax or Tax.none()
    p = _min_price(tariff, costs, tax, margin=target_margin_pct / 100, offset=0.0,
                   lo=0.0, hi=max_price, step=step)
    if p is None:
        return None
    return PriceSolution(p, unit_economics(p, tariff, costs, tax))


def break_even_price(tariff: Tariff, costs: Costs, tax: Tax | None = None, *, step: float = 1.0) -> float | None:
    sol = price_for_margin(0.0, tariff, costs, tax, step=step)
    return sol.price if sol else None


@dataclass(frozen=True)
class DeadZone:
    """Цены от ``start`` (не включая) до ``end`` (не включая) дают прибыль ниже, чем на ``start``."""

    start: float
    end: float | None
    profit_at_start: float
    profit_after_start: float


def dead_zones(tariff: Tariff, costs: Costs, tax: Tax | None = None, *, step: float = 1.0,
               max_price: float = 1_000_000.0) -> list[DeadZone]:
    """Ищет пороги, после которых прибыль падает, и цену, где она восстанавливается.

    Пример: у Ozon на 300 ₽ комиссия и логистика переходят на дорогую полку —
    цена 301 ₽ может приносить меньше, чем 299 ₽, вплоть до заметно более высокой цены.
    """
    tax = tax or Tax.none()
    zones = []
    for b in tariff.breakpoints():
        if b <= 0 or b >= max_price:
            continue
        at = _profit(b, tariff, costs, tax)
        after = _profit(b + step, tariff, costs, tax)
        if after >= at - EPS:
            continue
        end = _min_price(tariff, costs, tax, margin=0.0, offset=at, lo=b + step, hi=max_price, step=step)
        zones.append(DeadZone(b, end, at, after))
    return zones


def scan(prices: list[float], tariff: Tariff, costs: Costs, tax: Tax | None = None) -> list[Breakdown]:
    return [unit_economics(p, tariff, costs, tax) for p in prices]
