"""Create (or refresh) the least-privilege database login the API runs as.

The API used to connect as the superuser that owns the database. If a SQL injection bug were ever introduced, a
superuser could read or drop everything and even run operating-system commands (COPY ... PROGRAM). The app role:
  * can only SELECT/INSERT/UPDATE/DELETE rows in the profile tables (no CREATE/ALTER/DROP, no other schemas);
  * cannot create roles or databases, is not a superuser;
  * has statement_timeout 5 s and idle_in_transaction_session_timeout 30 s (limits abuse of slow queries).
Its random password is written to .env (GEOCROP_DB_APP_USER / GEOCROP_DB_APP_PASSWORD) and never printed.

Run as the admin (owner) login from .env:   python scripts/db/create_app_role.py
Re-running is safe: it re-applies grants and only generates a password when the role is new (or with --rotate).
"""
import argparse
import os
import re
import secrets
import sys
from pathlib import Path

from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from geocrop.db import Base, admin_engine  # noqa: E402

ROLE = "geocrop_app"
ENV = ROOT / ".env"


def _set_env(key, value):
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    line = f"{key}={value}"
    text = re.sub(rf"(?m)^{key}=.*$", line, text) if re.search(rf"(?m)^{key}=", text) else text.rstrip("\n") + f"\n{line}\n"
    ENV.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotate", action="store_true", help="generate a new password even if the role exists")
    a = ap.parse_args()
    eng = admin_engine()
    Base.metadata.create_all(eng)  # tables are owned by the admin login
    db = os.environ.get("GEOCROP_DB_NAME", "geocrop")
    tables = list(Base.metadata.tables)
    with eng.begin() as c:
        raw = c.connection.driver_connection
        with raw.cursor() as cur:
            cur.execute("select 1 from pg_roles where rolname = %s", (ROLE,))
            exists = cur.fetchone() is not None
            pw = None
            if not exists or a.rotate:
                pw = secrets.token_urlsafe(32)
                stmt = "ALTER ROLE {} WITH LOGIN PASSWORD {}" if exists else "CREATE ROLE {} WITH LOGIN PASSWORD {}"
                cur.execute(sql.SQL(stmt).format(sql.Identifier(ROLE), sql.Literal(pw)))
            cur.execute(sql.SQL("ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '30s'").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(ROLE)))
            cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cur.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(ROLE)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
            for t in tables:
                cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {} TO {}").format(sql.Identifier(t), sql.Identifier(ROLE)))
    if pw:
        _set_env("GEOCROP_DB_APP_USER", ROLE)
        _set_env("GEOCROP_DB_APP_PASSWORD", pw)
    print(f"role {ROLE}: {'created' if not exists else ('password rotated' if pw else 'grants refreshed')}; "
          f"DML on {len(tables)} tables; credentials {'written to' if pw else 'unchanged in'} .env")


if __name__ == "__main__":
    main()
