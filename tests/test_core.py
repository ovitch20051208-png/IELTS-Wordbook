import os
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from wordbook.models.card import Card, STATUSES, GRADES, TEXT_FIELDS, normalize_word
from wordbook.importer.txt import parse_file, parse_text, export_text
from wordbook.storage.database import Database
from wordbook.services.review import ReviewSession
from wordbook.paths import data_directory, bundled_wordlist
from tests.fixtures import sample_cards, sample_text

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / ".test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.folder = Path(self.temp.name)
        self.db = Database(self.folder / "wordbook.db")

    def tearDown(self):
        self.temp.cleanup()

    def fixture_cards(self):
        return sample_cards()

    def imported(self):
        self.db.import_cards(self.fixture_cards())
        return self.db.list_cards()


class ImportTests(DatabaseCase):
    def test_generated_preview_import_and_every_field(self):
        result = parse_text(sample_text())
        self.assertEqual(result.errors, [])
        self.assertEqual(result.total, 160)
        self.assertEqual(len({normalize_word(c.word) for c in result.cards}), 160)
        self.assertEqual(self.db.preview_import(result.cards), {"新增": 160, "更新": 0, "重复": 0})
        self.assertEqual(self.db.stats()["全部"], 0)
        self.assertEqual(self.db.import_cards(result.cards)["新增"], 160)
        actual = {normalize_word(c.word): c for c in self.db.list_cards()}
        for card in result.cards:
            saved = actual[normalize_word(card.word)]
            for field in TEXT_FIELDS:
                self.assertEqual(getattr(saved, field), getattr(card, field), (card.word, field))
            self.assertEqual(saved.status, "未测试")
            self.assertTrue(saved.id)
        self.assertEqual(self.db.stats()["未测试"], 160)

    def test_repeat_generated_import_zero_and_preserves_learning(self):
        card = self.imported()[0]
        self.db.record(card.id, "已掌握")
        old = self.db.get(card.id)
        self.assertEqual(self.db.import_cards(self.fixture_cards()), {"新增": 0, "更新": 0, "重复": 160})
        self.assertEqual(self.db.get(card.id), old)
        self.assertEqual(len(self.db.history()), 1)

    def test_utf8_bom_chinese_ipa_punctuation_and_colon(self):
        path = self.folder / "中文.txt"
        path.write_text("# IELTS-VOCAB/1\n=== CARD ===\nmeaning: 毛巾：擦脸用\nword: towel\nipa: /ˈtaʊəl/\nexample_en: Time: bring a towel.\ntags: 听力，易听错\n", encoding="utf-8-sig")
        result = parse_file(path)
        self.assertFalse(result.errors)
        self.assertEqual(result.cards[0].meaning, "毛巾：擦脸用")
        self.assertEqual(result.cards[0].ipa, "/ˈtaʊəl/")
        self.assertEqual(result.cards[0].example_en, "Time: bring a towel.")
        self.assertEqual(result.cards[0].tags, "听力,易听错")

    def test_dedup_whitespace_and_case(self):
        cards = [Card(" Beyond   one's means ", "超出经济能力"), Card("bEYOND one's\tmeans", "另一义")]
        self.assertEqual(self.db.preview_import(cards), {"新增": 1, "更新": 0, "重复": 1})
        self.assertEqual(self.db.import_cards(cards), {"新增": 1, "更新": 0, "重复": 1})
        self.assertEqual(self.db.stats()["全部"], 1)

    def test_merge_preserves_nonempty_and_unions_source_tags(self):
        key = self.db.add(Card("amass", "人工编辑", source="甲", tags="阅读", note="我的备注"))
        self.db.record(key, "完全记不得")
        counts = self.db.import_cards([Card("AMASS", "不应覆盖", ipa="/test/", source="乙", tags="阅读,五星阅读词", note="不应覆盖")])
        card = self.db.get(key)
        self.assertEqual(counts["更新"], 1)
        self.assertEqual((card.meaning, card.note, card.ipa), ("人工编辑", "我的备注", "/test/"))
        self.assertEqual(card.source, "甲 | 乙")
        self.assertEqual(card.tags, "阅读,五星阅读词")
        self.assertEqual(card.status, "完全记不得")
        self.assertTrue(card.focus)
        self.assertEqual(len(self.db.list_cards(source="乙", tag="五星阅读词")), 1)

    def test_skip_policy(self):
        key = self.db.add(Card("word", "中文"))
        before = self.db.get(key)
        self.assertEqual(self.db.import_cards([Card("WORD", "新中文", ipa="/x/", source="新来源")], "skip")["重复"], 1)
        self.assertEqual(self.db.get(key), before)

    def test_errors_keep_valid_cards_and_report_lines(self):
        result = parse_text("garbage\n=== CARD ===\nword: valid\nmeaning: 有效\n=== CARD ===\nword: missing\n=== CARD ===\nword: broken\nmeaning: 解释\nunknown: value\n=== CARD ===\nword: final\nmeaning: 最后\n")
        self.assertEqual(result.total, 4)
        self.assertEqual([c.word for c in result.cards], ["valid", "final"])
        self.assertEqual(len(result.errors), 3)
        self.assertIn("第 1 行", result.errors[0])
        self.assertIn("meaning", result.errors[1])
        self.assertIn("第 10 行", result.errors[2])
        self.db.import_cards(result.cards)
        self.assertEqual(self.db.stats()["全部"], 2)

    def test_duplicate_field_and_missing_colon(self):
        result = parse_text("=== CARD ===\nword: a\nword: b\nmeaning: 中\ninvalid\n")
        self.assertEqual(len(result.cards), 0)
        self.assertIn("重复", result.errors[0])
        self.assertIn("冒号", result.errors[0])

    def test_empty_and_wrong_encoding(self):
        self.assertTrue(parse_text("# empty\n").errors)
        path = self.folder / "bad.txt"
        path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            parse_file(path)

    def test_transaction_rolls_back_all_on_invalid_card(self):
        with self.assertRaises(ValueError):
            self.db.import_cards([Card("good", "好"), Card("bad", "")])
        self.assertEqual(self.db.stats()["全部"], 0)

    def test_txt_roundtrip_all_fields(self):
        original = self.imported()
        exported = parse_text(export_text(original))
        self.assertFalse(exported.errors)
        self.assertEqual(len(exported.cards), 160)
        other = Database(self.folder / "other.db")
        other.import_cards(exported.cards)
        for a, b in zip(original, other.list_cards()):
            for field in TEXT_FIELDS:
                self.assertEqual(getattr(a, field), getattr(b, field))

    def test_5000_cards_and_no_repeat(self):
        cards = [Card(f"word {i}", f"解释 {i}", source="大词库", tags="阅读") for i in range(5000)]
        self.assertEqual(self.db.import_cards(cards)["新增"], 5000)
        self.assertEqual(len(self.db.list_cards()), 5000)
        self.assertEqual(len({c.id for c in self.db.sample(5000, global_random=True)}), 5000)
        self.assertEqual(self.db.import_cards(cards)["新增"], 0)

    def test_search_facets_and_phrases(self):
        self.imported()
        for phrase in ("one-sided", "someone's book", "read aloud", "listen to"):
            self.db.add(Card(phrase, "短语测试"))
            self.assertTrue(self.db.list_cards(search=phrase), phrase)
        self.assertEqual(self.db.list_cards(search="测试释义 10")[0].word, "test word 010")
        self.assertTrue(self.db.list_cards(priority="A", tag="测试重点"))
        self.assertIn("测试标签", self.db.facets()["tag"])


class ReviewTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.cards = self.imported()

    def test_ten_untested_three_grades_saved_immediately(self):
        session = ReviewSession(self.db, self.db.sample(10, status="未测试"))
        for i in range(10):
            session.reveal()
            session.grade(GRADES[i % 3])
            self.assertEqual(len(self.db.history()), i + 1)
        self.assertEqual(self.db.stats()["未测试"], 150)
        self.assertEqual([self.db.stats()[s] for s in GRADES], [4, 3, 3])
        self.assertIsNone(session.current)
        self.assertEqual(session.summary()["未作答"], 0)
        self.assertEqual(self.db.sessions()[0]["state"], "completed")

    def test_known_becomes_forgotten_history_survives(self):
        card = self.cards[0]
        self.db.record(card.id, "已掌握")
        self.db.record(card.id, "完全记不得")
        self.assertEqual(self.db.get(card.id).status, "完全记不得")
        self.assertEqual(self.db.stats()["已掌握"], 0)
        self.assertEqual(self.db.stats()["完全记不得"], 1)
        self.assertEqual([h["status"] for h in self.db.history(card.id)], ["完全记不得", "已掌握"])

    def test_global_random_ignores_status_contains_four_categories(self):
        for card, grade in zip(self.cards[:3], GRADES):
            self.db.record(card.id, grade)
        selected = self.db.sample(160, global_random=True, status="未测试", rng=random.Random(42))
        self.assertEqual({c.status for c in selected}, set(STATUSES))
        self.assertEqual(len({c.id for c in selected}), 160)
        known = next(c for c in selected if c.status == "已掌握")
        session = ReviewSession(self.db, [known])
        session.reveal()
        session.grade("完全记不得")
        self.assertEqual(self.db.get(known.id).status, "完全记不得")

    def test_source_tag_range_and_insufficient_count(self):
        selected = self.db.sample(5, status="未测试", source="剑21T1", tag="阅读")
        self.assertTrue(all(c.source == "剑21T1" and "阅读" in c.tags for c in selected))
        for count in (0, -1, 161, True):
            with self.assertRaisesRegex(ValueError, "160"):
                self.db.sample(count)

    def test_direct_front_grade_allowed_but_paused_and_invalid_rejected(self):
        session = ReviewSession(self.db, self.cards[:2])
        first = session.current.id
        session.grade("已掌握")
        self.assertEqual(self.db.get(first).status, "已掌握")
        session.toggle_pause()
        with self.assertRaises(ValueError):
            session.grade("已掌握")
        session.skip()
        self.assertEqual(session.index, 1)
        session.toggle_pause()
        with self.assertRaises(ValueError):
            session.grade("未测试")
        self.assertEqual(len(self.db.history()), 1)

    def test_flip_and_skip_dont_mark_tested(self):
        session = ReviewSession(self.db, self.cards[:2])
        session.reveal()
        self.assertEqual(len(self.db.history()), 0)
        session.skip()
        self.assertEqual(self.db.get(self.cards[0].id).status, "未测试")
        self.assertEqual(len(self.db.history()), 0)
        self.assertEqual(session.summary()["跳过"], 1)

    def test_undo_restores_status_count_time_and_keeps_audit(self):
        card = self.cards[0]
        self.db.record(card.id, "已掌握")
        before = self.db.get(card.id)
        session = ReviewSession(self.db, [before])
        session.reveal()
        session.grade("完全记不得")
        session.undo()
        after = self.db.get(card.id)
        self.assertEqual((after.status, after.review_count, after.last_reviewed_at), (before.status, before.review_count, before.last_reviewed_at))
        self.assertIsNotNone(session.current)
        self.assertTrue(session.revealed)
        history = self.db.history(card.id)
        self.assertEqual(len(history), 2)
        self.assertTrue(history[0]["undone_at"])
        session.grade("有一点印象")
        self.assertEqual(self.db.get(card.id).status, "有一点印象")

    def test_undo_cannot_clobber_newer_manual_change(self):
        session = ReviewSession(self.db, self.cards[:2])
        session.reveal()
        card_id = session.current.id
        session.grade("已掌握")
        card = self.db.get(card_id)
        card.status = "完全记不得"
        self.db.update(card_id, card)
        with self.assertRaisesRegex(ValueError, "更新"):
            session.undo()
        self.assertEqual(self.db.get(card_id).status, "完全记不得")

    def test_state_history_ids_persist_on_restart(self):
        card = self.cards[0]
        self.db.record(card.id, "有一点印象")
        reopened = Database(self.db.path)
        self.assertEqual(reopened.get(card.id).status, "有一点印象")
        self.assertEqual(reopened.get(card.id).review_count, 1)
        self.assertEqual(len(reopened.history(card.id)), 1)

    def test_delete_preserves_history_snapshot(self):
        card = self.cards[0]
        self.db.record(card.id, "已掌握")
        self.db.delete(card.id)
        self.assertEqual(self.db.history()[0]["word_snapshot"], card.word)
        self.assertIsNone(self.db.history()[0]["word_id"])
        self.assertEqual(self.db.stats()["全部"], 159)

    def test_manual_state_updates_are_recorded(self):
        card = self.cards[0]
        card.meaning = "人工释义"
        card.status = "完全记不得"
        self.db.update(card.id, card)
        card.status = "未测试"
        self.db.update(card.id, card)
        self.assertEqual(self.db.get(card.id).meaning, "人工释义")
        self.assertEqual(self.db.stats()["未测试"], 160)
        self.assertEqual(len(self.db.history(card.id)), 2)
        self.assertTrue(all(h["origin"] == "manual" for h in self.db.history(card.id)))

    def test_interruption_keeps_completed_grades(self):
        session = ReviewSession(self.db, self.cards[:3])
        session.reveal()
        session.grade("已掌握")
        self.db.interrupt_sessions()
        self.assertEqual(self.db.sessions()[0]["state"], "interrupted")
        self.assertEqual(self.db.stats()["已掌握"], 1)


