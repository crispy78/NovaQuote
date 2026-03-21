# NovaQuote — deployment & security

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | **Required** when `DJANGO_DEBUG=0`. Long random string. |
| `DJANGO_DEBUG` | `0` / `false` for production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames (e.g. `quotes.example.com,www.example.com`). **Required** when debug is off. |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` when terminating TLS at Django (often off if nginx handles HTTPS). |
| `DJANGO_SESSION_COOKIE_SECURE` | Default `1` when `DEBUG=0` (cookies only over HTTPS). |
| `DJANGO_CSRF_COOKIE_SECURE` | Default `1` when `DEBUG=0`. |
| `DJANGO_SECURE_HSTS_SECONDS` | e.g. `31536000` with HTTPS reverse proxy. |
| `DJANGO_DATABASE` | Set to `postgres` to use PostgreSQL (see below). |
| `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` | PostgreSQL connection when `DJANGO_DATABASE=postgres`. |

## PostgreSQL

1. Install the driver: `pip install "psycopg[binary]>=3.1"` (not in minimal `requirements.txt` by default).
2. Set `DJANGO_DATABASE=postgres` and the `PG*` variables.
3. Run `migrate`.

SQLite remains the default for local development.

## Frontend authentication

All routes under the main site (`/price-list/`, `/proposal/`, `/orders/`, `/contacts/`, …) require a logged-in user. Exempt paths:

- `/admin/`
- `/accounts/` (login, logout, password reset)
- `/static/` (collected static files)

**Media** (`/media/`) is **not** exempt: in `DEBUG`, Django serves media to any request; in production, serve files behind authentication (e.g. signed URLs, nginx `internal`, or a dedicated view). See Django deployment docs.

## Production checklist

- [ ] `DJANGO_DEBUG=0`, strong `DJANGO_SECRET_KEY`, non-empty `DJANGO_ALLOWED_HOSTS`
- [ ] HTTPS reverse proxy; enable `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` (defaults when debug off)
- [ ] PostgreSQL for multi-user write load
- [ ] `collectstatic`, proper `STATIC_ROOT` / CDN
- [ ] Backups and restore tests
- [ ] Rate limiting / WAF for `/accounts/login/` and APIs if exposed

`SECURE_BROWSER_XSS_FILTER` was removed in Django 4.0; rely on `SECURE_CONTENT_TYPE_NOSNIFF` and a modern browser.

## GDPR / PII (CRM)

The app stores personal data (`Person`, `OrganizationPerson`, events, etc.). Production deployments should add:

- Retention policy and periodic cleanup
- Data export (portability) and erasure procedures
- Legal basis documentation (DPA, privacy notice)

This is **not** implemented in code yet; track in `ROADMAP.md`.
