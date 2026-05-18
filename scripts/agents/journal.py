from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "user_data" / "agent_journal" / "trades.sqlite"


class AgentJournal:
    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                create table if not exists market_snapshots (
                    id integer primary key autoincrement,
                    created_at text not null,
                    pair text not null,
                    payload text not null
                );
                create table if not exists agent_outputs (
                    id integer primary key autoincrement,
                    created_at text not null,
                    pair text not null,
                    agent text not null,
                    payload text not null
                );
                create table if not exists decisions (
                    id integer primary key autoincrement,
                    created_at text not null,
                    pair text not null,
                    decision text not null,
                    payload text not null
                );
                create table if not exists executions (
                    id integer primary key autoincrement,
                    created_at text not null,
                    pair text not null,
                    mode text not null,
                    status text not null,
                    payload text not null
                );
                """
            )

    def record_snapshot(self, pair: str, payload: dict[str, Any]) -> None:
        self._insert("market_snapshots", pair, None, payload)

    def record_agent_output(self, pair: str, agent: str, payload: dict[str, Any]) -> None:
        self._insert("agent_outputs", pair, agent, payload)

    def record_decision(self, pair: str, decision: str, payload: dict[str, Any]) -> None:
        self._insert("decisions", pair, decision, payload)

    def record_execution(self, pair: str, mode: str, status: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "insert into executions(created_at, pair, mode, status, payload) values (?, ?, ?, ?, ?)",
                (utc_now(), pair, mode, status, json.dumps(payload, sort_keys=True)),
            )

    def _insert(self, table: str, pair: str, label: str | None, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            if table == "agent_outputs":
                conn.execute(
                    "insert into agent_outputs(created_at, pair, agent, payload) values (?, ?, ?, ?)",
                    (utc_now(), pair, label, json.dumps(payload, sort_keys=True)),
                )
            elif table == "decisions":
                conn.execute(
                    "insert into decisions(created_at, pair, decision, payload) values (?, ?, ?, ?)",
                    (utc_now(), pair, label, json.dumps(payload, sort_keys=True)),
                )
            else:
                conn.execute(
                    "insert into market_snapshots(created_at, pair, payload) values (?, ?, ?)",
                    (utc_now(), pair, json.dumps(payload, sort_keys=True)),
                )