class BackupTests(DatabaseCase):
    def test_full_backup_restore_ids_settings_history_and_safety_copy(self):
        card = self.imported()[0]
        session = ReviewSession(self.db, [card])
        session.reveal()
        session.grade("有一点印象")
        self.db.set_setting("tts_repeat", 3)
        self.db.set_setting("tts_speed", 0.8)
        backup = self.folder / "完整备份.db"
        self.db.backup(backup)
        self.db.delete(card.id)
        self.db.set_setting("tts_repeat", 1)
        safety = self.db.restore(backup)
        self.assertTrue(safety.exists())
        self.assertEqual(self.db.stats()["全部"], 160)
        self.assertEqual(self.db.get(card.id).status, "有一点印象")
        self.assertEqual(self.db.history()[0]["session_id"], session.id)
        self.assertEqual(self.db.setting("tts_repeat"), 3)
        self.assertEqual(self.db.setting("tts_speed"), 0.8)
        self.assertEqual(Database(safety).stats()["全部"], 159)

    def test_invalid_restore_does_not_touch_live_database(self):
        self.imported()
        invalid = self.folder / "bad.db"
        invalid.write_text("not sqlite", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.db.restore(invalid)
        self.assertEqual(self.db.stats()["全部"], 160)

    def test_foreign_database_and_self_backup_rejected(self):
        foreign = self.folder / "foreign.db"
        conn = sqlite3.connect(foreign)
        try:
            conn.execute("CREATE TABLE unrelated(id INTEGER)")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ValueError):
            self.db.restore(foreign)
        with self.assertRaises(ValueError):
            self.db.backup(self.db.path)
        with self.assertRaises(ValueError):
            self.db.restore(self.db.path)


class PathTests(unittest.TestCase):
    def test_windows_local_appdata_location(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(ROOT / "fake_local"), "IELTS_WORDBOOK_DATA_DIR": ""}):
            self.assertEqual(data_directory(), ROOT / "fake_local" / "IELTSWordbook")
        self.assertTrue(bundled_wordlist().exists())
