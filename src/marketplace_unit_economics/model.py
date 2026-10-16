"""Модель: тариф площадки, налог, затраты продавца и раскладка цены."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence, Union

INF = math.inf


@dataclass(frozen=True)
class Tier:
    """Значение, действующее для цен до ``up_to`` включительно (``None`` — без верхней границы)."""

    up_to: float | None
    value: float


TierInput = Union[float, int, Sequence[Tier], Sequence[Sequence[Any]]]


def tiers(spec: TierInput) -> tuple[Tier, ...]:
    """Нормализует ставку: число → одна полка; ``[[300, 23], [None, 49]]`` → полки."""
    if isinstance(spec, (int, float)):
        return (Tier(None, float(spec)),)
    out = []
    for t in spec:
        if isinstance(t, Tier):
            out.append(t)
        else:
            up_to, value = t
            out.append(Tier(None if up_to is None else float(up_to), float(value)))
    bounds = [t.up_to for t in out]
    if not out or bounds[-1] is not None:
        raise ValueError("последняя полка должна быть без верхней границы (up_to=None)")
    finite = [b for b in bounds[:-1] if b is not None]
    if len(finite) != len(bounds) - 1 or finite != sorted(finite) or len(set(finite)) != len(finite):
        raise ValueError("границы полок должны строго возрастать, None — только у последней")
    return tuple(out)


def tier_value(ts: Sequence[Tier], price: float) -> float:
    for t in ts:
        if t.up_to is None or price <= t.up_to:
            return t.value
    return ts[-1].value


@dataclass(frozen=True)
class Tariff:
    """Тариф площадки для одной категории/схемы.

    Ставки зависят от цены продажи через полки (``Tier``): у Ozon и комиссия,
    и логистика меняются на ценовых порогах. Все проценты — в процентах (17 = 17 %).
    """

    name: str
    commission_pct: tuple[Tier, ...]
    logistics: tuple[Tier, ...] = (Tier(None, 0.0),)
    last_mile_pct: float = 0.0
    last_mile_max: float | None = None
    acquiring_pct: float = 0.0
    fixed_fee: float = 0.0
    reverse_logistics: tuple[Tier, ...] | None = None
    return_fee: float = 0.0
    return_refunds_last_mile: bool = False
    as_of: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "commission_pct", tiers(self.commission_pct))
        object.__setattr__(self, "logistics", tiers(self.logistics))
        if self.reverse_logistics is not None:
            object.__setattr__(self, "reverse_logistics", tiers(self.reverse_logistics))

    def commission_at(self, price: float) -> float:
        return tier_value(self.commission_pct, price)

    def logistics_at(self, price: float) -> float:
        return tier_value(self.logistics, price)

    def reverse_logistics_at(self, price: float) -> float:
        return tier_value(self.reverse_logistics or self.logistics, price)

    def last_mile_at(self, price: float) -> float:
        v = price * self.last_mile_pct / 100
        return min(v, self.last_mile_max) if self.last_mile_max is not None else v

    def breakpoints(self) -> list[float]:
        """Цены, на которых меняется формула: границы полок и потолок последней мили."""
        pts = {t.up_to for t in self.commission_pct + self.logistics + (self.reverse_logistics or ()) if t.up_to is not None}
        if self.last_mile_pct > 0 and self.last_mile_max is not None:
            pts.add(self.last_mile_max * 100 / self.last_mile_pct)
        return sorted(pts)

    def with_overrides(self, **kw: Any) -> "Tariff":
        data = {f: getattr(self, f) for f in self.__dataclass_fields__}
        data.update({k: v for k, v in kw.items() if v is not None})
        return Tariff(**data)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Tariff":
        d = dict(d)
        for key in ("commission_pct", "logistics", "reverse_logistics"):
            if key in d and d[key] is not None:
                d[key] = tiers(d[key])
        return cls(**d)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("commission_pct", "logistics", "reverse_logistics"):
            if d[key] is not None:
                d[key] = [[t["up_to"], t["value"]] for t in d[key]]
        return d


def load_tariff(path: str | Path) -> Tariff:
    return Tariff.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


TaxKind = Literal["usn_income", "usn_income_expense", "npd", "none"]


@dataclass(frozen=True)
class Tax:
    """Налог с одной продажи.

    * ``usn_income`` — УСН «доходы», ставка от выручки (обычно 6 %, в ряде регионов меньше);
    * ``usn_income_expense`` — УСН «доходы минус расходы», ставка от прибыли до налога (обычно 15 %);
    * ``npd`` — налог на профессиональный доход, от выручки (4 % при продаже физлицам);
    * ``vat_pct`` — НДС внутри цены (например, 5 % для УСН с доходом выше порога), считается
      как ``цена × vat / (100 + vat)`` и уменьшает базу УСН «доходы».

    Минимальный налог УСН 1 % считается по году, а не по единице товара — здесь не учитывается.
    """

    kind: TaxKind = "usn_income"
    rate_pct: float = 6.0
    vat_pct: float = 0.0

    @classmethod
    def usn6(cls, rate_pct: float = 6.0, vat_pct: float = 0.0) -> "Tax":
        return cls("usn_income", rate_pct, vat_pct)

    @classmethod
    def usn15(cls, rate_pct: float = 15.0, vat_pct: float = 0.0) -> "Tax":
        return cls("usn_income_expense", rate_pct, vat_pct)

    @classmethod
    def npd(cls, rate_pct: float = 4.0) -> "Tax":
        return cls("npd", rate_pct, 0.0)

    @classmethod
    def none(cls) -> "Tax":
        return cls("none", 0.0, 0.0)


@dataclass(frozen=True)
class Costs:
    """Затраты продавца на единицу товара.

    ``return_rate_pct`` — сколько возвратов и невыкупов приходится на 100 продаж
    (4 = 4 возврата на 100 выкупленных единиц). Каждый такой случай стоит обратной
    логистики, невозвращаемой последней мили и платы за обработку возврата.
    """

    cost: float
    extra: float = 0.0
    drr_pct: float = 0.0
    return_rate_pct: float = 0.0


@dataclass(frozen=True)
class Breakdown:
    price: float
    commission_pct: float
    commission: float
    logistics: float
    last_mile: float
    acquiring: float
    fixed_fee: float
    ads: float
    returns: float
    cost: float
    extra: float
    vat: float
    tax: float
    profit: float
    lines: tuple[tuple[str, float], ...] = field(default=(), compare=False)

    @property
    def marketplace_fees(self) -> float:
        return self.commission + self.logistics + self.last_mile + self.acquiring + self.fixed_fee

    @property
    def payout(self) -> float:
        """Сколько площадка перечислит продавцу за продажу (до рекламы, возвратов и налога)."""
        return self.price - self.marketplace_fees

    @property
    def margin_pct(self) -> float:
        return self.profit / self.price * 100 if self.price else 0.0

    @property
    def roi_pct(self) -> float | None:
        base = self.cost + self.extra
        return self.profit / base * 100 if base else None

    @property
    def markup(self) -> float | None:
        return self.price / self.cost if self.cost else None

    def to_dict(self) -> dict[str, Any]:
        d = {k: round(v, 2) for k, v in asdict(self).items() if isinstance(v, float)}
        d.update(
            marketplace_fees=round(self.marketplace_fees, 2),
            payout=round(self.payout, 2),
            margin_pct=round(self.margin_pct, 2),
            roi_pct=None if self.roi_pct is None else round(self.roi_pct, 2),
            markup=None if self.markup is None else round(self.markup, 3),
        )
        return d
