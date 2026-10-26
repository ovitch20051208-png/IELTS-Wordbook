"""Offline pronunciation additions and compact-source migration, with a safety backup."""
from functools import lru_cache
import json
from pathlib import Path
import uuid

from wordbook.models.card import normalize_source, normalize_word, now


@lru_cache(maxsize=1)
def pronunciation_catalog():
    path = Path(__file__).resolve().parent.parent / "data" / "ipa_en_gb.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["entries"]


def ipa_reference(word: str, ipa=None) -> str:
    entry = pronunciation_catalog().get(normalize_word(word))
    if not entry or (ipa is not None and ipa != entry["ipa"]):
        return "导入文件或手动填写的英式音标。"
    method = {"dictionary": "英式词典读音", "phrase": "英式词音组合的短语参考读法；实际弱读和重音随语境变化",
              "adapted": "根据词典的词干、词形或重音整理的参考读法"}[entry["kind"]]
    return method + "\n" + entry.get("note", "") + "\n" + "\n".join(entry["sources"])


def upgrade_catalog(db, entries=None):
    """Only fill empty IPA and normalize source. Never touch learning state/history."""
    entries = pronunciation_catalog() if entries is None else entries

    def changes(rows):
        for row in rows:
            entry = entries.get(normalize_word(row["word"]))
            ipa = row["ipa"] or (entry["ipa"] if entry else "")
            source = normalize_source(row["source"])
            if ipa != row["ipa"] or source != row["source"]:
                yield row, ipa, source

    with db.connection() as conn:
        pending = list(changes(conn.execute("SELECT id,word,ipa,source FROM cards").fetchall()))
    if not pending:
        return {"ipa_filled": 0, "sources_shortened": 0, "backup": None}
    backup = db.path.with_name("before_v1_1_content_" + uuid.uuid4().hex[:12] + ".db")
    db.backup(backup)
    result = {"ipa_filled": 0, "sources_shortened": 0, "backup": str(backup)}
    with db.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id,word,ipa,source FROM cards").fetchall()
        for row, ipa, source in changes(rows):
            result["ipa_filled"] += int(ipa != row["ipa"])
            result["sources_shortened"] += int(source != row["source"])
            conn.execute("UPDATE cards SET ipa=?,source=?,updated_at=? WHERE id=?", (ipa, source, now(), row["id"]))
    return result
