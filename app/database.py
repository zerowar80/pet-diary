import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "diary.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            breed_guess TEXT,
            created_at TEXT DEFAULT (datetime('now'))
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
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dog_id) REFERENCES dogs (id)
        )
        """
    )
    conn.commit()
    conn.close()


def get_or_create_dog(name: str, breed_guess: str | None = None) -> int:
    conn = get_conn()
    row = conn.execute("SELECT id FROM dogs WHERE name = ?", (name,)).fetchone()
    if row:
        dog_id = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO dogs (name, breed_guess) VALUES (?, ?)", (name, breed_guess)
        )
        conn.commit()
        dog_id = cur.lastrowid
    conn.close()
    return dog_id


def add_entry(dog_id: int, photo_path: str, diary_text: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO entries (dog_id, photo_path, diary_text) VALUES (?, ?, ?)",
        (dog_id, photo_path, diary_text),
    )
    conn.commit()
    conn.close()


def list_dogs():
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT dogs.id, dogs.name, dogs.breed_guess, COUNT(entries.id) as photo_count
        FROM dogs
        LEFT JOIN entries ON entries.dog_id = dogs.id
        GROUP BY dogs.id
        ORDER BY dogs.created_at DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_dog_by_name(name: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM dogs WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row


def list_entries_for_dog(dog_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM entries WHERE dog_id = ? ORDER BY created_at DESC",
        (dog_id,),
    ).fetchall()
    conn.close()
    return rows
