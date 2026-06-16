Save as `habit_tracker.py`. Optional dependencies: `pip install bcrypt matplotlib` — the script still runs without them using secure PBKDF2 hashing and an ASCII chart fallback.

```python
#!/usr/bin/env python3
"""
Daily Habit Tracker CLI

A fully functional single-file command-line habit tracker with:
- User registration/login/logout
- Secure password hashing: bcrypt when available, otherwise PBKDF2-HMAC-SHA256
- SQLite relational database storage
- Habit CRUD
- Daily habit logging
- Progress summaries
- Matplotlib chart generation with ASCII fallback

Optional:
    pip install bcrypt matplotlib

Usage examples:
    python habit_tracker.py init-db
    python habit_tracker.py register alice
    python habit_tracker.py login alice
    python habit_tracker.py habits add "Drink water" --type daily
    python habit_tracker.py logs add 1 --status completed
    python habit_tracker.py progress summary
    python habit_tracker.py progress chart --days 30
"""

import argparse
import getpass
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union


try:
    import bcrypt  # type: ignore
except Exception:
    bcrypt = None


HABIT_TYPES = ("daily", "weekly", "monthly")
LOG_STATUSES = ("completed", "missed", "skipped")
PASSWORD_ITERATIONS = 390_000
SCHEMA_VERSION = "1"


def resolve_default_path(env_var: str, filename: str) -> Path:
    """Resolve a default path from an environment variable or user home."""
    raw_path = os.environ.get(env_var)
    if raw_path:
        return Path(raw_path).expanduser()

    try:
        base = Path.home()
    except RuntimeError:
        base = Path(tempfile.gettempdir())

    return base / ".habit_tracker" / filename


DEFAULT_DB_PATH = resolve_default_path("HABIT_TRACKER_DB", "habits.db")
DEFAULT_SESSION_PATH = resolve_default_path("HABIT_TRACKER_SESSION", "session.json")


class HabitTrackerError(Exception):
    """Base application error."""

    exit_code = 1


class AuthenticationError(HabitTrackerError):
    """Authentication/session error."""

    exit_code = 2


class ValidationError(HabitTrackerError):
    """Input validation error."""

    exit_code = 3


class NotFoundError(HabitTrackerError):
    """Requested resource was not found."""

    exit_code = 4


class DatabaseError(HabitTrackerError):
    """Database error."""

    exit_code = 1


class PasswordHasher:
    """Secure password hashing/verification helper.

    Uses bcrypt when installed. If bcrypt is unavailable, falls back to
    PBKDF2-HMAC-SHA256 with a random salt so the script remains functional.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        password_bytes = password.encode("utf-8")

        if bcrypt is not None:
            try:
                return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")
            except Exception as exc:
                raise RuntimeError(f"bcrypt hashing failed: {exc}") from exc

        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password_bytes,
            salt,
            PASSWORD_ITERATIONS,
            dklen=64,
        )
        return f"$pbkdf2-sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        if not isinstance(password_hash, str) or not password_hash:
            return False

        if password_hash.startswith("$pbkdf2-sha256$"):
            parts = password_hash.split("$")
            if len(parts) != 5:
                return False

            _, algorithm, iterations_text, salt_hex, expected_digest = parts
            if algorithm != "pbkdf2-sha256":
                return False

            try:
                iterations = int(iterations_text)
                salt = bytes.fromhex(salt_hex)
            except ValueError:
                return False

            actual_digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
                dklen=64,
            ).hex()

            return actual_digest == expected_digest

        if bcrypt is not None:
            try:
                return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
            except (TypeError, ValueError):
                return False

        raise RuntimeError("This password hash requires bcrypt, but bcrypt is not installed.")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def expand_path(path_value: Union[str, Path]) -> Path:
    return Path(path_value).expanduser()


def ensure_parent_directory(path: Path, label: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatabaseError(f"Cannot create {label} directory '{path.parent}': {exc}") from exc


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def today_iso() -> str:
    return date.today().isoformat()


def format_optional_date(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


def format_streak(value: Optional[int]) -> str:
    return "-" if value is None else str(value)


def format_expected(value: Optional[int]) -> str:
    return "-" if value is None else str(value)


def truncate(text: Any, max_len: int) -> str:
    text = "" if text is None else str(text)

    if len(text) <= max_len:
        return text

    if max_len <= 0:
        return ""

    if max_len <= 3:
        return text[:max_len]

    return text[: max_len - 3] + "..."


def print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    rows_as_strings = [
        ["" if value is None else str(value) for value in row]
        for row in rows
    ]

    widths = [len(header) for header in headers]
    for row in rows_as_strings:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    lines = [
        " ".join(headers[index].ljust(widths[index]) for index in range(len(headers)))
    ]
    lines.append(" ".join("-" * width for width in widths))

    for row in rows_as_strings:
        padded_row = [
            (row[index] if index < len(row) else "").ljust(widths[index])
            for index in range(len(headers))
        ]
        lines.append(" ".join(padded_row))

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def normalize_username(username: str) -> str:
    if username is None:
        raise ValidationError("Username is required.")

    normalized = username.strip()

    if not normalized:
        raise ValidationError("Username is required.")

    if len(normalized) > 64:
        raise ValidationError("Username must be 64 characters or fewer.")

    if any(character.isspace() for character in normalized):
        raise ValidationError("Username cannot contain whitespace.")

    return normalized


def validate_text(value: Optional[str], field_name: str, min_len: int, max_len: int) -> str:
    text = "" if value is None else str(value).strip()

    if len(text) < min_len:
        raise ValidationError(f"{field_name} is required.")

    if len(text) > max_len:
        raise ValidationError(f"{field_name} must be {max_len} characters or fewer.")

    return text


def parse_date_value(value: Optional[str], field_name: str) -> date:
    if value is None:
        raise ValidationError(f"{field_name} is required.")

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must use YYYY-MM-DD format.") from None


def parse_optional_date_value(value: Optional[str], field_name: str) -> Optional[date]:
    if value is None:
        return None

    return parse_date_value(value, field_name)


def validate_date_range(start_date: date, end_date: Optional[date]) -> None:
    if end_date is not None and end_date < start_date:
        raise ValidationError("End date must be on or after start date.")


def validate_positive_int(value: int, field_name: str) -> int:
    if value < 1:
        raise ValidationError(f"{field_name} must be at least 1.")

    return value


def validate_limit(value: int, field_name: str = "limit") -> int:
    value = validate_positive_int(value, field_name)

    if value > 1000:
        raise ValidationError(f"{field_name} cannot exceed 1000.")

    return value


def validate_chart_days(value: int) -> int:
    value = validate_positive_int(value, "days")

    if value > 3650:
        raise ValidationError("days cannot exceed 3650.")

    return value


def prompt_password(confirm: bool = False) -> str:
    while True:
        try:
            password = getpass.getpass("Password: ")
        except EOFError:
            raise HabitTrackerError("Password input was interrupted.") from None

        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            continue

        if len(password) < 8:
            print("Password must be at least 8 characters.", file=sys.stderr)
            continue

        if confirm:
            try:
                confirmation = getpass.getpass("Confirm password: ")
            except EOFError:
                raise HabitTrackerError("Password confirmation was interrupted.") from None

            if confirmation != password:
                print("Passwords do not match.", file=sys.stderr)
                continue

        return password


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def write_session_file(session_path: Path, user_id: int, username: str) -> None:
    ensure_parent_directory(session_path, "session")

    data = {
        "user_id": int(user_id),
        "username": username,
        "logged_in_at": datetime.now(timezone.utc).isoformat(),
    }

    tmp_path = session_path.with_name(session_path.name + ".tmp")

    try:
        with tmp_path.open("w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, indent=2, sort_keys=True)
            file_obj.write("\n")

        # Best-effort permissions: session files should not be world-readable.
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass

        os.replace(tmp_path, session_path)
    except OSError as exc:
        raise AuthenticationError(f"Could not write session file '{session_path}': {exc}") from exc


def remove_session_file(session_path: Path) -> None:
    try:
        if session_path.exists():
            session_path.unlink()
    except OSError as exc:
        raise HabitTrackerError(f"Could not remove session file '{session_path}': {exc}") from exc


def load_session_file(session_path: Path) -> Dict[str, Any]:
    try:
        with session_path.open("r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except FileNotFoundError:
        raise AuthenticationError("No active session. Run 'login' first.") from None
    except json.JSONDecodeError as exc:
        raise AuthenticationError(f"Session file is corrupt: {exc}") from None
    except OSError as exc:
        raise AuthenticationError(f"Cannot read session file '{session_path}': {exc}") from None

    if not isinstance(data, dict):
        raise AuthenticationError("Session file is corrupt.")

    try:
        user_id = int(data["user_id"])
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError("Session file is missing a valid user_id.") from None

    username = data.get("username", "unknown")
    if not isinstance(username, str) or not username:
        username = "unknown"

    return {
        "user_id": user_id,
        "username": username,
    }


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO schema_info(key, value)
        VALUES ('version', '{SCHEMA_VERSION}');

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower
            ON users(lower(username));

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            habit_type TEXT NOT NULL CHECK (habit_type IN ('daily', 'weekly', 'monthly')),
            start_date TEXT NOT NULL,
            end_date TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            CHECK (end_date IS NULL OR end_date >= start_date)
        );

        CREATE INDEX IF NOT EXISTS idx_habits_user_id
            ON habits(user_id);

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('completed', 'missed', 'skipped')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE,
            UNIQUE(habit_id, log_date)
        );

        CREATE INDEX IF NOT EXISTS idx_habit_logs_habit_date
            ON habit_logs(habit_id, log_date);

        CREATE INDEX IF NOT EXISTS idx_habit_logs_date
            ON habit_logs(log_date);
        """
    )


@contextmanager
def database_connection(db_path: Union[str, Path]) -> Iterator[sqlite3.Connection]:
    path = expand_path(db_path)
    ensure_parent_directory(path, "database")

    conn = None

    try:
        conn = sqlite3.connect(str(path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        init_schema(conn)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise DatabaseError(f"Could not open or initialize database '{path}': {exc}") from exc

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def require_current_user(
    conn: sqlite3.Connection,
    session_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if session_path is None:
        session_path = expand_path(DEFAULT_SESSION_PATH)

    session = load_session_file(session_path)
    user_id = session["user_id"]

    row = conn.execute(
        "SELECT id, username FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        try:
            remove_session_file(session_path)
        except HabitTrackerError:
            pass

        raise AuthenticationError("The session user no longer exists. Run 'login' again.")

    return row_to_dict(row)


# ---------------------------------------------------------------------------
# Habit domain helpers
# ---------------------------------------------------------------------------


def get_habit_or_raise(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: int,
) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM habits
        WHERE id = ? AND user_id = ?
        """,
        (habit_id, user_id),
    ).fetchone()

    if row is None:
        raise NotFoundError(f"Habit {habit_id} not found.")

    return row_to_dict(row)


def create_habit(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    description: Optional[str],
    habit_type: str,
    start_date_text: str,
    end_date_text: Optional[str],
) -> int:
    name = validate_text(name, "name", 1, 100)
    description = validate_text(description, "description", 0, 500)

    if habit_type not in HABIT_TYPES:
        raise ValidationError(f"habit type must be one of: {', '.join(HABIT_TYPES)}")

    start_date = parse_date_value(start_date_text, "start_date")
    end_date = parse_optional_date_value(end_date_text, "end_date")
    validate_date_range(start_date, end_date)

    try:
        cursor = conn.execute(
            """
            INSERT INTO habits (
                user_id,
                name,
                description,
                habit_type,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                description,
                habit_type,
                start_date.isoformat(),
                end_date.isoformat() if end_date else None,
            ),
        )
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise DatabaseError(f"Could not create habit. Database constraint failed: {exc}") from exc


def update_habit(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: int,
    updates: Dict[str, Any],
) -> int:
    habit = get_habit_or_raise(conn, user_id, habit_id)

    if "name" in updates:
        updates["name"] = validate_text(updates["name"], "name", 1, 100)

    if "description" in updates:
        updates["description"] = validate_text(updates["description"], "description", 0, 500)

    if "habit_type" in updates and updates["habit_type"] not in HABIT_TYPES:
        raise ValidationError(f"habit type must be one of: {', '.join(HABIT_TYPES)}")

    current_start = parse_date_value(str(habit["start_date"]), "start_date")
    current_end = parse_optional_date_value(habit.get("end_date"), "end_date")

    new_start = updates.get("start_date", current_start)
    new_end = updates.get("end_date", current_end)

    if isinstance(new_start, str):
        new_start = parse_date_value(new_start, "start_date")

    if isinstance(new_end, str):
        new_end = parse_optional_date_value(new_end, "end_date")

    validate_date_range(new_start, new_end)

    if not updates:
        raise ValidationError("No update fields supplied.")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    assignments = [f"{column} = ?" for column in updates.keys()]
    params = list(updates.values()) + [habit_id, user_id]

    try:
        cursor = conn.execute(
            f"""
            UPDATE habits
            SET {', '.join(assignments)}
            WHERE id = ? AND user_id = ?
            """,
            params,
        )
        return int(cursor.rowcount)
    except sqlite3.IntegrityError as exc:
        raise DatabaseError(f"Could not update habit. Database constraint failed: {exc}") from exc


def delete_habit(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: int,
) -> int:
    get_habit_or_raise(conn, user_id, habit_id)

    cursor = conn.execute(
        """
        DELETE FROM habits
        WHERE id = ? AND user_id = ?
        """,
        (habit_id, user_id),
    )

    return int(cursor.rowcount)


def list_habits_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    active_only: bool = False,
    habit_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    where = ["h.user_id = ?"]
    params: List[Any] = [user_id]

    if active_only:
        where.append("(h.end_date IS NULL OR h.end_date >= date('now'))")

    if habit_type:
        where.append("h.habit_type = ?")
        params.append(habit_type)

    query = f"""
        SELECT
            h.*,
            COALESCE(s.total_logs, 0) AS total_logs,
            COALESCE(s.completed_logs, 0) AS completed_logs
        FROM habits h
        LEFT JOIN (
            SELECT
                habit_id,
                COUNT(*) AS total_logs,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_logs
            FROM habit_logs
            GROUP BY habit_id
        ) s ON s.habit_id = h.id
        WHERE {' AND '.join(where)}
        ORDER BY h.name COLLATE NOCASE, h.id
        LIMIT ?
    """

    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Habit log helpers
# ---------------------------------------------------------------------------


def upsert_habit_log(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: int,
    log_date: date,
    status: str,
) -> bool:
    """Create or update a habit log.

    Returns True if a new log was created, False if an existing log was updated.
    """
    get_habit_or_raise(conn, user_id, habit_id)

    if log_date > date.today():
        raise ValidationError("Log date cannot be in the future.")

    if status not in LOG_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(LOG_STATUSES)}")

    existing = conn.execute(
        """
        SELECT id
        FROM habit_logs
        WHERE habit_id = ? AND log_date = ?
        """,
        (habit_id, log_date.isoformat()),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE habit_logs
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, existing["id"]),
        )
        return False

    conn.execute(
        """
        INSERT INTO habit_logs (habit_id, log_date, status)
        VALUES (?, ?, ?)
        """,
        (habit_id, log_date.isoformat(), status),
    )

    return True


def list_habit_logs(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if habit_id is not None:
        get_habit_or_raise(conn, user_id, habit_id)

    if from_date and to_date and from_date > to_date:
        raise ValidationError("from-date must be on or before to-date.")

    where = ["h.user_id = ?"]
    params: List[Any] = [user_id]

    if habit_id is not None:
        where.append("l.habit_id = ?")
        params.append(habit_id)

    if from_date:
        where.append("l.log_date >= ?")
        params.append(from_date.isoformat())

    if to_date:
        where.append("l.log_date <= ?")
        params.append(to_date.isoformat())

    if status:
        where.append("l.status = ?")
        params.append(status)

    query = f"""
        SELECT
            l.id,
            l.habit_id,
            h.name AS habit_name,
            l.log_date,
            l.status,
            l.created_at
        FROM habit_logs l
        JOIN habits h ON h.id = l.habit_id
        WHERE {' AND '.join(where)}
        ORDER BY l.log_date DESC, l.id DESC
        LIMIT ?
    """

    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------


def expected_daily_days(habit: Dict[str, Any]) -> Optional[int]:
    if habit["habit_type"] != "daily":
        return None

    try:
        start = parse_date_value(str(habit["start_date"]), "start_date")
        end = parse_optional_date_value(habit.get("end_date"), "end_date") or date.today()
    except ValidationError:
        return 0

    end = min(end, date.today())

    if end < start:
        return 0

    return (end - start).days + 1


def current_daily_streak(conn: sqlite3.Connection, habit: Dict[str, Any]) -> Optional[int]:
    if habit["habit_type"] != "daily":
        return None

    try:
        start = parse_date_value(str(habit["start_date"]), "start_date")
        end = parse_optional_date_value(habit.get("end_date"), "end_date") or date.today()
    except ValidationError:
        return 0

    end = min(end, date.today())

    if end < start:
        return 0

    streak = 0
    current = end

    while current >= start:
        row = conn.execute(
            """
            SELECT status
            FROM habit_logs
            WHERE habit_id = ? AND log_date = ?
            """,
            (habit["id"], current.isoformat()),
        ).fetchone()

        if row and row["status"] == "completed":
            streak += 1
            current -= timedelta(days=1)
        else:
            break

    return streak


def habit_progress_stats(
    conn: sqlite3.Connection,
    habit: Dict[str, Any],
) -> Dict[str, Any]:
    stats_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_logs,
            COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
            COALESCE(SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END), 0) AS missed,
            COALESCE(SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped,
            MIN(log_date) AS first_log,
            MAX(log_date) AS last_log
        FROM habit_logs
        WHERE habit_id = ?
        """,
        (habit["id"],),
    ).fetchone()

    completed = int(stats_row["completed"] or 0)
    missed = int(stats_row["missed"] or 0)
    skipped = int(stats_row["skipped"] or 0)

    denominator = completed + missed
    completion_rate = round((completed / denominator) * 100.0, 1) if denominator else 0.0

    return {
        "id": habit["id"],
        "name": habit["name"],
        "habit_type": habit["habit_type"],
        "completed": completed,
        "missed": missed,
        "skipped": skipped,
        "rate": completion_rate,
        "streak": current_daily_streak(conn, habit),
        "expected": expected_daily_days(habit),
        "first_log": stats_row["first_log"],
        "last_log": stats_row["last_log"],
    }


def progress_summary_for_user(
    conn: sqlite3.Connection,
    user_id: int,
) -> List[Dict[str, Any]]:
    habits = conn.execute(
        """
        SELECT *
        FROM habits
        WHERE user_id = ?
        ORDER BY name COLLATE NOCASE, id
        """,
        (user_id,),
    ).fetchall()

    return [habit_progress_stats(conn, row_to_dict(habit)) for habit in habits]


def build_chart_series(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: Optional[int],
    days: int,
) -> Tuple[List[date], List[Optional[float]]]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=index) for index in range(days)]

    if habit_id:
        rows = conn.execute(
            """
            SELECT log_date, status
            FROM habit_logs
            WHERE habit_id = ? AND log_date BETWEEN ? AND ?
            ORDER BY log_date
            """,
            (habit_id, start.isoformat(), end.isoformat()),
        ).fetchall()

        status_by_date = {row["log_date"]: row["status"] for row in rows}
        rates: List[Optional[float]] = []

        for current_date in dates:
            status = status_by_date.get(current_date.isoformat())

            if status == "skipped":
                rates.append(None)
            elif status == "completed":
                rates.append(100.0)
            else:
                rates.append(0.0)

        return dates, rates

    rows = conn.execute(
        """
        SELECT
            l.log_date AS log_date,
            COALESCE(SUM(CASE WHEN l.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
            COALESCE(SUM(CASE WHEN l.status = 'missed' THEN 1 ELSE 0 END), 0) AS missed
        FROM habit_logs l
        JOIN habits h ON h.id = l.habit_id
        WHERE h.user_id = ? AND l.log_date BETWEEN ? AND ?
        GROUP BY l.log_date
        ORDER BY l.log_date
        """,
        (user_id, start.isoformat(), end.isoformat()),
    ).fetchall()

    rate_by_date: Dict[str, float] = {}

    for row in rows:
        completed = int(row["completed"] or 0)
        missed = int(row["missed"] or 0)
        denominator = completed + missed
        rate_by_date[row["log_date"]] = round((completed / denominator) * 100.0, 2) if denominator else 0.0

    rates = [rate_by_date.get(current_date.isoformat(), 0.0) for current_date in dates]
    return dates, rates


def default_output_path() -> Path:
    return Path(DEFAULT_SESSION_PATH).parent / "progress.png"


def render_ascii_chart(
    dates: Sequence[date],
    rates: Sequence[Optional[float]],
    title: str,
) -> str:
    if not dates:
        return "No data to display."

    max_points = 60

    if len(dates) > max_points:
        step = (len(dates) + max_points - 1) // max_points
        sampled_dates = list(dates[::step])
        sampled_rates = list(rates[::step])
    else:
        sampled_dates = list(dates)
        sampled_rates = list(rates)

    height = 10
    lines = [title]

    for level in range(height, 0, -1):
        threshold = level * (100.0 / height)
        line = f"{int(round(threshold)):>3}% |"

        for rate in sampled_rates:
            if rate is None:
                line += " "
            elif rate >= threshold:
                line += "█"
            else:
                line += " "

        lines.append(line)

    lines.append(" " + "-" * len(sampled_dates))

    if sampled_dates:
        middle_index = len(sampled_dates) // 2
        labels = [
            sampled_dates[0].isoformat(),
            sampled_dates[middle_index].isoformat(),
            sampled_dates[-1].isoformat(),
        ]
        lines.append(" " + " ".join(labels))

    return "\n".join(lines)


def generate_progress_chart(
    conn: sqlite3.Connection,
    user_id: int,
    habit_id: Optional[int],
    days: int,
    output_path: Optional[Path],
) -> Tuple[Optional[str], Optional[str]]:
    """Generate a progress chart.

    Returns:
        (png_path, ascii_chart)
        png_path is set when matplotlib succeeds.
        ascii_chart is set when matplotlib is unavailable.
    """
    dates, rates = build_chart_series(conn, user_id, habit_id, days)

    if habit_id:
        habit = get_habit_or_raise(conn, user_id, habit_id)
        title = f"Progress: {habit['name']}"
    else:
        title = "Overall habit completion"

    chart_path = output_path if output_path is not None else default_output_path()

    try:
        import matplotlib  # type: ignore

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return None, render_ascii_chart(dates, rates, title)

    try:
        ensure_parent_directory(chart_path, "chart output")

        fig, ax = plt.subplots(figsize=(max(8.0, min(18.0, days * 0.25)), 4.0))
        ax.plot(dates, rates, marker="o", linewidth=2, color="#2563eb")
        ax.set_ylim(-5, 105)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylabel("Completion rate (%)")
        ax.set_xlabel("Date")
        ax.set_title(title)
        ax.grid(True, linestyle="--", alpha=0.35)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(str(chart_path), dpi=160)
        plt.close(fig)
    except Exception as exc:
        raise HabitTrackerError(f"Could not create progress chart: {exc}") from exc

    return str(chart_path), None


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_init_db(args: argparse.Namespace) -> int:
    with database_connection(args.db_path):
        pass

    print(f"Database initialized at {expand_path(args.db_path)}")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    username = normalize_username(args.username)

    with database_connection(args.db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if existing:
            raise ValidationError("Username already exists.")

        password = prompt_password(confirm=True)

        try:
            password_hash = PasswordHasher.hash_password(password)
        except Exception as exc:
            raise HabitTrackerError(f"Password hashing failed: {exc}") from exc

        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
                """,
                (username, password_hash),
            )
        except sqlite3.IntegrityError as exc:
            raise DatabaseError(f"Could not create user. Database constraint failed: {exc}") from exc

    print(f"Account created for '{username}' (user_id={cursor.lastrowid}).")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    username = normalize_username(args.username)
    session_path = expand_path(DEFAULT_SESSION_PATH)

    if session_path.exists() and not args.force:
        raise AuthenticationError("Already logged in. Use --force or run 'logout'.")

    password = prompt_password(confirm=False)

    with database_connection(args.db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if row is None:
            raise AuthenticationError("Invalid username or password.")

        try:
            valid = PasswordHasher.verify_password(password, row["password_hash"])
        except RuntimeError as exc:
            raise AuthenticationError(str(exc)) from exc

        if not valid:
            raise AuthenticationError("Invalid username or password.")

        user = row_to_dict(row)
        write_session_file(session_path, int(user["id"]), str(user["username"]))

    print(f"Logged in as {user['username']}.")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    session_path = expand_path(DEFAULT_SESSION_PATH)

    if session_path.exists():
        remove_session_file(session_path)
        print("Logged out.")
    else:
        print("No active session.")

    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)

    print(f"Logged in as {user['username']} (user_id={user['id']}).")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    db_path = expand_path(args.db_path)
    session_path = expand_path(DEFAULT_SESSION_PATH)

    with database_connection(db_path) as conn:
        try:
            user = require_current_user(conn, session_path)
        except AuthenticationError:
            user = None

        version_row = conn.execute(
            "SELECT value FROM schema_info WHERE key = 'version'"
        ).fetchone()

        schema_version = version_row["value"] if version_row else "unknown"

    hasher = (
        "bcrypt"
        if bcrypt is not None
        else f"pbkdf2-sha256 ({PASSWORD_ITERATIONS:,} iterations)"
    )

    print("Daily Habit Tracker")
    print(f"Database       : {db_path}")
    print(f"Session file   : {session_path}")
    print(f"Current user   : {user['username']} (id={user['id']})" if user else "Current user   : none")
    print(f"Schema version : {schema_version}")
    print(f"Password hasher: {hasher}")

    return 0


def cmd_habit_add(args: argparse.Namespace) -> int:
    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        habit_id = create_habit(
            conn,
            user["id"],
            args.name,
            args.description,
            args.habit_type,
            args.start_date,
            args.end_date,
        )

    print(f"Habit created (id={habit_id}).")
    return 0


def cmd_habit_update(args: argparse.Namespace) -> int:
    if args.end_date is not None and args.clear_end_date:
        raise ValidationError("Use either --end-date or --clear-end-date, not both.")

    updates: Dict[str, Any] = {}

    if args.name is not None:
        updates["name"] = validate_text(args.name, "name", 1, 100)

    if args.description is not None:
        updates["description"] = validate_text(args.description, "description", 0, 500)

    if args.habit_type is not None:
        updates["habit_type"] = args.habit_type

    if args.start_date is not None:
        updates["start_date"] = parse_date_value(args.start_date, "start_date")

    if args.end_date is not None:
        updates["end_date"] = parse_optional_date_value(args.end_date, "end_date")
    elif args.clear_end_date:
        updates["end_date"] = None

    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        update_habit(conn, user["id"], args.habit_id, updates)

    print(f"Habit {args.habit_id} updated.")
    return 0


def cmd_habit_delete(args: argparse.Namespace) -> int:
    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        habit = get_habit_or_raise(conn, user["id"], args.habit_id)

        if not args.yes:
            try:
                answer = input(f"Delete habit '{habit['name']}' and all its logs? [y/N] ").strip().lower()
            except EOFError:
                raise ValidationError("Delete requires --yes in non-interactive sessions.") from None

            if answer not in {"y", "yes"}:
                print("Cancelled.")
                return 0

        delete_habit(conn, user["id"], args.habit_id)

    print(f"Deleted habit {args.habit_id} ('{habit['name']}').")
    return 0


def cmd_habit_list(args: argparse.Namespace) -> int:
    limit = validate_limit(args.limit, "limit")

    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        habits = list_habits_for_user(
            conn,
            user["id"],
            active_only=args.active,
            habit_type=args.type,
            limit=limit,
        )

    if not habits:
        print("No habits found.")
        return 0

    rows = [
        (
            habit["id"],
            habit["habit_type"],
            truncate(habit["name"], 24),
            truncate(habit.get("description") or "", 32),
            habit["start_date"],
            format_optional_date(habit.get("end_date")),
            habit["total_logs"],
            habit["completed_logs"],
        )
        for habit in habits
    ]

    print_table(
        ["ID", "Type", "Name", "Description", "Start", "End", "Logs", "Done"],
        rows,
    )

    return 0


def cmd_log_add(args: argparse.Namespace) -> int:
    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        habit = get_habit_or_raise(conn, user["id"], args.habit_id)
        log_date = parse_date_value(args.date, "date")
        created = upsert_habit_log(
            conn,
            user["id"],
            habit["id"],
            log_date,
            args.status,
        )

    verb = "Created" if created else "Updated"
    print(f"{verb} log for '{habit['name']}' on {log_date.isoformat()}: {args.status}.")
    return 0


def cmd_logs_list(args: argparse.Namespace) -> int:
    limit = validate_limit(args.limit, "limit")

    from_date = parse_optional_date_value(args.from_date, "from-date") if args.from_date else None
    to_date = parse_optional_date_value(args.to_date, "to-date") if args.to_date else None

    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        logs = list_habit_logs(
            conn,
            user["id"],
            habit_id=args.habit_id,
            from_date=from_date,
            to_date=to_date,
            status=args.status,
            limit=limit,
        )

    if not logs:
        print("No logs found.")
        return 0

    rows = [
        (
            log["id"],
            truncate(log["habit_name"], 24),
            log["log_date"],
            log["status"],
            log["created_at"],
        )
        for log in logs
    ]

    print_table(["ID", "Habit", "Date", "Status", "Created"], rows)
    return 0


def cmd_progress_summary(args: argparse.Namespace) -> int:
    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        stats = progress_summary_for_user(conn, user["id"])

    if not stats:
        print("No habits found. Create one first.")
        return 0

    rows = [
        (
            item["id"],
            item["habit_type"],
            truncate(item["name"], 28),
            item["completed"],
            item["missed"],
            item["skipped"],
            f"{item['rate']:.1f}%",
            format_streak(item["streak"]),
            format_expected(item["expected"]),
        )
        for item in stats
    ]

    print_table(
        ["ID", "Type", "Name", "Completed", "Missed", "Skipped", "Rate", "Streak", "Expected"],
        rows,
    )

    return 0


def cmd_progress_chart(args: argparse.Namespace) -> int:
    days = validate_chart_days(args.days)
    output_path = expand_path(args.output) if args.output else None

    with database_connection(args.db_path) as conn:
        user = require_current_user(conn)
        chart_path, ascii_chart = generate_progress_chart(
            conn,
            user["id"],
            args.habit_id,
            days,
            output_path,
        )

    if chart_path:
        print(f"Progress chart saved to {chart_path}")
    else:
        print("Matplotlib is unavailable; showing ASCII preview:")
        print(ascii_chart)

    return 0


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track and manage daily habits from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python habit_tracker.py init-db
  python habit_tracker.py register alice
  python habit_tracker.py login alice
  python habit_tracker.py habits add "Drink water" --type daily
  python habit_tracker.py habits add "Read" --type daily --description "20 pages"
  python habit_tracker.py habits update 1 --name "Drink 2L water"
  python habit_tracker.py habits delete 1 --yes
  python habit_tracker.py logs add 1 --status completed
  python habit_tracker.py logs add 1 --date 2026-05-15 --status missed
  python habit_tracker.py logs list --habit-id 1
  python habit_tracker.py progress summary
  python habit_tracker.py progress chart --days 30
        """,
    )

    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path. Default: {DEFAULT_DB_PATH}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument(
        "--db-path",
        default=argparse.SUPPRESS,
        help="SQLite database path for this command.",
    )

    p = subparsers.add_parser("init-db", parents=[db_parent], help="Initialize the database")
    p.set_defaults(func=cmd_init_db)

    p = subparsers.add_parser("register", parents=[db_parent], help="Create a new account")
    p.add_argument("username")
    p.set_defaults(func=cmd_register)

    p = subparsers.add_parser("login", parents=[db_parent], help="Log in")
    p.add_argument("username")
    p.add_argument("--force", action="store_true", help="Replace an existing session")
    p.set_defaults(func=cmd_login)

    p = subparsers.add_parser("logout", parents=[db_parent], help="Log out")
    p.set_defaults(func=cmd_logout)

    p = subparsers.add_parser("whoami", parents=[db_parent], help="Show current logged-in user")
    p.set_defaults(func=cmd_whoami)

    p = subparsers.add_parser("info", parents=[db_parent], help="Show app/database/session info")
    p.set_defaults(func=cmd_info)

    # Habit commands
    p_habits = subparsers.add_parser("habits", parents=[db_parent], help="Manage habits")
    h_sub = p_habits.add_subparsers(dest="habit_action", required=True, metavar="ACTION")

    p = h_sub.add_parser("add", help="Create a habit")
    p.add_argument("name")
    p.add_argument("--description", "-d", default="", help="Optional description, max 500 characters")
    p.add_argument("--type", choices=HABIT_TYPES, default="daily", dest="habit_type", help="Habit frequency")
    p.add_argument("--start-date", default=today_iso(), help="Start date in YYYY-MM-DD format")
    p.add_argument("--end-date", help="Optional end date in YYYY-MM-DD format")
    p.set_defaults(func=cmd_habit_add)

    p = h_sub.add_parser("update", help="Update a habit")
    p.add_argument("habit_id", type=int)
    p.add_argument("--name", help="New habit name")
    p.add_argument("--description", help="New description")
    p.add_argument("--type", choices=HABIT_TYPES, dest="habit_type", help="New habit frequency")
    p.add_argument("--start-date", help="New start date in YYYY-MM-DD format")
    p.add_argument("--end-date", help="New end date in YYYY-MM-DD format")
    p.add_argument("--clear-end-date", action="store_true", help="Clear the optional end date")
    p.set_defaults(func=cmd_habit_update)

    p = h_sub.add_parser("delete", aliases=["rm"], help="Delete a habit and its logs")
    p.add_argument("habit_id", type=int)
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p.set_defaults(func=cmd_habit_delete)

    p = h_sub.add_parser("list", aliases=["ls"], help="List habits")
    p.add_argument("--active", action="store_true", help="Only show habits that have not ended")
    p.add_argument("--type", choices=HABIT_TYPES, help="Filter by habit type")
    p.add_argument("--limit", type=int, default=50, help="Maximum rows to show")
    p.set_defaults(func=cmd_habit_list)

    # Log commands
    p_logs = subparsers.add_parser("logs", parents=[db_parent], help="Manage habit logs")
    log_sub = p_logs.add_subparsers(dest="log_action", required=True, metavar="ACTION")

    p = log_sub.add_parser("add", help="Create or update a habit log")
    p.add_argument("habit_id", type=int)
    p.add_argument("--date", default=today_iso(), help="Log date in YYYY-MM-DD format")
    p.add_argument("--status", choices=LOG_STATUSES, default="completed", help="Log status")
    p.set_defaults(func=cmd_log_add)

    p = log_sub.add_parser("list", aliases=["ls"], help="List habit logs")
    p.add_argument("--habit-id", type=int, help="Filter by habit ID")
    p.add_argument("--from-date", help="Inclusive start date in YYYY-MM-DD format")
    p.add_argument("--to-date", help="Inclusive end date in YYYY-MM-DD format")
    p.add_argument("--status", choices=LOG_STATUSES, help="Filter by status")
    p.add_argument("--limit", type=int, default=50, help="Maximum rows to show")
    p.set_defaults(func=cmd_logs_list)

    # Progress commands
    p_progress = subparsers.add_parser("progress", parents=[db_parent], help="View progress")
    progress_sub = p_progress.add_subparsers(dest="progress_action", required=True, metavar="ACTION")

    p = progress_sub.add_parser("summary", aliases=["stats"], help="Show progress summary")
    p.set_defaults(func=cmd_progress_summary)

    p = progress_sub.add_parser("chart", aliases=["plot"], help="Generate a progress chart")
    p.add_argument("--habit-id", type=int, help="Chart a single habit. Defaults to aggregate progress.")
    p.add_argument("--days", type=int, default=30, help="Number of days to include")
    p.add_argument("--output", "-o", help="Output PNG path")
    p.set_defaults(func=cmd_progress_chart)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except HabitTrackerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except sqlite3.Error as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```