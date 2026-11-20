"""Penghitung seq: naik pada setiap perubahan data."""


def current_seq(conn) -> int:
    row = conn.execute("SELECT value FROM seq_counter WHERE id=1").fetchone()
    return int(row["value"]) if row else 0


def bump_seq(conn) -> None:
    conn.execute("UPDATE seq_counter SET value = value + 1 WHERE id=1")