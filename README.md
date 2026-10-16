# marketplace-unit-economics

[![tests](https://github.com/sakurajim4/marketplace-unit-economics/actions/workflows/tests.yml/badge.svg)](https://github.com/sakurajim4/marketplace-unit-economics/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)

Юнит-экономика товара на **Ozon** и **Wildberries**: сколько остаётся с одной продажи после комиссии, логистики, последней мили, эквайринга, рекламы, возвратов и налога. Есть подбор **минимальной цены под целевую маржу** и поиск **«мёртвых зон»** — диапазонов цен, где из-за ценовых полок комиссии прибыль ниже, чем чуть дешевле.

Python-библиотека и CLI `mpue`, без внешних зависимостей.

## Зачем

У Ozon комиссия и логистика зависят от **цены товара**, а не только от категории. Например, для FBS-категории «Дом и сад» по тарифам от 28.08.2026:

| цена продажи | комиссия FBS | логистика, коробка 2 л, СПб → Москва |
|---|---|---|
| до 100 ₽ | 17 % | 32 ₽ |
| 101–300 ₽ | 23 % | 32 ₽ |
| выше 300 ₽ | 52 % (49 % при сдаче до рекомендованного слота) | 100 ₽ |

Из-за этого цена 301 ₽ может приносить вдвое меньше, чем 299 ₽, а прежний уровень прибыли возвращается только около 600–700 ₽. Обычный калькулятор с одной ставкой этого не покажет. Здесь каждая ставка задаётся полками по цене, а решатель учитывает переходы между ними.

> Ставки в пресете — пример на указанную дату для одной категории. Комиссия зависит от категории и схемы, логистика — от объёма и пары кластеров. Перед решением о цене сверьте ставки в кабинете и подставьте свои (JSON-файл или `Tariff`).

## Установка

```bash
pip install git+https://github.com/sakurajim4/marketplace-unit-economics
```

## CLI

```bash
# раскладка цены
mpue calc --preset ozon-fbs-2026-08 --price 1800 --cost 300 --drr 5 --returns 4 --tax usn6
```

```
Тариф: Ozon FBS · Дом и сад · 28.08.2026 (на 2026-08-28)
Цена продажи                               1 800.00 ₽
  − Комиссия 49%                             882.00 ₽
  − Логистика                                100.00 ₽
  − Последняя миля                            25.00 ₽
  − Эквайринг 1%                              18.00 ₽
  − Реклама (ДРР 5%)                          90.00 ₽
  − Возвраты (4 на 100 продаж)                 5.00 ₽
  − Себестоимость                            300.00 ₽
  − УСН «доходы» 6%                          108.00 ₽
Прибыль с единицы                            272.00 ₽
Маржа 15.1% · ROI 91% · наценка ×6.00 · к выплате от площадки 775.00 ₽
```

```bash
# минимальная цена под маржу 25 % + мёртвые зоны
mpue price --preset ozon-fbs-2026-08 --margin 25 --cost 300 --returns 4 --tax usn6
```

```
Минимальная цена для маржи 25%: 2 264.00 ₽
...
Мёртвая зона: после 300.00 ₽ прибыль падает с -149.28 до -297.56 ₽ и не возвращается до 638.00 ₽.
```

```bash
# таблица прибыли по диапазону цен
mpue scan --preset ozon-fbs-2026-08 --from 250 --to 700 --by 50 --cost 300

# свой тариф из файла (см. examples/ozon_fbs_tariff.json)
mpue calc --tariff my_tariff.json --price 299 --cost 60

# Wildberries: комиссия категории + логистика по объёму и коэффициенту склада
mpue calc --wb --commission 24.5 --wb-volume 3 --wb-first-liter 40 --wb-extra-liter 10 --wb-coef 1.2 \
          --price 1500 --cost 400 --json
```

Основные параметры: `--cost` себестоимость, `--extra` прочие расходы на единицу (упаковка, маркировка), `--drr` доля рекламных расходов в % от цены, `--returns` возвратов/невыкупов на 100 продаж, `--tax usn6|usn15|npd|none`, `--tax-rate` своя ставка, `--vat` НДС внутри цены (например 5), `--commission` и `--logistics` — заменить ставки тарифа одной цифрой, `--json` — машиночитаемый вывод.

## Библиотека

```python
from marketplace_unit_economics import (
    Costs, Tariff, Tax, Tier, dead_zones, ozon_fbs_2026_08, price_for_margin, unit_economics,
)

tariff = ozon_fbs_2026_08(logistics_low=32, logistics_high=100)
costs = Costs(cost=300, drr_pct=5, return_rate_pct=4)

b = unit_economics(1800, tariff, costs, Tax.usn6())
print(b.profit, b.margin_pct, b.payout)
for name, amount in b.lines:
    print(name, round(amount, 2))

sol = price_for_margin(25, tariff, costs, Tax.usn6())   # None, если цель недостижима
print(sol.price)

for z in dead_zones(tariff, costs, Tax.usn6()):
    print(f"после {z.start} ₽ прибыль ниже, чем на {z.start} ₽, вплоть до {z.end} ₽")

# свой тариф: полки задаются как (цена «до» включительно, значение)
my = Tariff(
    name="Ozon FBO · моя категория",
    commission_pct=[(300, 20), (None, 38)],
    logistics=[(300, 45), (None, 120)],
    last_mile_pct=20, last_mile_max=25, acquiring_pct=1,
)
```

## Что и как считается

```
прибыль = цена − НДС − комиссия(цена) − логистика(цена) − последняя_миля − эквайринг − обработка
        − реклама − возвраты − себестоимость − прочие − налог
```

- **Комиссия, логистика, обратная логистика** — ступенчатые, по ценовым полкам (`Tier(up_to, value)`; граница включительно).
- **Последняя миля** — % от цены с потолком (у Ozon на 28.08.2026: 20 %, не более 25 ₽).
- **Возвраты:** `возвратов на 100 продаж / 100 × (обратная логистика + плата за возврат + невозвращаемая последняя миля)`. Комиссию при невыкупе Ozon не удерживает, поэтому она в стоимость возврата не входит.
- **Налоги:** УСН «доходы» (от выручки), УСН «доходы минус расходы» (от прибыли, на убыток налог 0), НПД (от выручки), опционально НДС внутри цены (`цена × НДС / (100 + НДС)`, уменьшает базу УСН «доходы»). Минимальный налог УСН 1 % считается по году и здесь не учитывается.
- **Цена под маржу:** прибыль линейна по цене между точками перелома (границы полок, потолок последней мили, ноль прибыли для УСН 15 %), поэтому решение находится аналитически на каждом участке, без перебора, и затем проверяется честным пересчётом. Тесты сверяют решатель с полным перебором на случайных тарифах.
- **Мёртвая зона:** для каждой границы полки — проверка, падает ли прибыль сразу за ней, и поиск цены, где она возвращается к прежнему уровню.

## Разработка

```bash
pip install -e ".[dev]"
pytest
```

## Лицензия

MIT

---

## English

**marketplace-unit-economics** is a zero-dependency Python library and CLI (`mpue`) for per-unit economics on Russian marketplaces Ozon and Wildberries: commission, logistics, last mile, acquiring, ad spend share (DRR), returns, and taxes (USN 6 %, USN 15 %, NPD, optional VAT).

Ozon commission and logistics depend on the *sale price* via price tiers (e.g. 23 % up to 300 ₽, 49–52 % above), which creates "dead zones" where a slightly higher price earns much less. The library models every rate as price tiers, finds the minimum price for a target margin analytically per linear segment (verified against brute force in tests), and reports dead zones. Bundled rates are a dated example (Ozon FBS, 2026-08-28) — always check your own seller account and pass your own tariff (JSON or `Tariff`).

```bash
pip install git+https://github.com/sakurajim4/marketplace-unit-economics
mpue price --preset ozon-fbs-2026-08 --margin 25 --cost 300 --returns 4 --tax usn6
```
