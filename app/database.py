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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entry_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            photo_path TEXT NOT NULL,
            media_type TEXT DEFAULT 'photo',
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (entry_id) REFERENCES entries (id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entry_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(entry_id, user_id),
            FOREIGN KEY (entry_id) REFERENCES entries (id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entry_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (entry_id) REFERENCES entries (id) ON DELETE CASCADE
        )
        """
    )
    # 기존에 만들어둔 DB(weather_icon 컬럼이 없는 이전 버전)를 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE entries ADD COLUMN weather_icon TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # 기존에 만들어둔 DB(is_admin 컬럼이 없는 이전 버전)를 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # 공지사항 '새 글' 배지를 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE users ADD COLUMN notices_last_seen_at TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # 반려견 프로필 사진을 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE dogs ADD COLUMN profile_photo TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # 댓글 알림(강아지 카드 배지)을 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE dogs ADD COLUMN comments_last_seen_at TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    try:
        conn.execute("ALTER TABLE users ADD COLUMN comment_notifications_enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # 기존에 만들어둔 DB(media_type 컬럼이 없는 이전 버전)를 위한 마이그레이션
    try:
        conn.execute("ALTER TABLE entry_photos ADD COLUMN media_type TEXT DEFAULT 'photo'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 있으면 무시
    # entry_photos 테이블이 새로 생긴 경우, 기존 entries.photo_path를 채워넣습니다.
    conn.execute(
        """
        INSERT INTO entry_photos (entry_id, photo_path, sort_order)
        SELECT id, photo_path, 0 FROM entries
        WHERE id NOT IN (SELECT DISTINCT entry_id FROM entry_photos)
        """
    )
    conn.commit()
    conn.close()


def ensure_admin_exists():
    """관리자가 한 명도 없는데 사용자는 있다면, 가장 먼저 가입한 사용자를 관리자로 지정합니다.
    (is_admin 컬럼이 새로 추가된 기존 설치본을 위한 안전장치)"""
    conn = get_conn()
    admin_row = conn.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    if not admin_row:
        first_user = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
        if first_user:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (first_user["id"],))
            conn.commit()
    conn.close()


# ---------- users ----------

def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
        (username, password_hash, 1 if is_admin else 0),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def count_users() -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
    conn.close()
    return row["cnt"]


def get_admin_user():
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1").fetchone()
    conn.close()
    return row


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
        SELECT dogs.id, dogs.name, dogs.breed_guess, dogs.profile_photo, dogs.comments_last_seen_at,
               COUNT(entries.id) as photo_count
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


def set_dog_profile_photo(user_id: int, dog_id: int, photo_path: str | None):
    """photo_path가 None이면 프로필 사진을 지웁니다."""
    conn = get_conn()
    conn.execute(
        "UPDATE dogs SET profile_photo = ? WHERE id = ? AND user_id = ?",
        (photo_path, dog_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_dog(user_id: int, dog_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM dogs WHERE id = ? AND user_id = ?", (dog_id, user_id))
    conn.commit()
    conn.close()


# ---------- entries ----------

def add_entry(dog_id: int, photo_paths: list[str], diary_text: str, ai_provider: str, weather_icon: str | None = None, media_type: str = "photo") -> int:
    """photo_paths: 이 일기에 포함될 미디어 경로 목록 (1개여도 리스트로 전달). 첫 번째가 대표 미디어가 됩니다.
    media_type: 'photo' 또는 'video'. 한 일기 안의 미디어는 모두 같은 타입입니다."""
    conn = get_conn()
    cover_photo = photo_paths[0]
    cur = conn.execute(
        "INSERT INTO entries (dog_id, photo_path, diary_text, ai_provider, weather_icon) VALUES (?, ?, ?, ?, ?)",
        (dog_id, cover_photo, diary_text, ai_provider, weather_icon),
    )
    entry_id = cur.lastrowid
    for order, path in enumerate(photo_paths):
        conn.execute(
            "INSERT INTO entry_photos (entry_id, photo_path, media_type, sort_order) VALUES (?, ?, ?, ?)",
            (entry_id, path, media_type, order),
        )
    conn.commit()
    conn.close()
    return entry_id


def get_entry_photos(entry_id: int) -> list[dict]:
    """[{"id": ..., "path": ..., "media_type": "photo"|"video"}, ...] 목록을 정렬 순서대로 반환합니다."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, photo_path, media_type FROM entry_photos WHERE entry_id = ? ORDER BY sort_order ASC",
        (entry_id,),
    ).fetchall()
    conn.close()
    return [{"id": row["id"], "path": row["photo_path"], "media_type": row["media_type"] or "photo"} for row in rows]


