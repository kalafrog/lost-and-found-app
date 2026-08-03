"""
database.py
SQLite persistence layer for the Find & Broadcast prototype.

Tables:
    users        - simulated nearby users (stand-ins for real app installs)
    requests     - lost item/pet search requests with a paid broadcast radius
    claims       - "I found it" submissions from a user against a request
    fee_ledger   - immutable record of every broadcast fee charged (audit trail)

There is no bounty/reward amount anywhere in this schema. The poster pays a
flat per-kilometer fee to broadcast their search radius; that fee is the
platform's entire revenue, charged the moment the request is posted. Finders
are never paid -- resolving a request just closes it out and gives the
finder a reputation point.

This is deliberately plain sqlite3 (stdlib) rather than an ORM, so the file
stays readable as a portfolio piece. A production build would swap this for
PostgreSQL + PostGIS behind a FastAPI service, but the table shapes and the
fee flow below map directly onto that design.
"""

import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager

from geo_utils import find_users_in_radius, calculate_broadcast_fee, random_point_within_radius, RATE_PER_KM

DB_PATH = Path(__file__).parent / "geo_bounty.db"

SCHEMA = """
         CREATE TABLE IF NOT EXISTS users (
                                              id          INTEGER PRIMARY KEY AUTOINCREMENT,
                                              name        TEXT NOT NULL,
                                              lat         REAL NOT NULL,
                                              lon         REAL NOT NULL,
                                              reputation  INTEGER NOT NULL DEFAULT 0
         );

         CREATE TABLE IF NOT EXISTS requests (
                                                 id            INTEGER PRIMARY KEY AUTOINCREMENT,
                                                 poster_name   TEXT NOT NULL,
                                                 category      TEXT NOT NULL,          -- 'item' or 'pet'
                                                 item_name     TEXT NOT NULL,
                                                 description   TEXT,
                                                 lat           REAL NOT NULL,
                                                 lon           REAL NOT NULL,
                                                 radius_km     REAL NOT NULL,
                                                 rate_per_km   REAL NOT NULL,
                                                 broadcast_fee REAL NOT NULL,          -- radius_km * rate_per_km, charged up front
                                                 status        TEXT NOT NULL DEFAULT 'active',   -- active | resolved | cancelled
                                                 created_at    TEXT NOT NULL
         );

         CREATE TABLE IF NOT EXISTS claims (
                                               id          INTEGER PRIMARY KEY AUTOINCREMENT,
                                               request_id  INTEGER NOT NULL,
                                               finder_name TEXT NOT NULL,
                                               proof_note  TEXT,
                                               status      TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
                                               claimed_at  TEXT NOT NULL,
                                               FOREIGN KEY (request_id) REFERENCES requests (id)
             );

         CREATE TABLE IF NOT EXISTS fee_ledger (
                                                   id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                                   request_id      INTEGER NOT NULL,
                                                   poster_name     TEXT NOT NULL,
                                                   radius_km       REAL NOT NULL,
                                                   rate_per_km     REAL NOT NULL,
                                                   broadcast_fee   REAL NOT NULL,
                                                   charged_at      TEXT NOT NULL,
                                                   FOREIGN KEY (request_id) REFERENCES requests (id)
             ); \
         """


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ---------------------------------------------------------------- users ----

def seed_demo_users(center_lat: float, center_lon: float, count: int = 25, spread_km: float = 6.0, rng=None):
    """Populate the users table with randomly scattered demo accounts, once."""
    with _connect() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if existing > 0:
            return
        first_names = [
            "Aisha", "Rohan", "Priya", "Kabir", "Meera", "Arjun", "Sana", "Dev",
            "Neha", "Vikram", "Isha", "Farhan", "Tanvi", "Aman", "Riya", "Yusuf",
            "Ananya", "Karan", "Zoya", "Nikhil", "Divya", "Rahul", "Simran", "Omar", "Pooja",
        ]
        for i in range(count):
            lat, lon = random_point_within_radius(center_lat, center_lon, spread_km, rng=rng)
            name = first_names[i % len(first_names)]
            conn.execute(
                "INSERT INTO users (name, lat, lon, reputation) VALUES (?, ?, ?, ?)",
                (name, lat, lon, 0),
            )


