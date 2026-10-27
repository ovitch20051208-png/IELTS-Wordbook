import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from wordbook.importer.txt import parse_file, parse_text
from wordbook.storage.database import Database
from wordbook.models.card import Card
from wordbook.services.tts import SpeechService, Voice, preferred_voice
from wordbook.ui.main_window import MainWindow
from wordbook.ui.dialogs import CardDialog, ImportPreview
from tests.fixtures import sample_cards, sample_text

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / ".test-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
APP = QApplication.instance() or QApplication([])


class FakeSpeech(QObject):
    voices_changed = Signal(object)
    error = Signal(str)
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.voices = [Voice("us", "US Voice", ("en-US",)), Voice("gb", "GB Voice", ("en-GB",))]
        self.voice_id, self.available, self.speed, self.repeat, self.last_error = "gb", True, 1.0, 1, ""
        self.texts = []

    def speak(self, text):
        self.texts.append(text)
        return self.available

    def stop(self):
        pass

    def close(self):
        pass


class UiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.db = Database(Path(self.temp.name) / "wordbook.db")
        self.db.import_cards(sample_cards())
        self.speech = FakeSpeech()
        self.window = MainWindow(self.db, self.speech)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        if self.window.review.session:
            self.window.review.session.end()
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp.cleanup()

    def start(self):
        page = self.window.review
        self.window.tabs.setCurrentIndex(2)
        page.start(False)
        APP.processEvents()
        return page

    def test_front_hides_meaning_shows_ipa_and_space_grade_shortcuts(self):
        page = self.start()
        self.assertFalse(page.back.isVisible())
        self.assertTrue(page.word_speaker.isVisible())
        self.assertFalse(page.example_speaker.isVisible())
        self.assertTrue(all(control.isEnabled() for control in page.grade_buttons))
        self.assertTrue(page.ipa.isVisible())
        page.setFocus()
        QTest.keyClick(page, Qt.Key.Key_Space)
        APP.processEvents()
        self.assertTrue(page.back.isVisible())
        self.assertTrue(all(control.isEnabled() for control in page.grade_buttons))
        QTest.keyClick(page, Qt.Key.Key_1)
        APP.processEvents()
        self.assertEqual(self.db.stats()["已掌握"], 1)
        self.assertEqual(page.session.index, 1)

    def test_all_three_buttons_really_advance_from_front_and_back(self):
        page = self.start()
        for revealed in (False, True):
            for index, grade in enumerate(("已掌握", "有一点印象", "完全记不得")):
                card_id = page.session.current.id
                previous = page.session.index
                if revealed:
                    page.flip()
                self.assertEqual(page.session.revealed, revealed)
                QTest.mouseClick(page.grade_buttons[index], Qt.MouseButton.LeftButton)
                APP.processEvents()
                self.assertEqual(page.session.index, previous + 1)
                self.assertEqual(self.db.get(card_id).status, grade)
        self.assertEqual(len(self.db.history()), 6)
        self.assertEqual([self.db.stats()[s] for s in ("已掌握", "有一点印象", "完全记不得")], [2, 2, 2])

    def test_two_speakers_pass_distinct_english_and_do_not_flip(self):
        page = self.start()
        card = page.session.current
        QTest.mouseClick(page.word_speaker, Qt.MouseButton.LeftButton)
        self.assertFalse(page.session.revealed)
        self.assertEqual(self.speech.texts[-1], card.word)
        page.flip()
        QTest.mouseClick(page.example_speaker, Qt.MouseButton.LeftButton)
        self.assertEqual(self.speech.texts[-1], card.example_en)
        self.assertNotEqual(self.speech.texts[-2], self.speech.texts[-1])
        self.assertNotIn(card.meaning, self.speech.texts)

    def test_empty_ipa_detail_speakers_and_edit_save(self):
        card = self.db.list_cards(search="test word 000")[0]
        self.assertEqual(card.ipa_display, "音标待补充")
        dialog = CardDialog(self.db, self.speech, card, self.window)
        dialog.show()
        APP.processEvents()
        QTest.mouseClick(dialog.word_speaker, Qt.MouseButton.LeftButton)
        QTest.mouseClick(dialog.example_speaker, Qt.MouseButton.LeftButton)
        self.assertEqual(self.speech.texts[-2:], [card.word, card.example_en])
        dialog.fields["meaning"].setPlainText("新的人工中文释义")
        dialog.status.setCurrentText("完全记不得")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.db.get(card.id).meaning, "新的人工中文释义")
        self.assertEqual(self.db.get(card.id).status, "完全记不得")

    def test_pos_visible_on_word_cards_hidden_on_phrases_and_editable(self):
        key = self.db.add(Card("example", "示例", pos="n."))
        word = self.db.get(key)
        word.pos = "v."
        self.db.update(word.id, word)
        page = self.start()
        page.session.cards[0] = self.db.get(word.id)
        page.render()
        self.assertTrue(page.pos_label.isVisible())
        self.assertEqual(page.pos_label.text(), "v.")
        page.flip()
        self.assertTrue(page.pos_label.isVisible())
        phrase = self.db.list_cards(search="test word 000")[0]
        page.session.cards[0] = phrase
        page.render()
        self.assertFalse(page.pos_label.isVisible())
        dialog = CardDialog(self.db, self.speech, word, self.window)
        dialog.fields["pos"].setCurrentText("n.; v.")
        dialog.save()
        self.assertEqual(self.db.get(word.id).pos, "n.; v.")
        phrase_dialog = CardDialog(self.db, self.speech, phrase, self.window)
        self.assertFalse(phrase_dialog.fields["pos"].isEnabled())
        self.assertEqual(phrase_dialog.value("pos"), "")
        phrase_dialog.reject()

    def test_category_filters_and_counts(self):
        self.db.record(self.db.list_cards()[0].id, "已掌握")
        self.window.refresh()
        self.window.open_category("已掌握")
        self.assertEqual(self.window.library_model.rowCount(), 1)
        self.assertIn("1 张", self.window.stat_buttons["已掌握"].text())
        self.window.clear_filters()
        self.assertEqual(self.window.library_model.rowCount(), 160)

    def test_en_gb_preference_explicit_us_label_speed_and_repeat(self):
        self.assertEqual(self.speech.voice_id, "gb")
        self.window.voice_combo.setCurrentIndex(self.window.voice_combo.findData("us"))
        self.assertIn("en-US", self.window.voice_label.text())
        self.assertIn("不是英式英语", self.window.voice_label.text())
        self.window.speed_combo.setCurrentIndex(1)
        self.window.repeat_spin.setValue(3)
        self.assertEqual((self.speech.speed, self.speech.repeat), (0.8, 3))
        self.assertEqual(self.db.setting("tts_repeat"), 3)

    def test_unavailable_speech_does_not_break_learning(self):
        self.speech.available = False
        self.speech.voices = []
        self.speech.last_error = "本地朗读服务不可用"
        self.window.update_voices([])
        page = self.start()
        page.word_speaker.click()
        page.flip()
        page.grade("已掌握")
        self.assertEqual(self.db.stats()["已掌握"], 1)
        self.assertIn("暂不可用", self.window.voice_label.text())

    def test_saved_voice_survives_delayed_startup_detection(self):
        self.db.set_setting("tts_voice", "us")
        self.window.update_voices([])
        self.assertEqual(self.db.setting("tts_voice"), "us")
        self.window.update_voices(self.speech.voices)
        self.assertEqual(self.speech.voice_id, "us")

    def test_pause_skip_undo_and_result_page(self):
        page = self.start()
        page.pause()
        self.assertFalse(page.word_speaker.isEnabled())
        self.assertFalse(page.back.isVisible())
        page.pause()
        page.flip()
        page.grade("已掌握")
        page.skip()
        page.undo()
        self.assertEqual(page.session.index, 0)
        self.assertEqual(self.db.stats()["已掌握"], 0)
        self.assertEqual(page.session.summary()["跳过"], 0)
        page.session.end()
        page.render()
        self.assertEqual(page.stack.currentWidget(), page.results)

    def test_global_button_ignores_ui_filters(self):
        page = self.window.review
        self.window.tabs.setCurrentIndex(2)
        page.status.setCurrentText("完全记不得")
        page.source.setCurrentIndex(1)
        page.tag.setCurrentIndex(1)
        page.presets.setCurrentText("自定义")
        page.count.setValue(160)
        page.start(True)
        self.assertEqual(len(page.session.cards), 160)
        self.assertEqual(len({c.id for c in page.session.cards}), 160)

    def test_import_preview_counts(self):
        result = parse_text(sample_text())
        dialog = ImportPreview(self.window, result, self.db.preview_import(result.cards))
        self.assertIn("解析 160", dialog.counts.text())
        self.assertIn("预计新增 0", dialog.counts.text())
        self.assertIn("重复/跳过 160", dialog.counts.text())
        dialog.reject()

    def test_custom_count_keyboard_is_not_intercepted_by_grading_shortcuts(self):
        page = self.window.review
        self.window.tabs.setCurrentIndex(2)
        page.presets.setCurrentText("自定义")
        page.count.setFocus()
        page.count.selectAll()
        QTest.keyClicks(page.count, "123")
        self.assertEqual(page.count.value(), 123)

    def test_background_import_preview_confirm_and_repeat_end_to_end(self):
        fixture_path = Path(self.temp.name) / "fixture.txt"
        fixture_path.write_text(sample_text(), encoding="utf-8")
        fresh = Database(Path(self.temp.name) / "fresh.db")
        window = MainWindow(fresh, FakeSpeech())
        window.show()
        APP.processEvents()
        self.assertTrue(window.initial_button.isVisible())
        try:
            with patch.object(ImportPreview, "exec", return_value=QDialog.DialogCode.Accepted), patch.object(QMessageBox, "information"):
                for _ in range(2):
                    window.import_path(fixture_path)
                    deadline = time.monotonic() + 8
                    while (window.jobs or fresh.stats()["全部"] == 0) and time.monotonic() < deadline:
                        APP.processEvents()
                        QTest.qWait(10)
                    self.assertFalse(window.jobs)
                    self.assertEqual(fresh.stats()["全部"], 160)
            self.assertFalse(window.initial_button.isVisible())
        finally:
            window.close()
            window.deleteLater()
            APP.processEvents()

    def test_render_real_gui_screenshots(self):
        self.window.grab().save(str(ARTIFACTS / "home.png"))
        self.window.tabs.setCurrentIndex(1)
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "library.png"))
        page = self.start()
        page.session.cards[0] = self.db.list_cards(search="test word 000")[0]
        page.render()
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "card_front.png"))
        page.flip()
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "card_back.png"))
        self.assertTrue((ARTIFACTS / "card_back.png").exists())


