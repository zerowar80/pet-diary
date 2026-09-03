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
            weather_icon TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dog_id) REFERENCES dogs (id) ON DELETE CASCADE
        )
        """
    )
    # 기존에 만들어둔 DB(weather_icon 컬럼이 없는 이전 버전)를 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE entries ADD COLUMN weather_icon TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
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


def update_user_password(user_id: int, password_hash: str):
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    conn.close()


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


def dog_name_exists(user_id: int, name: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM dogs WHERE user_id = ? AND name = ?", (user_id, name)
    ).fetchone()
    conn.close()
    return row is not None


def create_dog(user_id: int, name: str, breed_guess: str | None = None) -> int:
    conn = get_conn()
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

def add_entry(dog_id: int, photo_path: str, diary_text: str, ai_provider: str, weather_icon: str | None = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO entries (dog_id, photo_path, diary_text, ai_provider, weather_icon) VALUES (?, ?, ?, ?, ?)",
        (dog_id, photo_path, diary_text, ai_provider, weather_icon),
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


def get_first_entry_photo(dog_id: int):
    """얼굴 인식용 대표 사진(가장 처음 올린 사진 경로)을 반환합니다. 사진이 없으면 None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT photo_path FROM entries WHERE dog_id = ? ORDER BY created_at ASC LIMIT 1",
        (dog_id,),
    ).fetchone()
    conn.close()
    return row["photo_path"] if row else None


def list_available_months(dog_id: int):
    """해당 반려견의 일기가 있는 연-월 목록을 최신순으로 반환합니다 (예: ['2026-09', '2026-08'])."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT DISTINCT substr(created_at, 1, 7) AS ym
        FROM entries
        WHERE dog_id = ?
        ORDER BY ym DESC
        """,
        (dog_id,),
    ).fetchall()
    conn.close()
    return [row["ym"] for row in rows]


def list_entries_for_dog_month(dog_id: int, year_month: str):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM entries
        WHERE dog_id = ? AND substr(created_at, 1, 7) = ?
        ORDER BY created_at ASC
        """,
        (dog_id, year_month),
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
