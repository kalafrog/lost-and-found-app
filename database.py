"""
database.py
SQLite persistence layer for the Find & Reward prototype.

Tables:
    users          - simulated nearby users (stand-ins for real app installs)
    bounties       - lost item/pet posts with a paid broadcast radius
    claims         - "I found it" submissions from a user against a bounty
    escrow_ledger  - immutable record of every reward released (audit trail)

This is deliberately plain sqlite3 (stdlib) rather than an ORM, so the file
stays readable as a portfolio piece. A production build would swap this for
PostgreSQL + PostGIS behind a FastAPI service, but the table shapes and the
escrow flow below map directly onto that design.
"""

import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager

from geo_utils import find_users_in_radius, split_reward, random_point_within_radius

DB_PATH = Path(__file__).parent / "geo_bounty.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    reputation  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bounties (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    poster_name   TEXT NOT NULL,
    category      TEXT NOT NULL,          -- 'item' or 'pet'
    item_name     TEXT NOT NULL,
    description   TEXT,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    radius_km     REAL NOT NULL,
    reward_total  REAL NOT NULL,
    finder_pct    INTEGER NOT NULL DEFAULT 50,
    status        TEXT NOT NULL DEFAULT 'active',   -- active | resolved | cancelled
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bounty_id   INTEGER NOT NULL,
    finder_name TEXT NOT NULL,
    proof_note  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    claimed_at  TEXT NOT NULL,
    FOREIGN KEY (bounty_id) REFERENCES bounties (id)
);

CREATE TABLE IF NOT EXISTS escrow_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bounty_id       INTEGER NOT NULL,
    claim_id        INTEGER NOT NULL,
    finder_name     TEXT NOT NULL,
    finder_share    REAL NOT NULL,
    platform_share  REAL NOT NULL,
    released_at     TEXT NOT NULL,
    FOREIGN KEY (bounty_id) REFERENCES bounties (id),
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);
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


# ------------------------------------------------------------- bounties ----

def create_bounty(poster_name, category, item_name, description, lat, lon, radius_km, reward_total, finder_pct=50) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO bounties
               (poster_name, category, item_name, description, lat, lon, radius_km,
                reward_total, finder_pct, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (poster_name, category, item_name, description, lat, lon, radius_km,
             reward_total, finder_pct, _now()),
        )
        return cur.lastrowid


def get_bounties(status: str = None) -> list:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM bounties WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM bounties ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_bounty(bounty_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM bounties WHERE id = ?", (bounty_id,)).fetchone()
        return dict(row) if row else None


def cancel_bounty(bounty_id: int):
    with _connect() as conn:
        conn.execute("UPDATE bounties SET status = 'cancelled' WHERE id = ?", (bounty_id,))


def broadcast_targets(bounty_id: int) -> list:
    """Simulate the push-notification fan-out: which demo users fall inside the paid radius."""
    bounty = get_bounty(bounty_id)
    if not bounty:
        return []
    users = get_users()
    return find_users_in_radius(bounty["lat"], bounty["lon"], bounty["radius_km"], users)


# --------------------------------------------------------------- claims ----

def submit_claim(bounty_id: int, finder_name: str, proof_note: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO claims (bounty_id, finder_name, proof_note, status, claimed_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (bounty_id, finder_name, proof_note, _now()),
        )
        return cur.lastrowid


def get_claims(bounty_id: int = None) -> list:
    with _connect() as conn:
        if bounty_id is not None:
            rows = conn.execute(
                "SELECT * FROM claims WHERE bounty_id = ? ORDER BY claimed_at DESC", (bounty_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM claims ORDER BY claimed_at DESC").fetchall()
        return [dict(r) for r in rows]


def approve_claim(claim_id: int) -> dict:
    """
    Approve a claim: release escrow, split the reward, mark the bounty resolved,
    and reject any other pending claims on the same bounty. Returns the ledger row.
    """
    with _connect() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not claim:
            raise ValueError("Claim not found")
        bounty = conn.execute("SELECT * FROM bounties WHERE id = ?", (claim["bounty_id"],)).fetchone()
        if not bounty:
            raise ValueError("Bounty not found")
        if bounty["status"] != "active":
            raise ValueError("Bounty is no longer active")

        finder_share, platform_share = split_reward(bounty["reward_total"], bounty["finder_pct"])

        conn.execute("UPDATE claims SET status = 'approved' WHERE id = ?", (claim_id,))
        conn.execute(
            "UPDATE claims SET status = 'rejected' WHERE bounty_id = ? AND id != ? AND status = 'pending'",
            (bounty["id"], claim_id),
        )
        conn.execute("UPDATE bounties SET status = 'resolved' WHERE id = ?", (bounty["id"],))
        conn.execute(
            "UPDATE users SET reputation = reputation + 1 WHERE name = ?",
            (claim["finder_name"],),
        )

        released_at = _now()
        conn.execute(
            """INSERT INTO escrow_ledger
               (bounty_id, claim_id, finder_name, finder_share, platform_share, released_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bounty["id"], claim_id, claim["finder_name"], finder_share, platform_share, released_at),
        )

        return {
            "bounty_id": bounty["id"],
            "finder_name": claim["finder_name"],
            "finder_share": finder_share,
            "platform_share": platform_share,
            "released_at": released_at,
        }


def reject_claim(claim_id: int):
    with _connect() as conn:
        conn.execute("UPDATE claims SET status = 'rejected' WHERE id = ?", (claim_id,))


# --------------------------------------------------------------- ledger ----

def get_ledger() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM escrow_ledger ORDER BY released_at DESC").fetchall()
        return [dict(r) for r in rows]


def reset_all():
    """Wipe every table -- used by the 'Reset demo data' button in the UI."""
    with _connect() as conn:
        for table in ("escrow_ledger", "claims", "bounties", "users"):
            conn.execute(f"DELETE FROM {table}")
