from dataclasses import asdict
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from wordbook.models.card import Card, is_phrase, normalize_pos
from wordbook.paths import bundled_wordlist
from wordbook.importer.txt import parse_file, parse_text, export_text
from wordbook.services.parts_of_speech import fill_missing_pos, pos_catalog
from wordbook.storage.database import Database

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / ".test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)


class PosTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.path = Path(self.temp.name) / "test.db"
        self.db = Database(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_abbreviation_normalization_and_multiple_pos(self):
        for raw, expected in (("动词", "v."), ("NOUN", "n."), ("形容词", "adj."), ("副词", "adv."),
                              ("n./v.", "n.; v."), ("adj.; n.", "adj.; n."), ("v., verb", "v.")):
            self.assertEqual(normalize_pos(raw), expected)
        with self.assertRaises(ValueError):
            normalize_pos("incorrect POS")

    def test_phrases_blank_but_hyphen_and_slash_word_forms_have_pos(self):
        for word in ("coincide with", "art dealer", "worth doing sth"):
            self.assertTrue(is_phrase(word))
            key = self.db.add(Card(word, "词组", pos="v."))
            self.assertEqual(self.db.get(key).pos, "")
            self.assertEqual(self.db.get(key).pos_display, "")
        for word in ("one-sided", "energy-intensive", "stimulus / stimuli"):
            self.assertFalse(is_phrase(word))
        self.assertEqual(Card("newword", "新单词").pos_display, "待补充")

    def test_pos_is_saved_edited_and_preserved_on_repeat_import(self):
        key = self.db.add(Card("amass", "积累", pos="动词", source="剑21T1"))
        self.db.record(key, "已掌握")
        history = self.db.history()
        self.assertEqual(Database(self.path).get(key).pos, "v.")
        self.db.import_cards([Card("AMASS", "新释义", pos="n.", source="剑20T3")])
        actual = self.db.get(key)
        self.assertEqual(actual.pos, "v.")
        self.assertEqual(actual.source, "剑21T1 | 剑20T3")
        actual.pos = "n.; v."
        self.db.update(key, actual)
        self.assertEqual(self.db.get(key).pos, "n.; v.")
        self.assertEqual(self.db.get(key).status, "已掌握")
        self.assertEqual(self.db.history(), history)

    def test_duplicate_import_fills_blank_pos_once(self):
        key = self.db.add(Card("therapeutic", "治疗性的"))
        incoming = Card("therapeutic", "不同内容", pos="adj.")
        self.assertEqual(self.db.preview_import([incoming])["更新"], 1)
        self.db.import_cards([incoming])
        self.assertEqual(self.db.get(key).pos, "adj.")
        self.assertEqual(self.db.import_cards([incoming])["重复"], 1)

    def test_v3_requires_pos_for_single_word_only_and_old_formats_still_work(self):
        text = ("# IELTS-VOCAB/3\n=== CARD ===\nword: amass\nmeaning: 积累\nipa: /əˈmæs/\nsource: 剑21T1\n"
                "=== CARD ===\nword: art dealer\nmeaning: 艺术品交易商\nipa: /ɑːt diːlə/\nsource: 剑21T1\npos:\n"
                "=== CARD ===\nword: good\nmeaning: 好的\nipa: /ɡʊd/\nsource: 剑21T1\npos: 形容词\n")
        result = parse_text(text)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("pos", result.errors[0])
        self.assertEqual([(c.word, c.pos) for c in result.cards], [("art dealer", ""), ("good", "adj.")])
        for header in (1, 2):
            legacy = f"# IELTS-VOCAB/{header}\n=== CARD ===\nword: amass\nmeaning: 积累\nipa: /əˈmæs/\nsource: 剑21T1\n"
            self.assertFalse(parse_text(legacy).errors)

    def test_v3_export_roundtrip_and_phrase_field_stays_blank(self):
        cards = [Card("amass", "积累", ipa="/əˈmæs/", source="剑21T1", pos="v."),
                 Card("art dealer", "艺术品交易商", ipa="/ɑːt diːlə/", source="剑21T1")]
        self.db.import_cards(cards)
        text = export_text(self.db.list_cards())
        self.assertTrue(text.startswith("# IELTS-VOCAB/3"))
        parsed = parse_text(text)
        self.assertFalse(parsed.errors)
        self.assertEqual([(c.word, c.pos) for c in parsed.cards], [(c.word, c.pos) for c in self.db.list_cards()])

    def test_public_catalog_contains_only_optional_examples(self):
        catalog = pos_catalog()
        self.assertEqual(set(catalog), {"apple", "book", "water", "read", "write", "listen", "speak", "learn"})
        self.assertTrue(all(not is_phrase(word) for word in catalog))
        completed = parse_file(bundled_wordlist())
        self.assertFalse(completed.errors)
        self.assertEqual(len(completed.cards), 8)
        self.assertTrue(all(c.pos if not is_phrase(c.word) else not c.pos for c in completed.cards))
        self.assertEqual({c.word: c.pos for c in completed.cards}, {word: entry["pos"] for word, entry in catalog.items()})
        self.assertEqual(self.db.list_cards(), [])

    def test_content_fill_preserves_all_other_card_fields_and_learning_history(self):
        original = parse_file(bundled_wordlist()).cards
        for card in original:
            card.pos = ""
        self.db.import_cards(original)
        first = self.db.list_cards()[0]
        self.db.record(first.id, "有一点印象")
        self.db.set_setting("custom-setting", "保留设置")
        before = {c.id: asdict(c) for c in self.db.list_cards()}
        history = self.db.history()
        result = fill_missing_pos(self.db)
        self.assertEqual(result["pos_filled"], 8)
        self.assertTrue(Path(result["backup"]).exists())
        self.assertEqual({c.id: asdict(c) for c in Database(result["backup"]).list_cards()}, before)
        for card in self.db.list_cards():
            for field, value in asdict(card).items():
                if field != "pos":
                    self.assertEqual(value, before[card.id][field], (card.word, field))
        self.assertEqual(self.db.history(), history)
        self.assertEqual(self.db.setting("custom-setting"), "保留设置")
        self.assertIsNone(fill_missing_pos(self.db)["backup"])

    def test_manual_pos_and_different_meaning_are_not_overwritten(self):
        manual = self.db.add(Card("apple", "苹果", pos="vt."))
        other = self.db.add(Card("book", "预订"))
        self.assertIsNone(fill_missing_pos(self.db)["backup"])
        self.assertEqual(self.db.get(manual).pos, "vt.")
        self.assertEqual(self.db.get(other).pos, "")

    def make_v1_fixture(self):
        key = self.db.add(Card("learn", "学习"))
        self.db.record(key, "完全记不得")
        # An isolated test database simulates the previous release's exact schema.
        with self.db.connection() as conn:
            conn.execute("DROP TABLE card_pos")
            conn.execute("PRAGMA user_version=1")
        return key

    def test_v1_schema_migration_backs_up_and_old_card_queries_remain_compatible(self):
        key = self.make_v1_fixture()
        conn = sqlite3.connect(self.path)
        try:
            columns_before = [d[0] for d in conn.execute("SELECT * FROM cards").description]
        finally:
            conn.close()
        migrated = Database(self.path)
        self.assertTrue(migrated.schema_backup.exists())
        conn = sqlite3.connect(migrated.schema_backup)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        finally:
            conn.close()
        with migrated.connection() as conn:
            self.assertEqual([d[0] for d in conn.execute("SELECT * FROM cards").description], columns_before)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(migrated.get(key).status, "完全记不得")
        self.assertEqual(len(migrated.history()), 1)

    def test_v1_backup_restores_and_upgrades_without_losing_history(self):
        key = self.make_v1_fixture()
        legacy = Path(self.temp.name) / "legacy.db"
        self.db.backup(legacy)
        destination = Database(Path(self.temp.name) / "restored.db")
        destination.restore(legacy)
        self.assertEqual(destination.get(key).status, "完全记不得")
        self.assertEqual(len(destination.history()), 1)
        fill_missing_pos(destination)
        self.assertEqual(destination.get(key).pos, "v.")

    def test_v2_backup_retains_pos_and_delete_cascades_only_pos_metadata(self):
        key = self.db.add(Card("amass", "积累", pos="v."))
        self.db.record(key, "已掌握")
        backup = Path(self.temp.name) / "full.db"
        self.db.backup(backup)
        self.db.delete(key)
        with self.db.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM card_pos").fetchone()[0], 0)
        self.assertEqual(len(self.db.history()), 1)
        self.db.restore(backup)
        self.assertEqual(self.db.get(key).pos, "v.")
        self.assertEqual(self.db.get(key).status, "已掌握")

    def test_fresh_start_does_not_seed_words_or_create_upgrade_backups(self):
        self.assertIsNone(self.db.schema_backup)
        self.assertEqual(fill_missing_pos(self.db), {"pos_filled": 0, "phrases_cleared": 0, "backup": None})
        self.assertEqual(self.db.list_cards(), [])
        self.assertEqual(self.db.history(), [])
        self.assertEqual(self.db.sessions(), [])
        self.assertEqual(list(self.path.parent.glob("before_*.db")), [])

    def test_sources_only_import_does_not_fill_or_change_pos(self):
        key = self.db.add(Card("book", "书", source="甲"))
        self.db.import_cards([Card("BOOK", "书", pos="n.", source="乙")], "sources")
        self.assertEqual(self.db.get(key).pos, "")
        self.assertEqual(self.db.get(key).source, "甲 | 乙")

    def test_invalid_pos_backup_is_rejected_without_changing_current_data(self):
        key = self.db.add(Card("book", "书", pos="n."))
        backup = self.path.with_name("invalid_pos.db")
        self.db.backup(backup)
        with closing(sqlite3.connect(backup)) as conn:
            conn.execute("UPDATE card_pos SET pos='invalid'")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "词性"):
            self.db.restore(backup)
        self.assertEqual(self.db.get(key).pos, "n.")
