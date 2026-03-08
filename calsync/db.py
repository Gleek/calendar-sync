import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendars (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    description TEXT,
    time_zone TEXT,
    color TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT NOT NULL,
    calendar_id TEXT NOT NULL REFERENCES calendars(id),
    summary TEXT,
    description TEXT,
    location TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_minutes INTEGER,
    all_day INTEGER NOT NULL DEFAULT 0,
    recurring_event_id TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed',
    created TEXT,
    updated TEXT,
    PRIMARY KEY (id, calendar_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    calendar_id TEXT PRIMARY KEY REFERENCES calendars(id),
    sync_token TEXT,
    last_synced_at TEXT
);
"""


def get_db(path="calendar.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_calendar(conn, cal):
    conn.execute(
        """INSERT OR REPLACE INTO calendars (id, summary, description, time_zone, color)
           VALUES (:id, :summary, :description, :time_zone, :color)""",
        cal,
    )


def upsert_event(conn, event):
    conn.execute(
        """INSERT OR REPLACE INTO events
           (id, calendar_id, summary, description, location,
            start_time, end_time, duration_minutes, all_day,
            recurring_event_id, status, created, updated)
           VALUES (:id, :calendar_id, :summary, :description, :location,
                   :start_time, :end_time, :duration_minutes, :all_day,
                   :recurring_event_id, :status, :created, :updated)""",
        event,
    )


def delete_event(conn, event_id, calendar_id):
    conn.execute(
        "DELETE FROM events WHERE id = ? AND calendar_id = ?",
        (event_id, calendar_id),
    )


def delete_events_by_recurring_id(conn, recurring_event_id, calendar_id):
    conn.execute(
        "DELETE FROM events WHERE recurring_event_id = ? AND calendar_id = ?",
        (recurring_event_id, calendar_id),
    )


def get_sync_token(conn, calendar_id):
    row = conn.execute(
        "SELECT sync_token FROM sync_state WHERE calendar_id = ?",
        (calendar_id,),
    ).fetchone()
    return row["sync_token"] if row else None


def set_sync_token(conn, calendar_id, token):
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO sync_state (calendar_id, sync_token, last_synced_at)
           VALUES (?, ?, ?)""",
        (calendar_id, token, now),
    )


def get_all_events(conn):
    return conn.execute(
        """SELECT e.*, c.summary as calendar_name
           FROM events e
           JOIN calendars c ON e.calendar_id = c.id
           WHERE e.status = 'confirmed'
           ORDER BY e.start_time, e.end_time"""
    ).fetchall()