def get_users() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------- requests ----

def create_request(poster_name, category, item_name, description, lat, lon, radius_km, rate_per_km=RATE_PER_KM) -> dict:
    """
    Create a search request and immediately charge the broadcast fee
    (radius_km * rate_per_km). Returns the created request as a dict.
    There is no reward/bounty amount -- the poster only pays for reach.
    """
    fee = calculate_broadcast_fee(radius_km, rate_per_km)
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO requests
               (poster_name, category, item_name, description, lat, lon, radius_km,
                rate_per_km, broadcast_fee, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (poster_name, category, item_name, description, lat, lon, radius_km,
             rate_per_km, fee, _now()),
        )
        request_id = cur.lastrowid
        conn.execute(
            """INSERT INTO fee_ledger
               (request_id, poster_name, radius_km, rate_per_km, broadcast_fee, charged_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (request_id, poster_name, radius_km, rate_per_km, fee, _now()),
        )
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row)


def get_requests(status: str = None) -> list:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM requests WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM requests ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_request(request_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None


def cancel_request(request_id: int):
    with _connect() as conn:
        conn.execute("UPDATE requests SET status = 'cancelled' WHERE id = ?", (request_id,))


def broadcast_targets(request_id: int) -> list:
    """Simulate the push-notification fan-out: which demo users fall inside the paid radius."""
    request = get_request(request_id)
    if not request:
        return []
    users = get_users()
    return find_users_in_radius(request["lat"], request["lon"], request["radius_km"], users)


# --------------------------------------------------------------- claims ----

def submit_claim(request_id: int, finder_name: str, proof_note: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO claims (request_id, finder_name, proof_note, status, claimed_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (request_id, finder_name, proof_note, _now()),
        )
        return cur.lastrowid


def get_claims(request_id: int = None) -> list:
    with _connect() as conn:
        if request_id is not None:
            rows = conn.execute(
                "SELECT * FROM claims WHERE request_id = ? ORDER BY claimed_at DESC", (request_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM claims ORDER BY claimed_at DESC").fetchall()
        return [dict(r) for r in rows]


def approve_claim(claim_id: int) -> dict:
    """
    Approve a claim: mark the request resolved, credit the finder a reputation
    point, and reject any other pending claims on the same request. No money
    changes hands here -- the poster already paid their broadcast fee up
    front when the request was created.
    """
    with _connect() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not claim:
            raise ValueError("Claim not found")
        request = conn.execute("SELECT * FROM requests WHERE id = ?", (claim["request_id"],)).fetchone()
        if not request:
            raise ValueError("Request not found")
        if request["status"] != "active":
            raise ValueError("Request is no longer active")

        conn.execute("UPDATE claims SET status = 'approved' WHERE id = ?", (claim_id,))
        conn.execute(
            "UPDATE claims SET status = 'rejected' WHERE request_id = ? AND id != ? AND status = 'pending'",
            (request["id"], claim_id),
        )
        conn.execute("UPDATE requests SET status = 'resolved' WHERE id = ?", (request["id"],))
        conn.execute(
            "UPDATE users SET reputation = reputation + 1 WHERE name = ?",
            (claim["finder_name"],),
        )

        return {
            "request_id": request["id"],
            "finder_name": claim["finder_name"],
            "resolved_at": _now(),
        }


def reject_claim(claim_id: int):
    with _connect() as conn:
        conn.execute("UPDATE claims SET status = 'rejected' WHERE id = ?", (claim_id,))


# --------------------------------------------------------------- ledger ----

def get_ledger() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM fee_ledger ORDER BY charged_at DESC").fetchall()
        return [dict(r) for r in rows]


def reset_all():
    """Wipe every table -- used by the 'Reset demo data' button in the UI."""
    with _connect() as conn:
        for table in ("fee_ledger", "claims", "requests", "users"):
            conn.execute(f"DELETE FROM {table}")