def get_entry_photo_row(entry_photo_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM entry_photos WHERE id = ?", (entry_photo_id,)).fetchone()
    conn.close()
    return row


def count_entry_photos(entry_id: int) -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM entry_photos WHERE entry_id = ?", (entry_id,)).fetchone()
    conn.close()
    return row["cnt"]


def delete_entry_photo(entry_photo_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM entry_photos WHERE id = ?", (entry_photo_id,))
    conn.commit()
    conn.close()


def resync_entry_cover(entry_id: int):
    """entry_photos의 남은 첫 번째 항목으로 entries.photo_path(대표 사진)를 다시 맞춥니다."""
    conn = get_conn()
    row = conn.execute(
        "SELECT photo_path FROM entry_photos WHERE entry_id = ? ORDER BY sort_order ASC LIMIT 1",
        (entry_id,),
    ).fetchone()
    if row:
        conn.execute("UPDATE entries SET photo_path = ? WHERE id = ?", (row["photo_path"], entry_id))
        conn.commit()
    conn.close()


def add_entry_photos(entry_id: int, paths: list[str], media_type: str = "photo"):
    """기존 일기에 사진/동영상을 추가로 덧붙입니다."""
    conn = get_conn()
    row = conn.execute("SELECT MAX(sort_order) as m FROM entry_photos WHERE entry_id = ?", (entry_id,)).fetchone()
    start = (row["m"] + 1) if row and row["m"] is not None else 0
    for i, path in enumerate(paths):
        conn.execute(
            "INSERT INTO entry_photos (entry_id, photo_path, media_type, sort_order) VALUES (?, ?, ?, ?)",
            (entry_id, path, media_type, start + i),
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
    """얼굴 인식용 대표 사진(가장 처음 올린 '사진' 경로, 동영상은 제외)을 반환합니다. 없으면 None."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT ep.photo_path FROM entries e
        JOIN entry_photos ep ON ep.entry_id = e.id AND ep.sort_order = 0
        WHERE e.dog_id = ? AND (ep.media_type IS NULL OR ep.media_type = 'photo')
        ORDER BY e.created_at ASC LIMIT 1
        """,
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


# ---------- settings ----------

def get_setting(key: str):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


# ---------- 로그인 기록 ----------

def add_login_record(user_id: int, username: str, ip_address: str, user_agent: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO login_history (user_id, username, ip_address, user_agent) VALUES (?, ?, ?, ?)",
        (user_id, username, ip_address, user_agent),
    )
    conn.commit()
    conn.close()


def list_login_history(limit: int = 100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM login_history ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


# ---------- 공지사항 ----------

def create_notice(title: str, content: str, author: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO notices (title, content, author) VALUES (?, ?, ?)",
        (title, content, author),
    )
    conn.commit()
    notice_id = cur.lastrowid
    conn.close()
    return notice_id


def list_notices():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def get_notice(notice_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    conn.close()
    return row


def update_notice(notice_id: int, title: str, content: str):
    conn = get_conn()
    conn.execute(
        "UPDATE notices SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?",
        (title, content, notice_id),
    )
    conn.commit()
    conn.close()


def delete_notice(notice_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()


def get_latest_notice_created_at():
    conn = get_conn()
    row = conn.execute("SELECT MAX(created_at) as latest FROM notices").fetchone()
    conn.close()
    return row["latest"] if row else None


def get_latest_notice():
    conn = get_conn()
    row = conn.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return row


def get_notices_last_seen(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT notices_last_seen_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row["notices_last_seen_at"] if row else None


def update_notices_last_seen(user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET notices_last_seen_at = datetime('now') WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()


# ---------- 반응(이모지) ----------

def toggle_reaction(entry_id: int, user_id: int, emoji: str):
    """같은 이모지를 다시 누르면 취소, 다른 이모지를 누르면 바꿉니다 (한 사람당 한 반응)."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT emoji FROM entry_reactions WHERE entry_id = ? AND user_id = ?", (entry_id, user_id)
    ).fetchone()
    if existing and existing["emoji"] == emoji:
        conn.execute(
            "DELETE FROM entry_reactions WHERE entry_id = ? AND user_id = ?", (entry_id, user_id)
        )
    else:
        conn.execute(
            "INSERT INTO entry_reactions (entry_id, user_id, emoji) VALUES (?, ?, ?) "
            "ON CONFLICT(entry_id, user_id) DO UPDATE SET emoji = excluded.emoji, created_at = datetime('now')",
            (entry_id, user_id, emoji),
        )
    conn.commit()
    conn.close()


def get_reaction_summary(entry_id: int) -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT emoji, COUNT(*) as cnt FROM entry_reactions WHERE entry_id = ? GROUP BY emoji",
        (entry_id,),
    ).fetchall()
    conn.close()
    return {row["emoji"]: row["cnt"] for row in rows}


def get_user_reaction(entry_id: int, user_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT emoji FROM entry_reactions WHERE entry_id = ? AND user_id = ?", (entry_id, user_id)
    ).fetchone()
    conn.close()
    return row["emoji"] if row else None


# ---------- 댓글 ----------

def add_comment(entry_id: int, user_id: int, username: str, content: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO entry_comments (entry_id, user_id, username, content) VALUES (?, ?, ?, ?)",
        (entry_id, user_id, username, content),
    )
    conn.commit()
    comment_id = cur.lastrowid
    conn.close()
    return comment_id


def list_comments(entry_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM entry_comments WHERE entry_id = ? ORDER BY created_at ASC", (entry_id,)
    ).fetchall()
    conn.close()
    return rows


def get_comment(comment_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM entry_comments WHERE id = ?", (comment_id,)).fetchone()
    conn.close()
    return row


def delete_comment(comment_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM entry_comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()


# ---------- 댓글 알림 (강아지 카드 배지) ----------

def get_latest_comment_at(dog_id: int):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT MAX(ec.created_at) as latest
        FROM entry_comments ec
        JOIN entries e ON e.id = ec.entry_id
        WHERE e.dog_id = ?
        """,
        (dog_id,),
    ).fetchone()
    conn.close()
    return row["latest"] if row else None


def update_dog_comments_seen(dog_id: int):
    conn = get_conn()
    conn.execute("UPDATE dogs SET comments_last_seen_at = datetime('now') WHERE id = ?", (dog_id,))
    conn.commit()
    conn.close()


def get_comment_notifications_enabled(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT comment_notifications_enabled FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None or row["comment_notifications_enabled"] is None:
        return True
    return bool(row["comment_notifications_enabled"])


def set_comment_notifications_enabled(user_id: int, enabled: bool):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET comment_notifications_enabled = ? WHERE id = ?",
        (1 if enabled else 0, user_id),
    )
    conn.commit()
    conn.close()
