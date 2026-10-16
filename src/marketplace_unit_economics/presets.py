"""Готовые тарифы-примеры.

Ставки площадок меняются несколько раз в год и зависят от категории, схемы
(FBO/FBS), объёма товара и пары кластеров. Пресеты ниже — снимок на указанную
дату для конкретного случая, чтобы было с чего начать. Перед решением о цене
сверяйте ставки в своём кабинете и подставляйте свои через ``Tariff`` или JSON.
"""

from __future__ import annotations

from .model import Tariff, Tier


def ozon_fbs_2026_08(logistics_low: float = 32.0, logistics_high: float = 100.0,
                     slot_discount: bool = True) -> Tariff:
    """Ozon FBS, категория «Дом и сад» (искусственные цветы), тарифы от 28.08.2026.

    * комиссия по цене продажи: до 100 ₽ — 17 %, 101–300 ₽ — 23 %, выше 300 ₽ — 52 %;
      −3 п.п. за передачу отправления до рекомендованного слота (``slot_discount``) → 49 %;
    * логистика зависит от объёма и пары кластеров, а не от веса; на полке до 300 ₽
      она примерно втрое дешевле. По умолчанию — коробка 2 л, СПб → Москва: 32 ₽ / 100 ₽;
    * последняя миля — 20 % цены, но не более 25 ₽;
    * эквайринг 1 %; обработка отправления при сдаче в сортировочный центр — 0 ₽;
    * обратная логистика при невыкупе равна прямой; последнюю милю не возвращают.
    """
    high = 49.0 if slot_discount else 52.0
    return Tariff(
        name="Ozon FBS · Дом и сад · 28.08.2026",
        commission_pct=(Tier(100, 17.0), Tier(300, 23.0), Tier(None, high)),
        logistics=(Tier(300, logistics_low), Tier(None, logistics_high)),
        last_mile_pct=20.0,
        last_mile_max=25.0,
        acquiring_pct=1.0,
        fixed_fee=0.0,
        as_of="2026-08-28",
        note="Пример. Ставки зависят от категории, объёма и кластеров — сверяйте в кабинете.",
    )


def wb(commission_pct: float, logistics: float, acquiring_pct: float = 0.0,
       reverse_logistics: float | None = None, name: str = "Wildberries") -> Tariff:
    """Wildberries: комиссия категории и логистика задаются вручную из кабинета.

    Логистику удобно посчитать через :func:`wb_logistics`.
    """
    return Tariff(
        name=name,
        commission_pct=(Tier(None, commission_pct),),
        logistics=(Tier(None, logistics),),
        acquiring_pct=acquiring_pct,
        reverse_logistics=None if reverse_logistics is None else (Tier(None, reverse_logistics),),
        return_refunds_last_mile=True,
        note="Ставки задаются пользователем.",
    )


def wb_logistics(volume_l: float, first_liter: float, extra_liter: float, coefficient: float = 1.0) -> float:
    """Логистика WB по объёму: базовая ставка за первый литр + за каждый следующий,
    умноженные на коэффициент склада (в долях: 1.25 = 125 %). Ставки берутся из кабинета."""
    if volume_l <= 0:
        raise ValueError("объём должен быть больше нуля")
    extra = max(0.0, volume_l - 1.0)
    return round((first_liter + extra * extra_liter) * coefficient, 2)


PRESETS = {
    "ozon-fbs-2026-08": ozon_fbs_2026_08,
}
