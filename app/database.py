import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "diary.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            breed_guess TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            UNIQUE (user_id, name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dog_id INTEGER NOT NULL,
            photo_path TEXT NOT NULL,
            diary_text TEXT,
            ai_provider TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dog_id) REFERENCES dogs (id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


# ---------- users ----------

def create_user(username: str, password_hash: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_username(username: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


# ---------- dogs ----------

def get_or_create_dog(user_id: int, name: str, breed_guess: str | None = None) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM dogs WHERE user_id = ? AND name = ?", (user_id, name)
    ).fetchone()
    if row:
        dog_id = row["id"]
        if breed_guess:
            conn.execute("UPDATE dogs SET breed_guess = ? WHERE id = ?", (breed_guess, dog_id))
            conn.commit()
    else:
        cur = conn.execute(
            "INSERT INTO dogs (user_id, name, breed_guess) VALUES (?, ?, ?)",
            (user_id, name, breed_guess),
        )
        conn.commit()
        dog_id = cur.lastrowid
    conn.close()
    return dog_id


def list_dogs(user_id: int):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT dogs.id, dogs.name, dogs.breed_guess, COUNT(entries.id) as photo_count
        FROM dogs
        LEFT JOIN entries ON entries.dog_id = dogs.id
        WHERE dogs.user_id = ?
        GROUP BY dogs.id
        ORDER BY dogs.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_dog(user_id: int, dog_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM dogs WHERE id = ? AND user_id = ?", (dog_id, user_id)
    ).fetchone()
    conn.close()
    return row


def update_dog(user_id: int, dog_id: int, name: str, breed_guess: str | None):
    conn = get_conn()
    conn.execute(
        "UPDATE dogs SET name = ?, breed_guess = ? WHERE id = ? AND user_id = ?",
        (name, breed_guess, dog_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_dog(user_id: int, dog_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM dogs WHERE id = ? AND user_id = ?", (dog_id, user_id))
    conn.commit()
    conn.close()


# ---------- entries ----------

def add_entry(dog_id: int, photo_path: str, diary_text: str, ai_provider: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO entries (dog_id, photo_path, diary_text, ai_provider) VALUES (?, ?, ?, ?)",
        (dog_id, photo_path, diary_text, ai_provider),
    )
    conn.commit()
    conn.close()


def list_entries_for_dog(dog_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM entries WHERE dog_id = ? ORDER BY created_at DESC",
        (dog_id,),
    ).fetchall()
    conn.close()
    return rows


def get_entry(entry_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    return row


def delete_entry(entry_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
