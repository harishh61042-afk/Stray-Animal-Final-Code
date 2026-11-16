"""database/schema.sql must describe exactly the tables of the models (needs neither Flask nor MySQL)."""
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "database" / "schema.sql"

EXPECTED_TABLES = {
    "users", "user_profiles", "volunteer_profiles", "rescuer_profiles", "veterinarian_profiles", "shelter_profiles",
    "animal_reports", "rescue_assignments", "rescue_activities", "animals", "animal_images", "animal_status_history",
    "shelter_admissions", "medical_records", "vaccinations", "volunteer_tasks", "volunteer_task_assignments",
    "adoption_applications", "adoption_records", "notifications", "audit_logs", "contact_messages",
}


def _as_sqlite(sql):
    """Translate the few MySQL-only parts so Python's built-in sqlite3 can check the rest of the syntax."""
    sql = re.sub(r"^CREATE DATABASE.*$|^USE .*$", "", sql, flags=re.M)
    sql = sql.replace(" AUTO_INCREMENT", "").replace("DEFAULT (UTC_TIMESTAMP())", "DEFAULT CURRENT_TIMESTAMP")
    sql = re.sub(r"\) ENGINE=InnoDB[^;]*;", ");", sql)
    sql = re.sub(r",\n  UNIQUE KEY `[^`]+` \(([^)]*)\)", r",\n  UNIQUE (\1)", sql)
    sql = re.sub(r",\n  KEY `[^`]+` \([^)]*\)", "", sql)
    return sql


def test_schema_file_matches_the_models():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "make_schema.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_schema_has_every_table_once():
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS `(\w+)`", SCHEMA.read_text(encoding="utf-8"))
    assert len(tables) == len(set(tables)) == 22
    assert set(tables) == EXPECTED_TABLES


def test_schema_runs_and_foreign_keys_point_at_real_columns():
    connection = sqlite3.connect(":memory:")
    connection.executescript(_as_sqlite(SCHEMA.read_text(encoding="utf-8")))
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert EXPECTED_TABLES <= names
    for table in EXPECTED_TABLES:
        for row in connection.execute(f"PRAGMA foreign_key_list(`{table}`)"):
            parent, parent_column = row[2], row[4]
            columns = [info[1] for info in connection.execute(f"PRAGMA table_info(`{parent}`)")]
            assert parent_column in columns, f"{table} points at missing {parent}.{parent_column}"
    connection.close()
