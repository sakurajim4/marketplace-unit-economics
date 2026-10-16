"""Юнит-экономика товара на маркетплейсах (Ozon, Wildberries)."""

__version__ = "0.1.0"

from .calc import DeadZone, PriceSolution, break_even_price, dead_zones, price_for_margin, scan, unit_economics
from .model import Breakdown, Costs, Tariff, Tax, Tier, load_tariff, tiers
from .presets import ozon_fbs_2026_08, wb, wb_logistics

__all__ = [
    "Breakdown",
    "Costs",
    "DeadZone",
    "PriceSolution",
    "Tariff",
    "Tax",
    "Tier",
    "break_even_price",
    "dead_zones",
    "load_tariff",
    "ozon_fbs_2026_08",
    "price_for_margin",
    "scan",
    "tiers",
    "unit_economics",
    "wb",
    "wb_logistics",
]
