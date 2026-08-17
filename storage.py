"""
Module for local storage and tracking of processed emails and drafts.
"""
import sqlite3
import json
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = 'agent_data.db'

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize database tables."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_emails (
                id TEXT PRIMARY KEY,
                subject TEXT,
                processed_date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                title TEXT,
                content_json TEXT,
                status TEXT DEFAULT 'draft'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS published_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                title TEXT,
                sharepoint_url TEXT,
                published_date TEXT
            )
        ''')
        conn.commit()
    logger.info("Database initialized.")

def is_email_processed(email_id: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM processed_emails WHERE id = ?", (email_id,))
        return cursor.fetchone() is not None

def mark_email_processed(email_id: str, subject: str):
    date_str = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_emails (id, subject, processed_date) VALUES (?, ?, ?)",
            (email_id, subject, date_str)
        )
        conn.commit()

def save_draft(date: str, title: str, content_json: str) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO drafts (date, title, content_json, status) VALUES (?, ?, ?, 'draft')",
            (date, title, content_json)
        )
        conn.commit()
        return cursor.lastrowid

def get_latest_draft() -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None

def get_draft_by_id(draft_id: int) -> dict | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
        
def get_today_draft() -> dict | None:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts WHERE date = ? AND status = 'draft' ORDER BY id DESC LIMIT 1", (today,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_draft(draft_id: int, title: str, content_json: str):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE drafts SET title = ?, content_json = ? WHERE id = ?",
            (title, content_json, draft_id)
        )
        conn.commit()

def mark_draft_published(draft_id: int):
    with get_db_connection() as conn:
        conn.execute("UPDATE drafts SET status = 'published' WHERE id = ?", (draft_id,))
        conn.commit()

def save_published_post(date: str, title: str, sharepoint_url: str):
    pub_date = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO published_posts (date, title, sharepoint_url, published_date) VALUES (?, ?, ?, ?)",
            (date, title, sharepoint_url, pub_date)
        )
        conn.commit()

def get_published_posts() -> list[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM published_posts ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]

# Initialize db on module load
init_db()
