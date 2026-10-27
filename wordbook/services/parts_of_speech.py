"""Offline, context-reviewed POS additions. Phrases deliberately have no POS."""
from functools import lru_cache
import json
from pathlib import Path
import uuid

from wordbook.models.card import is_phrase, normalize_word, normalize_pos


@lru_cache(maxsize=1)
def pos_catalog():
    path = Path(__file__).resolve().parent.parent / "data/pos_catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def fill_missing_pos(db, entries=None):
    entries = pos_catalog() if entries is None else entries

    def changes(cards):
        for card in cards:
            if is_phrase(card.word):
                if card.pos:
                    yield card.id, ""
                continue
            entry = entries.get(normalize_word(card.word))
            if not card.pos and entry and card.meaning == entry["meaning"]:
                yield card.id, normalize_pos(entry["pos"])

    pending = list(changes(db.list_cards()))
    if not pending:
        return {"pos_filled": 0, "phrases_cleared": 0, "backup": None}
    backup = db.path.with_name("before_v1_2_pos_" + uuid.uuid4().hex[:12] + ".db")
    db.backup(backup)
    report = {"pos_filled": 0, "phrases_cleared": 0, "backup": str(backup)}
    from wordbook.storage.database import CARD_SELECT
    with db.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cards = [db._card(row) for row in conn.execute(CARD_SELECT).fetchall()]
        for word_id, pos in changes(cards):
            conn.execute("INSERT INTO card_pos(word_id,pos) VALUES (?,?) ON CONFLICT(word_id) DO UPDATE SET pos=excluded.pos", (word_id, pos))
            report["pos_filled" if pos else "phrases_cleared"] += 1
    return report
