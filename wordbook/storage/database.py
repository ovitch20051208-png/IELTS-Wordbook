from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
import json
import os
import random
import sqlite3
import uuid

from wordbook.models.card import Card, GRADES, STATUSES, TEXT_FIELDS, normalize_word, normalize_source, now, split_sources, split_tags

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
 id TEXT PRIMARY KEY, word TEXT NOT NULL, word_key TEXT NOT NULL UNIQUE,
 meaning TEXT NOT NULL, ipa TEXT NOT NULL DEFAULT '', example_en TEXT NOT NULL DEFAULT '',
 example_zh TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '',
 tags TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT '未测试' CHECK(status IN ('未测试','已掌握','有一点印象','完全记不得')),
 review_count INTEGER NOT NULL DEFAULT 0 CHECK(review_count >= 0), last_reviewed_at TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS idx_cards_source ON cards(source);
CREATE INDEX IF NOT EXISTS idx_cards_priority ON cards(priority);
CREATE TABLE IF NOT EXISTS review_sessions (
 id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
 mode TEXT NOT NULL, total INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS review_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 word_id TEXT REFERENCES cards(id) ON DELETE SET NULL, word_snapshot TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('未测试','已掌握','有一点印象','完全记不得')),
 reviewed_at TEXT NOT NULL, session_id TEXT REFERENCES review_sessions(id),
 origin TEXT NOT NULL DEFAULT 'test', undone_at TEXT,
 previous_status TEXT NOT NULL, previous_count INTEGER NOT NULL, previous_reviewed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_history_word_time ON review_history(word_id, id);