class SpeechTests(unittest.TestCase):
    def test_voice_preference_and_no_english(self):
        us = Voice("us", "American", ("en-US",))
        gb = Voice("gb", "British", ("en-GB",))
        zh = Voice("zh", "Chinese", ("zh-CN",))
        self.assertEqual(preferred_voice([zh, us, gb]), "gb")
        self.assertEqual(preferred_voice([zh, us]), "us")
        self.assertEqual(preferred_voice([zh]), "")

    def test_worker_thread_speed_repeat_new_text_and_cleanup(self):
        calls, event = [], threading.Event()
        parent_thread = threading.get_ident()

        class Backend:
            def voices(self):
                calls.append(("thread", threading.get_ident()))
                return [Voice("gb", "British", ("en-GB",))]

            def speak(self, *args):
                calls.append(("speak", args))
                event.set()

            def stop(self):
                calls.append(("stop",))

            def close(self):
                calls.append(("close",))

        service = SpeechService(backend_factory=Backend)
        deadline = time.monotonic() + 3
        while not service.available and time.monotonic() < deadline:
            time.sleep(0.01)
        try:
            service.speed, service.repeat = 0.8, 3
            self.assertTrue(service.speak("beyond one's means"))
            self.assertTrue(event.wait(2))
            self.assertIn(("speak", ("beyond one's means", "gb", 0.8, 3)), calls)
            self.assertNotEqual(calls[0][1], parent_thread)
            event.clear()
            service.speak("This is the full English example.")
            self.assertTrue(event.wait(2))
            self.assertIn(("speak", ("This is the full English example.", "gb", 0.8, 3)), calls)
        finally:
            service.close()
        self.assertFalse(service._thread.is_alive())
        self.assertEqual(calls[-1], ("close",))

    def test_backend_failure_is_nonfatal(self):
        def fail():
            raise RuntimeError("No installed engine")
        service = SpeechService(backend_factory=fail)
        service._thread.join(2)
        self.assertFalse(service.available)
        self.assertFalse(service.speak("amass"))
        self.assertIn("不可用", service.last_error)
        service.close()
