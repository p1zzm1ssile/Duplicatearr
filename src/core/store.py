"""Duplicatearr's database: what's been read from each file, and what's been removed."""

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS probes (
    path TEXT PRIMARY KEY, size INTEGER, mtime REAL, info TEXT
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL, original TEXT, recycled TEXT, size INTEGER, group_title TEXT,
    state TEXT,          -- recycled, restored, purged, deleted
    sidecars TEXT,       -- JSON [[original, recycled], ...] for subtitles and artwork moved with it
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ignored (
    group_id TEXT PRIMARY KEY, at REAL
);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)

    # Cached reads of a file, thrown away when the file changes

    def cached(self, path, size, mtime):
        with self.lock:
            row = self.db.execute("SELECT size, mtime, info FROM probes WHERE path = ?", (path,)).fetchone()
        if row and row["size"] == size and abs(row["mtime"] - mtime) < 1:
            return json.loads(row["info"])
        return {}

    def cache(self, path, size, mtime, info):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO probes VALUES (?, ?, ?, ?)", (path, size, mtime, json.dumps(info)))

    def forget_missing(self, keep_paths):
        keep = set(keep_paths)
        with self.lock, self.db:
            gone = [r[0] for r in self.db.execute("SELECT path FROM probes") if r[0] not in keep]
            self.db.executemany("DELETE FROM probes WHERE path = ?", [(p,) for p in gone])

    # Removed files

    def add_history(self, original, recycled, size, group_title, state, sidecars, note=""):
        with self.lock, self.db:
            return self.db.execute(
                "INSERT INTO history (at, original, recycled, size, group_title, state, sidecars, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), original, recycled, size, group_title, state, json.dumps(sidecars), note)).lastrowid

    def history(self, limit=200, offset=0):
        with self.lock:
            total = self.db.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            rows = self.db.execute("SELECT * FROM history ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return total, [{**dict(r), "sidecars": json.loads(r["sidecars"] or "[]")} for r in rows]

    def entry(self, history_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
        return {**dict(row), "sidecars": json.loads(row["sidecars"] or "[]")} if row else None

    def set_state(self, history_id, state, note=None):
        with self.lock, self.db:
            if note is None:
                self.db.execute("UPDATE history SET state = ? WHERE id = ?", (state, history_id))
            else:
                self.db.execute("UPDATE history SET state = ?, note = ? WHERE id = ?", (state, note, history_id))

    def recycled_before(self, cutoff):
        with self.lock:
            rows = self.db.execute("SELECT * FROM history WHERE state = 'recycled' AND at < ?", (cutoff,)).fetchall()
        return [{**dict(r), "sidecars": json.loads(r["sidecars"] or "[]")} for r in rows]

    def reclaimed(self):
        with self.lock:
            return self.db.execute(
                "SELECT COALESCE(SUM(size), 0) FROM history WHERE state IN ('recycled', 'purged', 'deleted')").fetchone()[0]

    # Groups marked "not duplicates"

    def ignored(self):
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT group_id FROM ignored")}

    def set_ignored(self, group_id, ignored):
        with self.lock, self.db:
            if ignored:
                self.db.execute("INSERT OR REPLACE INTO ignored VALUES (?, ?)", (group_id, time.time()))
            else:
                self.db.execute("DELETE FROM ignored WHERE group_id = ?", (group_id,))