CREATE INDEX IF NOT EXISTS idx_history_session ON review_history(session_id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version=1;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise ValueError("数据库来自更新版本，请升级软件后再打开。")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _card(row) -> Card:
        return Card(**{k: v for k, v in dict(row).items() if k != "word_key"})

    def get(self, word_id: str) -> Card:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id=?", (word_id,)).fetchone()
        if row is None:
            raise ValueError("该词卡已经不存在。")
        return self._card(row)

    def list_cards(self, search="", status="", source="", priority="", tag="") -> list[Card]:
        clauses, args = [], []
        if status:
            clauses.append("status=?")
            args.append(status)
        if priority:
            clauses.append("priority=?")
            args.append(priority)
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM cards" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY word_key", args).fetchall()
        cards = [self._card(r) for r in rows]
        query = normalize_word(search)
        return [c for c in cards if (not query or query in normalize_word(c.word + " " + c.meaning))
                and (not source or source in split_sources(c.source))
                and (not tag or tag in split_tags(c.tags))]

    def facets(self):
        cards = self.list_cards()
        return {"source": sorted({s for c in cards for s in split_sources(c.source)}),
                "tag": sorted({t for c in cards for t in split_tags(c.tags)}),
                "priority": sorted({c.priority for c in cards if c.priority})}

    def stats(self):
        with self.connection() as conn:
            counts = {r[0]: r[1] for r in conn.execute("SELECT status,COUNT(*) FROM cards GROUP BY status")}
            latest = conn.execute("SELECT MAX(reviewed_at) FROM review_history WHERE undone_at IS NULL AND origin='test'").fetchone()[0]
        return {"全部": sum(counts.values()), **{s: counts.get(s, 0) for s in STATUSES}, "最近测试": latest}

    @staticmethod
    def _insert(conn, card: Card):
        card = replace(card, source=normalize_source(card.source))
        card.validate()
        values = asdict(card)
        values.update(id=card.id or str(uuid.uuid4()), created_at=card.created_at or now(), updated_at=now(), word_key=normalize_word(card.word))
        columns = list(values)
        conn.execute(f"INSERT INTO cards ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [values[k] for k in columns])
        return values["id"]

    def add(self, card: Card) -> str:
        try:
            with self.connection() as conn:
                return self._insert(conn, card)
        except sqlite3.IntegrityError as exc:
            raise ValueError("这个英文单词/短语已存在，请编辑原词卡。") from exc

    def update(self, word_id: str, card: Card):
        card = replace(card, source=normalize_source(card.source))
        card.validate()
        try:
            with self.connection() as conn:
                conn.execute("UPDATE cards SET " + ",".join(f"{f}=?" for f in TEXT_FIELDS) + ",word_key=?,updated_at=? WHERE id=?",
                             [getattr(card, f) for f in TEXT_FIELDS] + [normalize_word(card.word), now(), word_id])
                current = conn.execute("SELECT status FROM cards WHERE id=?", (word_id,)).fetchone()
                if current is None:
                    raise ValueError("该词卡已经不存在。")
                if current[0] != card.status:
                    self._record(conn, word_id, card.status, None, "manual")
        except sqlite3.IntegrityError as exc:
            raise ValueError("这个英文单词/短语已存在，请使用另一个名称。") from exc

    def delete(self, word_id: str):
        with self.connection() as conn:
            # History is deliberately kept, with its immutable word snapshot.
            conn.execute("DELETE FROM cards WHERE id=?", (word_id,))

    @staticmethod
    def _merge(existing: Card, incoming: Card) -> Card:
        data = asdict(existing)
        for name in TEXT_FIELDS:
            if name not in ("word", "source", "tags") and not data[name]:
                data[name] = getattr(incoming, name)
        data["source"] = " | ".join(dict.fromkeys(split_sources(existing.source) + split_sources(incoming.source)))
        data["tags"] = ",".join(dict.fromkeys(split_tags(existing.tags) + split_tags(incoming.tags)))
        return Card(**data)

    @classmethod
    def _import(cls, conn, cards: list[Card], policy: str):
        if policy not in ("merge", "sources", "skip"):
            raise ValueError("未知的导入策略。")
        counts = {"新增": 0, "更新": 0, "重复": 0}
        for card in cards:
            card = replace(card, source=normalize_source(card.source))
            card.validate()
            row = conn.execute("SELECT * FROM cards WHERE word_key=?", (normalize_word(card.word),)).fetchone()
            if row is None:
                cls._insert(conn, card)
                counts["新增"] += 1
            else:
                existing = cls._card(row)
                merged = cls._merge(existing, card) if policy == "merge" else existing
                if policy == "sources":
                    merged = replace(existing,
                        source=" | ".join(dict.fromkeys(split_sources(existing.source) + split_sources(card.source))),
                        tags=",".join(dict.fromkeys(split_tags(existing.tags) + split_tags(card.tags))))
                if any(getattr(existing, f) != getattr(merged, f) for f in TEXT_FIELDS):
                    conn.execute("UPDATE cards SET " + ",".join(f"{f}=?" for f in TEXT_FIELDS) + ",updated_at=? WHERE id=?",
                                 [getattr(merged, f) for f in TEXT_FIELDS] + [now(), existing.id])
                    counts["更新"] += 1
                else:
                    counts["重复"] += 1
        return counts

    def preview_import(self, cards: list[Card], policy="merge"):
        # A private SQLite snapshot makes preview exact, including duplicates INSIDE the file.
        with self.connection() as source:
            memory = sqlite3.connect(":memory:")
            memory.row_factory = sqlite3.Row
            try:
                source.backup(memory)
                return self._import(memory, cards, policy)
            finally:
                memory.close()

    def import_cards(self, cards: list[Card], policy="merge"):
        with self.connection() as conn:
            # Start the write transaction before reading existing keys to serialize writers.
            conn.execute("BEGIN IMMEDIATE")
            return self._import(conn, cards, policy)

    def sample(self, count: int, *, global_random=False, status="", source="", tag="", rng=None):
        candidates = self.list_cards(status="" if global_random else status, source=source, tag=tag)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > len(candidates):
            raise ValueError(f"当前范围最多可抽取 {len(candidates)} 张，请输入 1–{len(candidates)} 的整数。")
        return (rng or random.SystemRandom()).sample(candidates, count)

    def start_session(self, mode: str, total: int) -> str:
        session_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("INSERT INTO review_sessions(id,started_at,mode,total) VALUES (?,?,?,?)", (session_id, now(), mode, total))
        return session_id

    def session_state(self, session_id: str, state: str):
        with self.connection() as conn:
            conn.execute("UPDATE review_sessions SET state=?,ended_at=? WHERE id=?", (state, now() if state in ("completed", "ended", "interrupted") else None, session_id))

    def interrupt_sessions(self):
        with self.connection() as conn:
            conn.execute("UPDATE review_sessions SET state='interrupted',ended_at=? WHERE state IN ('active','paused')", (now(),))

    @staticmethod
    def _record(conn, word_id: str, status: str, session_id: str | None, origin: str):
        if status not in (GRADES if origin == "test" else STATUSES):
            raise ValueError("请选择有效的掌握度。")
        row = conn.execute("SELECT * FROM cards WHERE id=?", (word_id,)).fetchone()
        if row is None:
            raise ValueError("该词卡已经不存在，未保存此次判定。")
        stamp = now()
        cursor = conn.execute("""INSERT INTO review_history(word_id,word_snapshot,status,reviewed_at,session_id,origin,previous_status,previous_count,previous_reviewed_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (word_id, row["word"], status, stamp, session_id, origin, row["status"], row["review_count"], row["last_reviewed_at"]))
        conn.execute("UPDATE cards SET status=?,review_count=review_count+?,last_reviewed_at=?,updated_at=? WHERE id=?",
                     (status, int(status != "未测试"), stamp, stamp, word_id))
        return cursor.lastrowid

    def record(self, word_id: str, status: str, session_id: str | None = None, origin="test") -> int:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self._record(conn, word_id, status, session_id, origin)

    def undo(self, history_id: int, session_id: str):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM review_history WHERE id=? AND session_id=? AND undone_at IS NULL", (history_id, session_id)).fetchone()
            if row is None or row["word_id"] is None:
                raise ValueError("此次判定无法撤销。")
            latest = conn.execute("SELECT MAX(id) FROM review_history WHERE word_id=? AND undone_at IS NULL", (row["word_id"],)).fetchone()[0]
            if latest != history_id:
                raise ValueError("此词已有更新的学习记录，不能撤销旧判定。")
            conn.execute("UPDATE review_history SET undone_at=? WHERE id=?", (now(), history_id))
            conn.execute("UPDATE cards SET status=?,review_count=?,last_reviewed_at=?,updated_at=? WHERE id=?",
                         (row["previous_status"], row["previous_count"], row["previous_reviewed_at"], now(), row["word_id"]))

    def history(self, word_id=None):
        with self.connection() as conn:
            return [dict(r) for r in conn.execute("""SELECT h.*,s.mode FROM review_history h LEFT JOIN review_sessions s ON h.session_id=s.id"""
                + (" WHERE h.word_id=?" if word_id else "") + " ORDER BY h.id DESC", (word_id,) if word_id else ())]

    def sessions(self):
        with self.connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM review_sessions ORDER BY started_at DESC")]

    def setting(self, key, default=None):
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as conn:
            conn.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, ensure_ascii=False)))

    def backup(self, destination: str | Path):
        destination = Path(destination).resolve()
        if destination == self.path:
            raise ValueError("备份文件不能是正在使用的数据文件。")
        staging = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with self.connection() as source:
                target = sqlite3.connect(staging)
                try:
                    source.backup(target)
                    target.execute("PRAGMA journal_mode=DELETE")
                finally:
                    target.close()
            os.replace(staging, destination)
        finally:
            if staging.exists():
                staging.unlink()

    def restore(self, source: str | Path) -> Path:
        source = Path(source).resolve()
        if source == self.path:
            raise ValueError("不能从正在使用的数据文件恢复。")
        # Validate an immutable, read-only source before touching the live database.
        incoming = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        incoming.row_factory = sqlite3.Row
        try:
            if incoming.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("备份文件完整性检查未通过。")
            if incoming.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("这不是兼容的 IELTS Wordbook 完整备份（需要版本 1）。")
            required = {"cards", "review_history", "review_sessions", "settings"}
            tables = {r[0] for r in incoming.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables or incoming.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("备份缺少必要数据表或历史关联损坏。")
            # Check all expected columns, card data and normalized unique keys.
            expected = {"cards": set(asdict(Card("a", "b"))) | {"word_key"},
                        "review_history": {"id", "word_id", "word_snapshot", "status", "reviewed_at", "session_id", "origin", "undone_at", "previous_status", "previous_count", "previous_reviewed_at"},
                        "review_sessions": {"id", "started_at", "ended_at", "mode", "total", "state"}, "settings": {"key", "value"}}
            for table, names in expected.items():
                if {r[1] for r in incoming.execute(f"PRAGMA table_info({table})")} != names:
                    raise ValueError(f"备份的 {table} 表结构不兼容。")
            keys = set()
            for row in incoming.execute("SELECT * FROM cards"):
                self._card(row).validate()
                if row["word_key"] != normalize_word(row["word"]) or row["word_key"] in keys:
                    raise ValueError("备份含有损坏或重复的英文词卡。")
                keys.add(row["word_key"])
            for row in incoming.execute("SELECT value FROM settings"):
                json.loads(row[0])
            safety = self.path.with_name("before_restore_" + uuid.uuid4().hex[:12] + ".db")
            self.backup(safety)
            # SQLite backup API also handles the live WAL safely; no raw .db copying.
            with self.connection() as target:
                incoming.backup(target)
            return safety
        except sqlite3.DatabaseError as exc:
            raise ValueError("文件不是有效的 IELTS Wordbook SQLite 备份。") from exc
        finally:
            incoming.close()
