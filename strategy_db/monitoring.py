"""Query logging and alerting for RAG pipeline monitoring."""

import sqlite3
import time
import json
import hashlib
import os
from datetime import datetime, timezone


class QueryLogger:
    """Logs every query with latency, results, and metadata to SQLite."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)
            db_path = os.path.join(log_dir, "query_log.db")

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                query_hash TEXT,
                top_k INTEGER DEFAULT 5,
                where_filters TEXT,
                cache_layer TEXT DEFAULT 'none',
                num_results INTEGER DEFAULT 0,
                avg_similarity REAL DEFAULT 0.0,
                min_similarity REAL DEFAULT 0.0,
                latency_ms REAL DEFAULT 0.0,
                reranker_used INTEGER DEFAULT 0,
                finetuned_used INTEGER DEFAULT 0,
                hybrid_used INTEGER DEFAULT 0,
                errors TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_queries INTEGER DEFAULT 0,
                zero_result_queries INTEGER DEFAULT 0,
                avg_latency_ms REAL DEFAULT 0.0,
                p95_latency_ms REAL DEFAULT 0.0,
                avg_similarity REAL DEFAULT 0.0,
                cache_hit_rate REAL DEFAULT 0.0,
                avg_results_per_query REAL DEFAULT 0.0
            );

            CREATE INDEX IF NOT EXISTS idx_query_log_timestamp
                ON query_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_query_log_hash
                ON query_log(query_hash);
        """)
        self.conn.commit()

    def log(
        self,
        query: str,
        top_k: int,
        results: list[dict],
        latency_ms: float,
        cache_layer: str = "none",
        errors: str | None = None,
        reranker_used: bool = False,
        finetuned_used: bool = False,
        hybrid_used: bool = False,
        where_filters: str | None = None,
    ):
        sims = [r.get("rerank_score", r.get("score", 0.0)) for r in results]
        avg_sim = sum(sims) / len(sims) if sims else 0.0
        min_sim = min(sims) if sims else 0.0

        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]

        self.conn.execute(
            """INSERT INTO query_log
               (timestamp, query, query_hash, top_k, where_filters, cache_layer,
                num_results, avg_similarity, min_similarity, latency_ms,
                reranker_used, finetuned_used, hybrid_used, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                query,
                query_hash,
                top_k,
                where_filters,
                cache_layer,
                len(results),
                round(avg_sim, 4),
                round(min_sim, 4),
                round(latency_ms, 2),
                1 if reranker_used else 0,
                1 if finetuned_used else 0,
                1 if hybrid_used else 0,
                errors,
            ),
        )
        self.conn.commit()

    def daily_rollup(self, date_str: str = None):
        """Compute daily aggregate statistics."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        row = self.conn.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN num_results = 0 THEN 1 ELSE 0 END) as zero_results,
                 AVG(latency_ms) as avg_latency,
                 AVG(avg_similarity) as avg_sim,
                 AVG(num_results) as avg_results
               FROM query_log
               WHERE date(timestamp) = ?""",
            (date_str,),
        ).fetchone()

        if row and row[0] > 0:
            p95_row = self.conn.execute(
                """SELECT latency_ms FROM query_log
                   WHERE date(timestamp) = ?
                   ORDER BY latency_ms DESC""",
                (date_str,),
            ).fetchall()

            if p95_row:
                p95_idx = int(len(p95_row) * 0.05)
                p95_latency = p95_row[p95_idx][0] if p95_idx < len(p95_row) else p95_row[-1][0]
            else:
                p95_latency = 0.0

            cache_row = self.conn.execute(
                """SELECT
                     SUM(CASE WHEN cache_layer != 'none' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
                   FROM query_log WHERE date(timestamp) = ?""",
                (date_str,),
            ).fetchone()
            cache_hit_rate = cache_row[0] if cache_row else 0.0

            self.conn.execute(
                """INSERT OR REPLACE INTO daily_stats
                   (date, total_queries, zero_result_queries, avg_latency_ms,
                    p95_latency_ms, avg_similarity, cache_hit_rate, avg_results_per_query)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (date_str, row[0], row[1], round(row[2], 2), round(p95_latency, 2),
                 round(row[3], 4), round(cache_hit_rate or 0.0, 4), round(row[4], 2)),
            )
            self.conn.commit()

    def get_recent_stats(self, days: int = 7) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?",
            (days,),
        ).fetchall()
        cols = ["date", "total_queries", "zero_result_queries", "avg_latency_ms",
                "p95_latency_ms", "avg_similarity", "cache_hit_rate", "avg_results_per_query"]
        return [dict(zip(cols, row)) for row in rows]

    def close(self):
        self.conn.close()


class RetrievalAlert:
    """Alert on zero results, low similarity, or high latency."""

    def __init__(self, latency_threshold_ms: float = 1000.0,
                 similarity_threshold: float = 0.5,
                 few_results_threshold: int = 2):
        self.latency_threshold_ms = latency_threshold_ms
        self.similarity_threshold = similarity_threshold
        self.few_results_threshold = few_results_threshold
        self.alerts: list[tuple[str, str]] = []

    def check(self, results: list[dict], query: str,
              latency_ms: float) -> list[tuple[str, str]]:
        alerts = []

        if len(results) == 0:
            alerts.append(("CRITICAL", f"Zero results for query: '{query}'"))
        elif len(results) <= self.few_results_threshold:
            alerts.append(("WARNING",
                          f"Few results ({len(results)}) for: '{query}'"))

        if results:
            avg_sim = sum(
                r.get("rerank_score", r.get("score", 0.5)) for r in results
            ) / len(results)
            if avg_sim < self.similarity_threshold:
                alerts.append(("WARNING",
                              f"Low avg similarity ({avg_sim:.2f}) for: '{query}'"))

        if latency_ms > self.latency_threshold_ms:
            alerts.append(("WARNING",
                          f"High latency ({latency_ms:.0f}ms) for: '{query}'"))

        self.alerts.extend(alerts)
        return alerts

    def flush(self) -> list[tuple[str, str]]:
        """Return and clear all alerts."""
        result = self.alerts.copy()
        self.alerts.clear()
        return result
