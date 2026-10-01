"""
db.py - a very small database layer.
Works with SQLite (default, no setup) and PostgreSQL (set DATABASE_URL in .env).
"""
import sqlite3
import threading
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, url: str):
        self.lock = threading.RLock()
        self.is_pg = url.startswith("postgres")
        if self.is_pg:
            import psycopg2
            import psycopg2.extras
            self._extras = psycopg2.extras
            self.conn = psycopg2.connect(url)
            self.kind = "PostgreSQL"
        else:
            path = url.replace("sqlite:///", "", 1)
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.kind = "SQLite"

    def _cursor(self):
        if self.is_pg:
            return self.conn.cursor(cursor_factory=self._extras.RealDictCursor)
        return self.conn.cursor()

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.is_pg else sql

    def execute(self, sql, params=()):
        with self.lock:
            cur = self._cursor()
            try:
                cur.execute(self._sql(sql), params)
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return cur

    def query(self, sql, params=()):
        with self.lock:
            cur = self._cursor()
            try:
                cur.execute(self._sql(sql), params)
                rows = cur.fetchall()
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return [dict(r) for r in rows]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, sql, params=()):
        """Run an INSERT and return the new row id."""
        with self.lock:
            cur = self._cursor()
            try:
                if self.is_pg:
                    cur.execute(self._sql(sql) + " RETURNING id", params)
                    new_id = cur.fetchone()["id"]
                else:
                    cur.execute(sql, params)
                    new_id = cur.lastrowid
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            return new_id

    def create_tables(self):
        pk = "SERIAL PRIMARY KEY" if self.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        ddl = [
            f"""CREATE TABLE IF NOT EXISTS users (
                id {pk}, username TEXT UNIQUE NOT NULL, full_name TEXT, password_hash TEXT NOT NULL,
                role TEXT NOT NULL, active INTEGER DEFAULT 1, created_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS categories (
                id {pk}, name TEXT UNIQUE NOT NULL, active INTEGER DEFAULT 1, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS documents (
                id {pk}, filename TEXT, stored_name TEXT, file_type TEXT, text TEXT,
                predicted_category TEXT, confidence REAL, final_category TEXT, status TEXT,
                ocr_method TEXT, ocr_confidence REAL, explanation_json TEXT,
                uploaded_by TEXT, created_at TEXT, saved_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS chunks (
                id {pk}, document_id INTEGER NOT NULL, chunk_index INTEGER, text TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS audit_logs (
                id {pk}, username TEXT, action TEXT, detail TEXT, created_at TEXT)""",
        ]
        for stmt in ddl:
            self.execute(stmt)
