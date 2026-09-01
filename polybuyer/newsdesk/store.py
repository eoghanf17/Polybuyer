"""Storage layer for the news desk.

SQLite through the stdlib so this runs anywhere with no dependencies and no
server. Every statement is portable SQL; swapping in Postgres means changing
the connection and the placeholder style, nothing else.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from .rules import RuleError, build_rules
from .schema import DDL, DEFAULTS, MIGRATIONS, SCHEMA_VERSION


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Market:
    condition_id: str
    question: str
    slug: str = ""
    rules: str = ""
    end_date: str = ""
    category: str = ""
    preferred_direction: int = 1
    token_id_ref: str = ""
    token_id_other: str = ""
    required_keyword: str = ""
    topic_terms: str = ""
    min_followers: int = DEFAULTS["min_followers"]
    aggression: float = DEFAULTS["aggression"]
    max_size_usd: float = DEFAULTS["max_size_usd"]
    aggression_kw: float = DEFAULTS["aggression_kw"]
    max_size_usd_kw: float = DEFAULTS["max_size_usd_kw"]
    on_off: int = 1
    off_reason: str = ""
    off_at: str = ""
    guard_5m: float = DEFAULTS["guard_5m"]
    guard_1h: float = DEFAULTS["guard_1h"]
    guard_2h: float = DEFAULTS["guard_2h"]
    guard_1d: float = DEFAULTS["guard_1d"]
    added_at: str = ""
    added_by: str = ""
    notes: str = ""
    accounts: list[dict] = field(default_factory=list)


class Store:
    def __init__(self, path: str = "newsdesk.db"):
        self.path = path
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        for stmt in DDL:
            self.db.execute(stmt)
        self._migrate()
        self.db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                        (str(SCHEMA_VERSION),))
        self.db.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the database was created.

        CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so a
        database made under an older schema keeps its old columns and the
        new ones have to be added explicitly. SQLite has no
        ADD COLUMN IF NOT EXISTS, so each statement is attempted and a
        duplicate-column error means it is already applied.
        """
        for _version, stmts in sorted(MIGRATIONS.items()):
            for stmt in stmts:
                try:
                    self.db.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
        self.db.execute("INSERT INTO meta(key,value) VALUES('schema_version',?)"
                        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (str(SCHEMA_VERSION),))
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ markets

    def add_market(self, m: Market) -> None:
        """Insert a market. An armed market must be streamable.

        Validating here rather than at stream time means a bad row is
        rejected by the person adding it, while they still have the context
        to fix it -- not silently disarmed hours later.
        """
        if m.on_off:
            probe = asdict(m)
            probe["accounts"] = m.accounts
            build_rules(probe)          # raises RuleError if unstreamable
        d = asdict(m)
        accounts = d.pop("accounts")
        d["added_at"] = d["added_at"] or _now()
        cols = ",".join(d)
        qs = ",".join("?" * len(d))
        self.db.execute(f"INSERT OR REPLACE INTO markets({cols}) VALUES({qs})",
                        tuple(d.values()))
        for a in accounts:
            self.add_account(m.condition_id, a["handle"],
                             a.get("tier", "beat"), a.get("why", ""))
        self.mark_seen(m.condition_id, m.question, "accepted", m.notes)
        self.db.commit()

    def add_account(self, cid: str, handle: str, tier: str = "beat",
                    why: str = "") -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO market_accounts(condition_id,handle,tier,why)"
            " VALUES(?,?,?,?)", (cid, handle.lstrip("@").lower(), tier, why))

    def get_market(self, cid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM markets WHERE condition_id=?", (cid,)).fetchone()
        if r is None:
            return None
        m = dict(r)
        m["accounts"] = [dict(a) for a in self.db.execute(
            "SELECT handle,tier,why FROM market_accounts WHERE condition_id=?", (cid,))]
        return m

    def armed_markets(self) -> list[dict]:
        """Every market currently armed, with its accounts.

        This is what the live engine loads on start and reloads on change.
        """
        rows = self.db.execute("SELECT * FROM markets WHERE on_off=1").fetchall()
        out = []
        for r in rows:
            m = dict(r)
            m["accounts"] = [dict(a) for a in self.db.execute(
                "SELECT handle,tier,why FROM market_accounts WHERE condition_id=?",
                (m["condition_id"],))]
            out.append(m)
        return out

    def watched_handles(self) -> dict[str, list[str]]:
        """handle -> condition_ids, across armed markets only.

        The stream subscribes to this key set; one handle can carry several
        markets, and a tweet must be scored against each.
        """
        out: dict[str, list[str]] = {}
        for r in self.db.execute(
            "SELECT a.handle, a.condition_id FROM market_accounts a"
            " JOIN markets m ON m.condition_id=a.condition_id WHERE m.on_off=1"
        ):
            out.setdefault(r["handle"], []).append(r["condition_id"])
        return out

    def stream_rules(self) -> list[dict]:
        """Every X filtered-stream rule across armed markets.

        This is the payload for ``POST /2/tweets/search/stream/rules``. A
        market whose configuration cannot produce a valid rule is skipped
        with its reason rather than aborting the set: one bad row must not
        take the whole desk off the air.
        """
        out: list[dict] = []
        for m in self.armed_markets():
            try:
                out.extend(r.as_dict() for r in build_rules(m))
            except RuleError as e:
                self.db.execute(
                    "UPDATE markets SET on_off=0, off_reason=?, off_at=?"
                    " WHERE condition_id=?",
                    (f"unbuildable rule: {e}", _now(), m["condition_id"]))
        self.db.commit()
        return out

    def disarm(self, cid: str, reason: str) -> None:
        """Turn a market off, recording why.

        Called after a fire, and also when a fire was wanted but the move
        guards blocked it -- the news is already in the price and re-arming
        would only chase it.
        """
        self.db.execute(
            "UPDATE markets SET on_off=0, off_reason=?, off_at=? WHERE condition_id=?",
            (reason, _now(), cid))
        self.db.commit()

    def set_params(self, cid: str, **kw: Any) -> None:
        allowed = {"aggression", "max_size_usd", "aggression_kw", "max_size_usd_kw",
                   "min_followers", "required_keyword", "topic_terms",
                   "on_off", "guard_5m", "guard_1h", "guard_2h", "guard_1d",
                   "preferred_direction", "rules", "notes"}
        bad = set(kw) - allowed
        if bad:
            raise ValueError(f"not settable: {sorted(bad)}")
        sets = ",".join(f"{k}=?" for k in kw)
        self.db.execute(f"UPDATE markets SET {sets} WHERE condition_id=?",
                        (*kw.values(), cid))
        self.db.commit()

    # -------------------------------------------------------------- seen

    def mark_seen(self, cid: str, question: str, decision: str = "pending",
                  reason: str = "") -> None:
        self.db.execute(
            "INSERT INTO seen_markets(condition_id,question,first_seen,decision,reason)"
            " VALUES(?,?,?,?,?) ON CONFLICT(condition_id) DO UPDATE SET"
            " decision=excluded.decision, reason=excluded.reason",
            (cid, question, _now(), decision, reason))
        self.db.commit()

    def seen_ids(self) -> set[str]:
        return {r["condition_id"] for r in
                self.db.execute("SELECT condition_id FROM seen_markets")}

    # ------------------------------------------------------------- fires

    def record_fire(self, cid: str, status: str, **kw: Any) -> int:
        row = {"condition_id": cid, "at": _now(), "status": status}
        for k in ("tweet_id", "handle", "tweet_text", "direction", "tier",
                  "followers", "mid_before", "limit_price", "size_usd",
                  "block_reason", "move_5m", "move_1h", "move_2h", "move_1d",
                  "latency_ms"):
            if k in kw:
                row[k] = kw[k]
        if "gate_answers" in kw:
            row["gate_answers"] = json.dumps(kw["gate_answers"])
        cols = ",".join(row)
        qs = ",".join("?" * len(row))
        cur = self.db.execute(f"INSERT INTO fires({cols}) VALUES({qs})",
                              tuple(row.values()))
        self.db.commit()
        return int(cur.lastrowid or 0)

    def fires(self, cid: str | None = None) -> list[dict]:
        if cid:
            rows = self.db.execute("SELECT * FROM fires WHERE condition_id=?"
                                   " ORDER BY id", (cid,))
        else:
            rows = self.db.execute("SELECT * FROM fires ORDER BY id")
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        q = lambda s: self.db.execute(s).fetchone()[0]  # noqa: E731
        return {
            "markets": q("SELECT COUNT(*) FROM markets"),
            "armed": q("SELECT COUNT(*) FROM markets WHERE on_off=1"),
            "accounts": q("SELECT COUNT(DISTINCT handle) FROM market_accounts"),
            "seen": q("SELECT COUNT(*) FROM seen_markets"),
            "fires": q("SELECT COUNT(*) FROM fires WHERE status!='blocked'"),
            "blocked": q("SELECT COUNT(*) FROM fires WHERE status='blocked'"),
        }
