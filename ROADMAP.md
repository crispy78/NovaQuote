# NovaQuote — technical roadmap

Items raised in expert review; priority is indicative.

## 1. Architecture (medium–long term)

**Split the `pricelist` app** into focused Django apps, e.g.:

- `catalog` — products, suppliers, combinations, profit profiles, price history  
- `quotes` — proposals, lines, snapshots, history  
- `orders` — orders, lines, line items  
- `crm` — organizations, persons, departments, network links, invoices/shipments  

Benefits: smaller `models.py` files, clearer imports, easier ownership per team.

**Prerequisite:** stable internal APIs or services between domains; migrations can be done incrementally (move models with `SeparateDatabaseAndState`).

## 2. Data integrity & concurrency

- **Proposal immutability:** document and test that `ProposalLine` / `ProposalContractSnapshot` snapshots are authoritative for historical quotes; `update-rates` is an explicit, audited action (`ProposalHistory`).
- **Product ↔ preferred `ProductSupplier`:** `sync_product_primary_from_suppliers` uses `update()` to avoid recursion; under concurrent admin edits, last write wins. Mitigations: short transactions, optional `select_for_update` on critical saves, or moving to a single source of truth UI (edit offers only, read-only mirror on product).

## 3. Test coverage (ongoing)

Baseline tests exist under `pricelist/tests/` for:

- Login middleware behaviour  
- Profit profile / rounding / `ProductSupplier` sync  
- Multi-supplier strategy helpers  

**Next targets:** `proposal_save_view` (POST → lines + prices), order creation from proposal, CRM promotion rules.

## 4. GDPR tooling (feature work)

- Export: management command or admin action → JSON/CSV for one person/org  
- Erasure: anonymise or cascade-delete with safeguards  
- Configurable retention job (e.g. `django-extensions` cron or Celery)

## 5. API / integrations (optional)

If external systems need quotes or catalog data, add a versioned API (e.g. DRF) with token auth, separate from session-based frontend.
