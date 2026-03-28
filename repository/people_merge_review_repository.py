"""
UX-9A: Persistent merge review decisions.

Stores accepted / rejected merge review decisions so pairs are not
resurfaced blindly in future suggestion runs.
"""

from __future__ import annotations

from typing import Set, Tuple


class PeopleMergeReviewRepository:
    """
    Stores accepted / rejected merge review decisions.
    Lightweight UX-9A persistence layer.
    """

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        conn = self.db if hasattr(self.db, "execute") else None
        if conn is None:
            return

        conn.execute("""
            CREATE TABLE IF NOT EXISTS people_merge_reviews (
                left_id TEXT NOT NULL,
                right_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (left_id, right_id)
            )
        """)

    def _pair_key(self, left_id: str, right_id: str) -> tuple[str, str]:
        return tuple(sorted((str(left_id), str(right_id))))

    def set_decision(self, left_id: str, right_id: str, decision: str):
        left_id, right_id = self._pair_key(left_id, right_id)
        self.db.execute("""
            INSERT INTO people_merge_reviews (left_id, right_id, decision)
            VALUES (?, ?, ?)
            ON CONFLICT(left_id, right_id)
            DO UPDATE SET decision=excluded.decision, created_at=CURRENT_TIMESTAMP
        """, (left_id, right_id, decision))

    def get_pairs_by_decision(self, decision: str) -> Set[Tuple[str, str]]:
        rows = self.db.execute("""
            SELECT left_id, right_id
            FROM people_merge_reviews
            WHERE decision = ?
        """, (decision,)).fetchall()
        return {self._pair_key(r[0], r[1]) for r in rows}

    def accept(self, left_id: str, right_id: str):
        self.set_decision(left_id, right_id, "accepted")

    def reject(self, left_id: str, right_id: str):
        self.set_decision(left_id, right_id, "rejected")
