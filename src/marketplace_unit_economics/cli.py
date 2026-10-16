"""mpue — юнит-экономика товара на Ozon/WB из командной строки."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .calc import dead_zones, price_for_margin, scan, unit_economics
from .model import Breakdown, Costs, Tariff, Tax, Tier, load_tariff
from .presets import PRESETS, wb, wb_logistics

TAXES = {
    "usn6": Tax.usn6,
    "usn15": Tax.usn15,
    "npd": Tax.npd,
    "none": Tax.none,
}


def _money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ")


def _common(ap: argparse.ArgumentParser) -> None:
    src = ap.add_argument_group("тариф")
    src.add_argument("--preset", choices=list(PRESETS), help="готовый тариф-пример")
    src.add_argument("--tariff", help="JSON-файл тарифа (см. examples/)")
    src.add_argument("--wb", action="store_true", help="тариф Wildberries из --commission и --logistics")
    src.add_argument("--commission", type=float, help="комиссия, %% (заменяет полки тарифа)")
    src.add_argument("--logistics", type=float, help="логистика, ₽ (заменяет полки тарифа)")
    src.add_argument("--wb-volume", type=float, help="объём, л — посчитать логистику WB")
    src.add_argument("--wb-first-liter", type=float, help="WB: ставка за первый литр, ₽")
    src.add_argument("--wb-extra-liter", type=float, help="WB: ставка за доп. литр, ₽")
    src.add_argument("--wb-coef", type=float, default=1.0, help="WB: коэффициент склада (1.25 = 125%%)")
    src.add_argument("--acquiring", type=float, help="эквайринг, %%")

    c = ap.add_argument_group("затраты и налог")
    c.add_argument("--cost", type=float, required=True, help="себестоимость единицы, ₽")
    c.add_argument("--extra", type=float, default=0.0, help="прочие расходы на единицу (упаковка, маркировка), ₽")
    c.add_argument("--drr", type=float, default=0.0, help="доля рекламных расходов, %% от цены")
    c.add_argument("--returns", type=float, default=0.0, help="возвратов и невыкупов на 100 продаж")
    c.add_argument("--tax", choices=list(TAXES), default="usn6", help="налоговый режим (по умолчанию usn6)")
    c.add_argument("--tax-rate", type=float, help="своя ставка налога, %%")
    c.add_argument("--vat", type=float, default=0.0, help="НДС внутри цены, %% (например 5)")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")


def _tariff(args: argparse.Namespace) -> Tariff:
    logistics = args.logistics
    if args.wb_volume is not None:
        if args.wb_first_liter is None or args.wb_extra_liter is None:
            raise SystemExit("для --wb-volume нужны --wb-first-liter и --wb-extra-liter")
        logistics = wb_logistics(args.wb_volume, args.wb_first_liter, args.wb_extra_liter, args.wb_coef)

    if args.wb:
        if args.commission is None or logistics is None:
            raise SystemExit("для --wb нужны --commission и --logistics (или --wb-volume)")
        return wb(args.commission, logistics, acquiring_pct=args.acquiring or 0.0)
    if args.tariff:
        base = load_tariff(args.tariff)
    elif args.preset:
        base = PRESETS[args.preset]()
    elif args.commission is not None:
        base = Tariff(name="Свой тариф", commission_pct=(Tier(None, args.commission),))
    else:
        raise SystemExit("укажите --preset, --tariff, --wb или хотя бы --commission")
    return base.with_overrides(
        commission_pct=None if args.commission is None else (Tier(None, args.commission),),
        logistics=None if logistics is None else (Tier(None, logistics),),
        acquiring_pct=args.acquiring,
    )


def _tax(args: argparse.Namespace) -> Tax:
    factory = TAXES[args.tax]
    if args.tax == "none":
        return factory()
    if args.tax == "npd":
        return factory(args.tax_rate) if args.tax_rate is not None else factory()
    kw = {"vat_pct": args.vat}
    if args.tax_rate is not None:
        kw["rate_pct"] = args.tax_rate
    return factory(**kw)


def _costs(args: argparse.Namespace) -> Costs:
    return Costs(cost=args.cost, extra=args.extra, drr_pct=args.drr, return_rate_pct=args.returns)


def _print_breakdown(b: Breakdown, tariff: Tariff) -> None:
    print(f"Тариф: {tariff.name}" + (f" (на {tariff.as_of})" if tariff.as_of else ""))
    print(f"Цена продажи{'':<27}{_money(b.price):>12} ₽")
    for name, value in b.lines:
        print(f"  − {name:<35}{_money(value):>12} ₽")
    print(f"Прибыль с единицы{'':<22}{_money(b.profit):>12} ₽")
    print(f"Маржа {b.margin_pct:.1f}%", end="")
    if b.roi_pct is not None:
        print(f" · ROI {b.roi_pct:.0f}% · наценка ×{b.markup:.2f}", end="")
    print(f" · к выплате от площадки {_money(b.payout)} ₽")
    if tariff.note:
        print(f"Примечание: {tariff.note}")


def cmd_calc(args: argparse.Namespace) -> int:
    tariff, costs, tax = _tariff(args), _costs(args), _tax(args)
    b = unit_economics(args.price, tariff, costs, tax)
    if args.json:
        print(json.dumps({"tariff": tariff.name, **b.to_dict()}, ensure_ascii=False, indent=2))
    else:
        _print_breakdown(b, tariff)
    return 0


def cmd_price(args: argparse.Namespace) -> int:
    tariff, costs, tax = _tariff(args), _costs(args), _tax(args)
    sol = price_for_margin(args.margin, tariff, costs, tax, step=args.step)
    zones = dead_zones(tariff, costs, tax, step=args.step)
    if args.json:
        print(json.dumps({
            "target_margin_pct": args.margin,
            "price": sol.price if sol else None,
            "breakdown": sol.breakdown.to_dict() if sol else None,
            "dead_zones": [z.__dict__ for z in zones],
        }, ensure_ascii=False, indent=2))
        return 0 if sol else 1
    if sol is None:
        print(f"Маржа {args.margin:g}% недостижима при этих затратах и тарифе.")
        return 1
    print(f"Минимальная цена для маржи {args.margin:g}%: {_money(sol.price)} ₽\n")
    _print_breakdown(sol.breakdown, tariff)
    _print_zones(zones)
    return 0


def _print_zones(zones) -> None:
    for z in zones:
        end = f"до {_money(z.end)} ₽" if z.end else "до конца диапазона"
        print(f"\nМёртвая зона: после {_money(z.start)} ₽ прибыль падает с {_money(z.profit_at_start)} "
              f"до {_money(z.profit_after_start)} ₽ и не возвращается {end}.")


def cmd_scan(args: argparse.Namespace) -> int:
    tariff, costs, tax = _tariff(args), _costs(args), _tax(args)
    prices, p = [], args.start
    while p <= args.stop + 1e-9:
        prices.append(round(p, 2))
        p += args.by
    rows = scan(prices, tariff, costs, tax)
    zones = dead_zones(tariff, costs, tax)
    if args.json:
        print(json.dumps({"rows": [r.to_dict() for r in rows], "dead_zones": [z.__dict__ for z in zones]},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"{'цена':>10} {'комиссия':>9} {'логистика':>10} {'прибыль':>10} {'маржа':>7}")
    for r in rows:
        print(f"{_money(r.price):>10} {r.commission_pct:>8g}% {_money(r.logistics):>10} "
              f"{_money(r.profit):>10} {r.margin_pct:>6.1f}%")
    _print_zones(zones)
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    for key, factory in PRESETS.items():
        t = factory()
        print(f"{key}: {t.name}\n  {t.note}")
        print("  " + json.dumps(t.to_dict(), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mpue", description="Юнит-экономика товара на Ozon и Wildberries")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("calc", help="раскладка цены и прибыль с единицы")
    p.add_argument("--price", type=float, required=True, help="цена продажи, ₽")
    _common(p)
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("price", help="минимальная цена под целевую маржу")
    p.add_argument("--margin", type=float, required=True, help="целевая маржа, %% от цены")
    p.add_argument("--step", type=float, default=1.0, help="шаг цены, ₽ (по умолчанию 1)")
    _common(p)
    p.set_defaults(func=cmd_price)

    p = sub.add_parser("scan", help="таблица прибыли по диапазону цен")
    p.add_argument("--from", dest="start", type=float, required=True)
    p.add_argument("--to", dest="stop", type=float, required=True)
    p.add_argument("--by", type=float, default=50.0, help="шаг таблицы, ₽")
    _common(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("presets", help="показать встроенные тарифы-примеры")
    p.set_defaults(func=cmd_presets)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
