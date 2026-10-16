"""Сравнить несколько товаров: минимальная цена под маржу 25 % и мёртвые зоны."""

from marketplace_unit_economics import Costs, Tax, dead_zones, ozon_fbs_2026_08, price_for_margin

tariff = ozon_fbs_2026_08(logistics_low=32, logistics_high=100)
tax = Tax.usn6()

for name, cost in [("Набор А", 60), ("Набор Б", 180), ("Набор В", 450)]:
    costs = Costs(cost=cost, drr_pct=5, return_rate_pct=4)
    sol = price_for_margin(25, tariff, costs, tax)
    price = f"{sol.price:.0f} ₽" if sol else "недостижима"
    zones = ", ".join(f"{z.start:.0f}→{z.end:.0f} ₽" for z in dead_zones(tariff, costs, tax) if z.end)
    print(f"{name}: закупка {cost} ₽ → цена для 25 %: {price}; мёртвые зоны: {zones or 'нет'}")
