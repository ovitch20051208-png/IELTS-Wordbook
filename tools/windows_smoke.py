r"""Real Windows/Qt + SAPI smoke check, with isolated data and optional audible speech.

Run: .venv\Scripts\python.exe tools\windows_smoke.py [--audio]
This tool never writes the user's %LOCALAPPDATA% learning database.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "windows"

from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from wordbook.importer.txt import parse_file
from wordbook.storage.database import Database
from wordbook.services.tts import SpeechService
from wordbook.ui.main_window import MainWindow
from wordbook.paths import bundled_wordlist
from wordbook.services.catalog import upgrade_catalog


def main():
    artifacts = ROOT / ".test-artifacts"
    artifacts.mkdir(exist_ok=True)
    folder = artifacts / "windows-smoke"
    folder.mkdir(exist_ok=True)
    db = Database(folder / "wordbook.db")
    upgrade_catalog(db)
    result = parse_file(bundled_wordlist())
    counts = db.import_cards(result.cards)
    app = QApplication([])
    speech = SpeechService()
    window = MainWindow(db, speech)
    window.show()
    report = {"platform": sys.platform, "cards": db.stats()["全部"], "import": counts,
              "errors": result.errors, "tts_errors": [], "screenshots": []}
    speech.error.connect(report["tts_errors"].append)

    def snapshot(name):
        app.processEvents()
        path = artifacts / ("windows_" + name + ".png")
        if not window.grab().save(str(path)):
            raise RuntimeError("Screenshot save failed")
        report["screenshots"].append(path.name)

    def exercise():
        try:
            snapshot("home")
            window.tabs.setCurrentIndex(1)
            snapshot("library")
            window.tabs.setCurrentIndex(4)
            snapshot("settings")
            report["voices"] = [{"name": voice.name, "languages": voice.languages} for voice in speech.voices]
            report["selected_voice"] = window.voice_label.text()
            page = window.review
            window.tabs.setCurrentIndex(2)
            page.count.setValue(8)
            page.start(False)
            page.session.cards[0] = db.list_cards(search="apple")[0]
            page.render()
            snapshot("front")
            report["word_pos_visible"] = page.pos_label.isVisible() and page.pos_label.text() == "n."
            if "--audio" in sys.argv:
                page.word_speaker.click()
                for _ in range(30):
                    app.processEvents()
                    time.sleep(0.1)
            page.flip()
            snapshot("back")
            if "--audio" in sys.argv:
                speech.speed, speech.repeat = 0.8, 2
                page.example_speaker.click()
                for _ in range(75):
                    app.processEvents()
                    time.sleep(0.1)
            page.flip()  # Return to the front, as in the reported screenshot.
            checks = []
            for revealed in (False, True):
                for i, grade in enumerate(("已掌握", "有一点印象", "完全记不得")):
                    if revealed:
                        page.flip()
                    card_id, position = page.session.current.id, page.session.index
                    QTest.mouseClick(page.grade_buttons[i], Qt.MouseButton.LeftButton)
                    app.processEvents()
                    ok = page.session.index == position + 1 and db.get(card_id).status == grade
                    checks.append({"side": "back" if revealed else "front", "grade": grade, "advanced_and_saved": ok})
                    if not ok:
                        raise AssertionError("Grade button failed")
            report["grade_button_checks"] = checks
            for _ in checks:
                page.undo()
            report["all_ipa_filled"] = all(card.ipa for card in db.list_cards())
            report["all_pos_filled"] = all(card.pos for card in db.list_cards())
            page.session.end()
            report["success"] = (db.stats()["全部"] == 8 and report["all_ipa_filled"]
                                 and report["all_pos_filled"] and report["word_pos_visible"] and not report["tts_errors"])
        except Exception as exc:
            report["success"] = False
            report["error"] = repr(exc)
            import traceback
            traceback.print_exc()
        finally:
            speech.close()
            window.close()
            output = artifacts / "windows_smoke_report.json"
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=True, indent=2))
            app.quit()

    QTimer.singleShot(1200, exercise)
    app.exec()
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
