from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wordbook.importer.txt import parse_file, parse_text, export_text
from wordbook.models.card import Card, normalize_source, split_sources
from wordbook.services.catalog import pronunciation_catalog, upgrade_catalog, ipa_reference
from wordbook.storage.database import Database
from wordbook.paths import bundled_wordlist
from tests.fixtures import sample_cards

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / ".test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)


class V11Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.db = Database(Path(self.temp.name) / "wordbook.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_compact_source_variants_and_multiple_source_dedup(self):
        for value in ("剑21 Test 1 听力 Part 1", "剑21 Test 1 阅读 Passage 3", "剑21 T1", "剑桥雅思21 Test 1", "Cambridge IELTS 21 Test 1", "剑21T1"):
            self.assertEqual(normalize_source(value), "剑21T1")
        source = "剑21 Test 1 阅读 Passage 2|剑20T3；剑21T1,旧雅思词库"
        self.assertEqual(split_sources(source), ["剑21T1", "剑20T3", "旧雅思词库"])

    def test_cross_book_import_appends_sources_preserves_every_learning_field(self):
        key = self.db.add(Card("amass", "人工释义", ipa="/əˈmæs/", source="剑21 Test 1 阅读 Passage 1", note="人工备注"))
        session = self.db.start_session("test", 1)
        self.db.record(key, "已掌握", session)
        before = self.db.get(key)
        history = self.db.history()
        incoming = Card("AMASS", "不能覆盖", source="剑20 Test 3 听力 Part 2", tags="高频")
        self.assertEqual(self.db.preview_import([incoming]), {"新增": 0, "更新": 1, "重复": 0})
        self.assertEqual(self.db.import_cards([incoming])["更新"], 1)
        actual = self.db.get(key)
        self.assertEqual(actual.source, "剑21T1 | 剑20T3")
        for field in ("id", "word", "meaning", "ipa", "status", "review_count", "last_reviewed_at", "created_at", "note"):
            self.assertEqual(getattr(actual, field), getattr(before, field))
        self.assertEqual(self.db.history(), history)
        self.assertEqual(self.db.import_cards([incoming]), {"新增": 0, "更新": 0, "重复": 1})
        self.assertEqual(self.db.stats()["全部"], 1)
        self.assertEqual(len(self.db.list_cards(source="剑20T3")), 1)

    def test_source_only_policy_still_appends_new_source(self):
        key = self.db.add(Card("amass", "积累", source="剑21T1"))
        self.db.import_cards([Card("amass", "其他", ipa="/əˈmæs/", source="剑19 Test 4 阅读 Passage 3")], "sources")
        actual = self.db.get(key)
        self.assertEqual(actual.source, "剑21T1 | 剑19T4")
        self.assertEqual(actual.ipa, "")
        self.assertEqual(actual.meaning, "积累")

    def test_v2_rejects_missing_ipa_and_source_but_keeps_good_cards(self):
        text = ("# IELTS-VOCAB/2\n=== CARD ===\nword: bad\nmeaning: 缺音标\nsource: 剑21T1\n"
                "=== CARD ===\nword: good\nmeaning: 好的\nipa: /ɡʊd/\nsource: 剑20 Test 3 听力 Part 1\n"
                "=== CARD ===\nword: no-source\nmeaning: 无来源\nipa: /test/\n")
        result = parse_text(text)
        self.assertEqual([c.word for c in result.cards], ["good"])
        self.assertEqual(result.cards[0].source, "剑20T3")
        self.assertEqual(len(result.errors), 2)
        self.assertIn("ipa", result.errors[0])
        self.assertIn("source", result.errors[1])

    def test_v2_ipa_slashes_and_variant_format(self):
        for ipa, valid in (("无音标", False), ("əˈmæs", False), ("/əˈmæs/", True), ("/a/；/b/", True)):
            result = parse_text(f"# IELTS-VOCAB/2\n=== CARD ===\nword: example\nmeaning: 例子\nipa: {ipa}\nsource: 剑21T1\n")
            self.assertEqual(bool(result.cards), valid)
        self.assertEqual(len(parse_text("# IELTS-VOCAB/1\n=== CARD ===\nword: legacy\nmeaning: 旧格式\n").cards), 1)

    def test_optional_examples_and_empty_pronunciation_catalog(self):
        result = parse_file(bundled_wordlist())
        self.assertEqual(len(result.cards), 8)
        self.assertFalse(result.errors)
        self.assertTrue(all(c.ipa and c.source for c in result.cards))
        self.assertEqual(pronunciation_catalog(), {})
        self.assertIn("手动", ipa_reference("apple", "/manual/"))
        entry = {"ipa": "/test/", "kind": "phrase", "sources": ["https://example.com"], "note": "测试参考"}
        with patch("wordbook.services.catalog.pronunciation_catalog", return_value={"test phrase": entry}):
            self.assertIn("参考读法", ipa_reference("test phrase", "/test/"))
        self.assertEqual(self.db.stats()["全部"], 0)
        self.db.import_cards(result.cards)
        self.assertEqual(self.db.import_cards(result.cards)["新增"], 0)
        self.assertTrue(export_text(self.db.list_cards()).startswith("# IELTS-VOCAB/3"))
        self.assertEqual(len(parse_text(export_text(self.db.list_cards())).cards), 8)

    def test_fresh_start_has_no_words_history_sessions_or_backups(self):
        self.assertEqual(upgrade_catalog(self.db), {"ipa_filled": 0, "sources_shortened": 0, "backup": None})
        self.db.interrupt_sessions()
        self.assertEqual(self.db.stats()["全部"], 0)
        self.assertEqual(self.db.history(), [])
        self.assertEqual(self.db.sessions(), [])
        self.assertEqual(list(self.db.path.parent.glob("before_*.db")), [])
        with self.db.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0], 0)

    def test_content_upgrade_backs_up_and_preserves_history_and_every_other_field(self):
        original = sample_cards()
        entries = {c.word: {"ipa": "/test/"} for c in original}
        self.db.import_cards(original)
        # Simulate an actual v1.0 database with long sources.
        with self.db.connection() as conn:
            conn.execute("UPDATE cards SET source='剑21 Test 1 阅读 Passage 2' WHERE source='剑21T1'")
        first = self.db.list_cards()[0]
        session = self.db.start_session("保留原测试", 10)
        self.db.record(first.id, "完全记不得", session)
        self.db.set_setting("my-setting", "不得覆盖")
        before = {c.id: asdict(c) for c in self.db.list_cards()}
        history, sessions = self.db.history(), self.db.sessions()
        result = upgrade_catalog(self.db, entries=entries)
        self.assertEqual(result["ipa_filled"], 80)
        self.assertEqual(result["sources_shortened"], 80)
        self.assertTrue(Path(result["backup"]).exists())
        backup = Database(result["backup"])
        self.assertEqual({c.id: asdict(c) for c in backup.list_cards()}, before)
        for card in self.db.list_cards():
            self.assertTrue(card.ipa)
            for field, value in asdict(card).items():
                if field not in ("ipa", "source", "updated_at"):
                    self.assertEqual(value, before[card.id][field], field)
        self.assertEqual(self.db.history(), history)
        self.assertEqual(self.db.sessions(), sessions)
        self.assertEqual(self.db.setting("my-setting"), "不得覆盖")
        self.assertIsNone(upgrade_catalog(self.db, entries=entries)["backup"])

    def test_content_upgrade_keeps_manual_nonempty_ipa_and_unknown_words(self):
        key = self.db.add(Card("amass", "积累", ipa="/manual/", source="剑20T3"))
        unknown = self.db.add(Card("unknown custom phrase", "自定义词条", source="自己的笔记"))
        upgrade_catalog(self.db)
        self.assertEqual(self.db.get(key).ipa, "/manual/")
        self.assertEqual(self.db.get(unknown).ipa, "")
