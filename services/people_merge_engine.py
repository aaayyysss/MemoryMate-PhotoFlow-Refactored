"""
UX-9A Post-Implementation: PeopleMergeEngine

Complementary merge engine that works with structured DB tables
(people_merge_decisions, people_merge_candidates, people_cluster_summary)
for persistent candidate caching, accept/reject decisions with scoring,
and cluster summary materialization.

Works alongside the existing PeopleMergeIntelligence (centroid-based scoring)
to provide a DB-native scoring and decision pipeline.
"""

import json
import math
import sqlite3
from typing import List, Dict, Any, Optional


def _cosine_similarity(vec_a, vec_b) -> float:
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = math.sqrt(sum(a * a for a in vec_a))
    nb = math.sqrt(sum(b * b for b in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class PeopleMergeEngine:
    """
    DB-native merge engine:
    - builds cluster summaries from face_branch_reps
    - scores merge candidates (78% embedding, 17% size balance, 5% unnamed bonus)
    - stores accept/reject decisions with scores
    - excludes already-rejected pairs
    - caches candidates for fast re-retrieval
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_merge_suggestions(self, project_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        summaries = self._load_cluster_summaries(project_id)
        rejected = self._load_rejected_pairs(project_id)

        suggestions: List[Dict[str, Any]] = []
        n = len(summaries)

        for i in range(n):
            for j in range(i + 1, n):
                left = summaries[i]
                right = summaries[j]

                pair_key = self._normalize_pair(left["person_id"], right["person_id"])
                if pair_key in rejected:
                    continue

                score, evidence = self._score_pair(left, right)
                if score < 0.60:
                    continue

                suggestions.append({
                    "left_id": left["person_id"],
                    "right_id": right["person_id"],
                    "left_label": left["label"],
                    "right_label": right["label"],
                    "score": score,
                    "label": f'{left["label"]} \u2194 {right["label"]} (score={score:.2f})',
                    "evidence": evidence,
                })

        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:limit]

    def accept_merge(self, project_id: int, left_person_id: str, right_person_id: str,
                     score: Optional[float] = None, reason: str = ""):
        left_person_id, right_person_id = self._normalize_pair(left_person_id, right_person_id)
        with self.conn:
            self.conn.execute("""
                INSERT OR IGNORE INTO people_merge_decisions
                (project_id, left_person_id, right_person_id, decision, score, reason)
                VALUES (?, ?, ?, 'accept', ?, ?)
            """, (project_id, left_person_id, right_person_id, score, reason))

    def reject_merge(self, project_id: int, left_person_id: str, right_person_id: str,
                     score: Optional[float] = None, reason: str = ""):
        left_person_id, right_person_id = self._normalize_pair(left_person_id, right_person_id)
        with self.conn:
            self.conn.execute("""
                INSERT OR IGNORE INTO people_merge_decisions
                (project_id, left_person_id, right_person_id, decision, score, reason)
                VALUES (?, ?, ?, 'reject', ?, ?)
            """, (project_id, left_person_id, right_person_id, score, reason))

    def cache_candidates(self, project_id: int, suggestions: List[Dict[str, Any]]):
        with self.conn:
            self.conn.execute("DELETE FROM people_merge_candidates WHERE project_id = ?", (project_id,))
            for s in suggestions:
                left_id, right_id = self._normalize_pair(s["left_id"], s["right_id"])
                self.conn.execute("""
                    INSERT OR REPLACE INTO people_merge_candidates
                    (project_id, left_person_id, right_person_id, score, evidence_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    project_id, left_id, right_id,
                    float(s.get("score", 0.0)),
                    json.dumps(s.get("evidence", {}), ensure_ascii=False),
                ))

    def rebuild_cluster_summaries(self, project_id: int, cluster_rows: List[Dict[str, Any]]):
        with self.conn:
            self.conn.execute("DELETE FROM people_cluster_summary WHERE project_id = ?", (project_id,))
            for row in cluster_rows:
                self.conn.execute("""
                    INSERT INTO people_cluster_summary
                    (project_id, person_id, label, face_count, representative_face_path, avg_embedding, is_unnamed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    project_id,
                    str(row["person_id"]),
                    str(row.get("label") or row["person_id"]),
                    int(row.get("face_count", 0)),
                    row.get("representative_face_path"),
                    row.get("avg_embedding_blob"),
                    1 if row.get("is_unnamed") else 0,
                ))

    def _load_cluster_summaries(self, project_id: int) -> List[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT person_id, label, face_count, representative_face_path, avg_embedding, is_unnamed
            FROM people_cluster_summary
            WHERE project_id = ?
            ORDER BY face_count DESC
        """, (project_id,))
        rows = []
        for person_id, label, face_count, rep_path, emb_blob, is_unnamed in cur.fetchall():
            rows.append({
                "person_id": str(person_id),
                "label": str(label or person_id),
                "face_count": int(face_count or 0),
                "representative_face_path": rep_path,
                "avg_embedding": self._decode_embedding_blob(emb_blob),
                "is_unnamed": bool(is_unnamed),
            })
        return rows

    def _load_rejected_pairs(self, project_id: int):
        cur = self.conn.execute("""
            SELECT left_person_id, right_person_id
            FROM people_merge_decisions
            WHERE project_id = ? AND decision = 'reject'
        """, (project_id,))
        return {self._normalize_pair(a, b) for a, b in cur.fetchall()}

    def _score_pair(self, left: Dict[str, Any], right: Dict[str, Any]):
        emb_score = _cosine_similarity(left.get("avg_embedding"), right.get("avg_embedding"))
        size_balance = min(left["face_count"], right["face_count"]) / max(1, max(left["face_count"], right["face_count"]))
        unnamed_bonus = 0.05 if (left.get("is_unnamed") or right.get("is_unnamed")) else 0.0

        score = (emb_score * 0.78) + (size_balance * 0.17) + unnamed_bonus

        evidence = {
            "embedding_similarity": round(emb_score, 4),
            "size_balance": round(size_balance, 4),
            "unnamed_bonus": unnamed_bonus,
        }
        return score, evidence

    def _decode_embedding_blob(self, blob):
        if not blob:
            return []
        try:
            import numpy as np
            return np.frombuffer(blob, dtype=np.float32).tolist()
        except Exception:
            pass
        try:
            import pickle
            vec = pickle.loads(blob)
            return [float(x) for x in vec]
        except Exception:
            return []

    def _normalize_pair(self, left_id: str, right_id: str):
        a, b = sorted([str(left_id), str(right_id)])
        return a, b
