# Security: SQL injection, CSRF, SSRF

Regression tests for everything below are in `tests/test_security.py` (26 tests).

## SQL injection
- **Queries:** all database access uses the SQLAlchemy ORM with bound parameters. A test fails if `text()`, `exec_driver_sql` or SQL built from strings appears in `geocrop/api/` or `geocrop/db.py`.
- **IDs from URLs** are parsed as UUIDs (`_uuid()` in `app_routes.py`). Anything else is answered with 404 before reaching the database.
- **Least privilege** (`scripts/db/create_app_role.py`): the API connects as `geocrop_app`. That login can only read and write rows in the four profile tables. It is not a superuser, cannot create or alter tables, cannot create roles, and cannot run `COPY ... PROGRAM` or read server files. It has `statement_timeout = 5s`.
- **Admin login:** the owner/admin login (`GEOCROP_DB_USER`) is used only for schema setup.
- **Credentials:** they're built with `sqlalchemy.URL.create`, so special characters in passwords are safe.

## CSRF (`geocrop/api/security.py`)
There are no cookies or sessions, so there is no ambient credential to steal. A hostile page could still make a visitor's browser create profiles or start expensive simulations. Every POST, PUT, PATCH or DELETE request must therefore have both:
1. an allow-listed `Origin`, or `Referer` if `Origin` is absent. The list is set by `GEOCROP_ALLOWED_ORIGINS` and defaults to the local dev server;
2. the header `X-GeoCrop-Client: web`.

A cross-site page can't add a custom header without a CORS preflight, and CORS only allows GeoCrop's origins, so plain HTML form posts fail too.
- **CORS** allows only `GET/POST/PUT/DELETE`, the `Content-Type` and `X-GeoCrop-Client` headers, and no credentials.
- **Response headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cross-Origin-Resource-Policy`.
- **Scripts and curl** calling write endpoints must send `-H "X-GeoCrop-Client: web"`.

## SSRF (`geocrop/common/safe_http.py`)
No API endpoint fetches a user-supplied URL. The data-download jobs do fetch URLs, some of them taken from third-party responses (for example the geoBoundaries API returns the file URL). Every outbound request goes through `safe_get` / `safe_request`, which enforces:
- https only;
- a host on the allow-list (`DATA_HOSTS`);
- no IP-literal URLs or embedded credentials;
- every resolved address must be public: no loopback, private, link-local (which covers cloud metadata), carrier-grade NAT or reserved ranges;
- redirects followed manually and re-checked at every hop.

A test fails if any file makes a direct `requests`, `urllib` or `httpx` call.

**Limits:** the address check happens at resolution time, and requests resolves again on connect, so a hostile DNS server could swap the answer between the two. The host allow-list is the primary control. The ECMWF client library makes its own requests to a fixed host.

## Setup (once per database)

```bash
.venv/Scripts/python scripts/db/create_app_role.py   # creates geocrop_app, writes its password to .env (never printed)
```

## Not covered here
- **Profiles have no login.** The profile UUID acts as a bearer secret: it's stored in localStorage and appears in URLs and server logs. Before exposing GeoCrop beyond localhost, add real authentication (OTP to phone, for example) and serve over HTTPS.
- **Rate limiting** isn't implemented. The simulator and diagnose endpoints are CPU-heavy.
- **Dependencies:** `npm audit` reports a high-severity open-redirect advisory in the installed React Router version; a patch release fixes it.
