# NovaQuote

NovaQuote is an open-source Django application for quoting and order processing. It supports product catalogs with configurable options, proposals (quotes), **customer invoices**, and purchase **orders** with per-item ordering/delivery tracking.

### Sales flow: proposal → invoice → order

The intended sequence is:

1. **Saved calculation (proposal)** — build the quote and save it.
2. **Invoice** — create a draft invoice (line totals are snapshotted). When you **mark the invoice as sent**, it is treated as issued to the customer (payment obligation). A **lead** linked on the proposal is promoted to **client** in Contacts at that moment.
3. **Order** — only after the invoice is **sent** (or **paid**) can you create the **purchase order** to suppliers.

Open **Invoicing** in the top menu for the invoice list. You can start an invoice from a saved calculation or open it from the invoice page and use **Create order** there.

## Security (read this first)

- **Frontend** (`/price-list/`, `/proposal/`, `/invoices/`, `/orders/`, `/contacts/`, …) requires **login**. Use `/accounts/login/` (create users in **Admin → Users**). `/admin/` and `/static/` stay separate.
- **Production:** do not use the default `SECRET_KEY` or `DEBUG=True`. Set environment variables as described in **[DEPLOYMENT.md](DEPLOYMENT.md)**.
- **PostgreSQL** is recommended for multi-user production; SQLite remains the default for local dev.

See also **[ROADMAP.md](ROADMAP.md)** for architecture, GDPR, and concurrency follow-ups.

## Quick start

### 1) Create & activate a virtual environment
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 2) Install dependencies
```powershell
pip install -r requirements.txt
```

### 3) Database
This project uses SQLite by default.

```powershell
python manage.py migrate
```

The repository ships a **single squashed** `pricelist` migration (`0001_initial`). If you still have an older database that was migrated with the previous long migration chain, either start from a new `db.sqlite3` or clear recorded `pricelist` rows in `django_migrations` and run `python manage.py migrate pricelist --fake-initial` so Django matches your existing tables.

Create a **superuser** for `/admin/` and the frontend (same user can log in at `/accounts/login/`):

```powershell
python manage.py createsuperuser
```

### Demo data (wipes the database)

