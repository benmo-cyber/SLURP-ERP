# Tariff flow (manual only)

Flexport HTS (Harmonized Tariff Schedule) integration has been **removed**. Flexport does not provide a public API for tariff lookup.

## How tariffs work now

- **Tariff** is a decimal rate (e.g. `0.381` for 38.1%) stored on **Item** and **CostMaster**.
- **HTS code** and **country of origin** remain on Item/CostMaster for **reference only** (e.g. for customs docs). They are **not** used to look up duty rates.
- You enter the **tariff** manually when creating or editing:
  - Items (e.g. when setting cost/vendor info), or
  - Cost Master rows (Finance → Cost Master List).
- Landed cost is still computed as: **(Price per kg × (1 + Tariff)) + Freight per kg** (and equivalent per lb).

## What was removed

- `erp_core/flexport_tariff.py` – deleted (no Flexport API calls).
- All automatic “look up tariff from Flexport using HTS + country of origin” logic in `views.py` (item create/update, cost master).
- The **Refresh Tariffs** button was removed from the Cost Master List UI. The backend endpoint `POST /api/cost-master/refresh_tariffs/` still exists but is a no-op and returns a message that tariffs are manual.
- The management command `python manage.py refresh_tariffs` is a no-op and prints that Flexport integration was removed. You can leave or remove any cron/scheduled task that called it.

## Optional: external duty-rate sources

If you want to automate duty rates again later, you’d need a provider that offers an API (e.g. some customs brokers or trade data vendors). Until then, use manual tariff entry and keep HTS/origin for reference and documentation.
