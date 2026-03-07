"""SQLite storage for fingerprints and trained models."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_DIR = Path.home() / ".wifipos"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "wifipos.db"


class Database:
    """SQLite database for storing WiFi fingerprints and trained models."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the database.

        Args:
            db_path: Path to the SQLite database file. If None, uses the default
                     path (~/.wifipos/wifipos.db). Use ':memory:' for in-memory DB.
        """
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path

        if db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the database tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                raw_data JSON NOT NULL
            );

            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                model_blob BLOB NOT NULL,
                metadata JSON NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_fingerprints_location
                ON fingerprints(location);
        """)
        self._conn.commit()

    def save_fingerprint(
        self, location: str, raw_data: list[dict], timestamp: datetime | None = None
    ) -> int:
        """Save a WiFi fingerprint to the database.

        Args:
            location: The location name.
            raw_data: List of WiFi reading dictionaries.
            timestamp: When the fingerprint was collected. Defaults to now.

        Returns:
            The ID of the saved fingerprint.
        """
        if timestamp is None:
            timestamp = datetime.now()

        cursor = self._conn.execute(
            "INSERT INTO fingerprints (location, timestamp, raw_data) VALUES (?, ?, ?)",
            (location, timestamp.isoformat(), json.dumps(raw_data)),
        )
        self._conn.commit()
        logger.debug(f"Saved fingerprint for location '{location}' with id {cursor.lastrowid}")
        return cursor.lastrowid  # type: ignore[return-value]

    def get_all_fingerprints(self) -> list[dict]:
        """Get all fingerprints from the database.

        Returns:
            A list of dictionaries with keys: id, location, timestamp, raw_data.
        """
        cursor = self._conn.execute(
            "SELECT id, location, timestamp, raw_data FROM fingerprints ORDER BY id"
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "location": row["location"],
                "timestamp": row["timestamp"],
                "raw_data": json.loads(row["raw_data"]),
            }
            for row in rows
        ]

    def get_fingerprints_by_location(self, location: str) -> list[dict]:
        """Get fingerprints for a specific location.

        Args:
            location: The location name to filter by.

        Returns:
            A list of fingerprint dictionaries.
        """
        cursor = self._conn.execute(
            "SELECT id, location, timestamp, raw_data FROM fingerprints WHERE location = ? ORDER BY id",
            (location,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "location": row["location"],
                "timestamp": row["timestamp"],
                "raw_data": json.loads(row["raw_data"]),
            }
            for row in rows
        ]

    def get_locations(self) -> list[str]:
        """Get all unique location names.

        Returns:
            A sorted list of location names.
        """
        cursor = self._conn.execute(
            "SELECT DISTINCT location FROM fingerprints ORDER BY location"
        )
        return [row["location"] for row in cursor.fetchall()]

    def get_fingerprint_count_by_location(self) -> dict[str, int]:
        """Get the count of fingerprints for each location.

        Returns:
            A dictionary mapping location names to fingerprint counts.
        """
        cursor = self._conn.execute(
            "SELECT location, COUNT(*) as count FROM fingerprints GROUP BY location ORDER BY location"
        )
        return {row["location"]: row["count"] for row in cursor.fetchall()}

    def delete_location(self, location: str) -> int:
        """Delete all fingerprints for a location.

        Args:
            location: The location name to delete.

        Returns:
            The number of deleted fingerprints.
        """
        cursor = self._conn.execute(
            "DELETE FROM fingerprints WHERE location = ?", (location,)
        )
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info(f"Deleted {deleted} fingerprints for location '{location}'")
        return deleted

    def save_model(self, model_blob: bytes, metadata: dict) -> int:
        """Save a trained model to the database.

        Args:
            model_blob: The serialized model bytes.
            metadata: Model metadata (accuracy, locations, etc.).

        Returns:
            The ID of the saved model.
        """
        cursor = self._conn.execute(
            "INSERT INTO models (created_at, model_blob, metadata) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), model_blob, json.dumps(metadata)),
        )
        self._conn.commit()
        logger.info(f"Saved model with id {cursor.lastrowid}")
        return cursor.lastrowid  # type: ignore[return-value]

    def load_latest_model(self) -> dict | None:
        """Load the most recently saved model.

        Returns:
            A dictionary with keys: id, created_at, model_blob, metadata.
            Returns None if no model exists.
        """
        cursor = self._conn.execute(
            "SELECT id, created_at, model_blob, metadata FROM models ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "model_blob": row["model_blob"],
            "metadata": json.loads(row["metadata"]),
        }

    def reset(self) -> None:
        """Delete all data from the database."""
        self._conn.executescript("""
            DELETE FROM fingerprints;
            DELETE FROM models;
        """)
        self._conn.commit()
        logger.info("Database reset: all data deleted.")

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