To **erase all data** (including users and history) and load a fresh demo catalog plus CRM (companies, departments, **organization memberships**, roles, **hobbies**, **events**, **life events**, **invoices**, **network links**), **two profit profiles**, products with **[placehold.net](https://placehold.net/600x800.png)**-style placeholder images, **price history** samples, **many product options** (UPS, paper, install service, privacy filter, …), a bundle, **contract durations**, **saved proposals** (lines, **contract snapshots**, **proposal history**), and **orders** (one sent, one draft; **order line items** with sample dates), run:

```powershell
python manage.py seed_demo --yes
```

Defaults: superuser **`admin`** / **`demo`** — change the password immediately. General settings are reset with **no custom logo** (the **bundled NovaQuote** mark is shown), site name **NovaQuote**, and the **Teal** color scheme (see below). Product images require outbound HTTPS to `placehold.net` during seed; if that fails, catalog rows are still created without files.

The seed creates **stable UUID v5** values for demo rows that have a `uuid` field (and explicit **`article_number`** on products), per project rules for external references.

Demo **Contacts** data includes:

- **Two supplier organizations** (matching the catalog distributors) with departments, people, and **product → supplier CRM** links in the catalog.
- **Three companies** (two clients, one lead) with departments and people.
- **Two network partners** and **six network links** to clients, leads, and suppliers.

Optional: `python manage.py seed_demo --yes --username you --password secret`

### 4) Run the server
```powershell
python manage.py runserver
```

### 5) Tests
```powershell
python manage.py test pricelist
```

## Translations (NL/EN)

The codebase uses Django i18n (`gettext_lazy` in Python and `{% trans %}` in templates).

On systems without GNU gettext tooling (`msgfmt`), translations are compiled using a pure-Python management command:
```powershell
python manage.py compilemessages_py -l nl
```

## Admin & configuration

### Frontend roles (who sees what on the customer site)

After migration **0002**, each user can have a **User frontend access** row linking them to a **Frontend role**. Edit the role’s checkboxes to turn areas on or off (price list, catalog, proposals, invoicing, orders, contacts, permanent delete, etc.). **Superusers** always have full frontend access.

Default templates are seeded for **Administrator**, **Sales** (no catalog), **Catalog manager** (catalog + price list only; no purge), and **Procurement** (price list, orders, read-only contacts).

#### RBAC demo accounts (log in at `/accounts/login/`)

| Username | Frontend role | What to check |
|----------|-----------------|---------------|
| `admin` (from `seed_demo` or your superuser) | Full access | All menus; can assign roles under **Admin → User frontend access**. |
| `sales` | Sales | Price list, proposals, invoicing, orders, contacts; **no** catalog / trash / purge. |
| `catalog` | Catalog manager | Price list + catalog only; soft-delete and trash; **no** proposals, invoicing, orders, or permanent purge. |
| `buyer` | Procurement | Price list, orders, contacts (read-only); **no** proposals or invoicing. |

- **`python manage.py seed_demo --yes`** — wipes the DB and creates **`admin`** (default password **`demo`**) plus **`sales`**, **`catalog`**, and **`buyer`** with the **same** password as the superuser.
- **`python manage.py seed_rbac_demo_users`** — **does not** wipe data; ensures the four **Frontend roles** exist and creates **`sales`**, **`catalog`**, and **`buyer`** if missing (default password **`demo`** for new users). Use **`--reset-password`** to set the password again on existing demo users.

Users **without** a profile keep the old behaviour: non-staff get the full menu except catalog (catalog was staff-only before); staff get catalog; only superusers could purge trash.

Log in to `/admin/` and configure `General settings` for:
- currency/rounding/number format
- frontend language
- **Color scheme** — **Orange** (#FFA726), **Navy blue** (#283593), **Teal** (#008080, default), **Black** (#424242), or **Red** (#DC143C)
- branding (**optional logo** upload to replace the default NovaQuote image, site name)

## Multiple suppliers per product

A catalog **product** can have several **supplier offers** (`Product supplier offers` inline on the product in admin): each row is supplier + cost, lead time, payment terms, and optional **Preferred supplier**. The **price list** and default proposal pricing use the **preferred** row (or the only row). The main `Product.supplier` / `cost_price` fields stay in sync with that preferred row for compatibility.

On the **Proposal** page, if a product has more than one offer, a **Supplier** column appears: pick the source per line, or use bulk actions (**Preferred**, **Cheapest price**, **Fastest delivery**, **Best payment terms**). **Save calculation** stores the chosen `ProductSupplier` on each line and recomputes the unit price server-side from the catalog (do not trust client-submitted prices for products). **Orders** group lines by the supplier chosen on the proposal line when set.

If you load a saved proposal where the same simple product appeared on multiple lines with **different** suppliers, quantities are merged into one row on the editor: the **first** line’s supplier is kept (limitation).

## Main user flows
- Price list + product detail
- Create and save proposals (quotes)
- Create orders from saved proposals
- Update per-item ordering/delivery status on the order page
- Link **Contacts (CRM)** to catalog data: **products** can reference a supplier **company, department, and contact** (organizations with the Supplier role). **Saved proposals** (and **orders**, via the proposal) can reference a **client or lead** company, department, and contact. Set these on the proposal page when saving, in **Admin → Products / Proposals**, or view them on the product and proposal/order detail pages.

## Contacts (CRM)

The **Contacts** menu links to:

- `/contacts/suppliers/` — organizations with the **SUPPLIER** role
- `/contacts/clients/` — **CLIENT** role
- `/contacts/leads/` — **LEAD** role (includes pipeline status)
- `/contacts/network/` — **NETWORK** role
- `/contacts/persons/` — person directory

Data model: **Organization** (one row per company) with multiple roles via **OrganizationRole**; **Department**; **Person**; **OrganizationPerson** (pivot). Persons have **hobbies** and dated **events** (with optional reminder offsets: on the day, 1 day, 1 week, 2 weeks, or 1 month before). **Life events** remain a separate relationship log (notes by date). Registering the first **Organization invoice** or **Organization shipment** (in admin) promotes **LEAD → CLIENT** unless suppressed or set to manual lead mode.

You can also **add and edit** companies, people, departments, and org–person links from the Contacts pages (buttons such as **Add company**, **Edit company**, **Add person**, **Link person**, **Add life event**). Success messages appear at the top of the page.

On **supplier / client / lead** organization detail pages, an **organization chart** shows departments and linked contacts (people without a department appear under **Unassigned**). Department names in the chart link to the **Departments** table on the same page (`#dept-…` anchors). **Email** and **phone** values on Contacts pages (and supplier CRM on product detail) use **`mailto:`** and **`tel:`** links so the OS mail client or dialer can open.

**Network** partners can be linked to multiple suppliers and clients via **Organization network links** (buttons **Link company** on the network partner’s page, **Link network partner** on supplier/client/lead pages). The same partner can have many links; each pair is unique.

Manage advanced bulk operations under **Admin → Organizations / Persons / …**.

