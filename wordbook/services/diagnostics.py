"""Optional frozen-build check. Only enabled by an explicit developer CLI flag."""
import json
import os
import sys
from PySide6.QtCore import QTimer
from wordbook.importer.txt import parse_file
from wordbook.paths import bundled_wordlist
from wordbook import __version__


def schedule_self_check(app, window, directory):
    if not os.environ.get("IELTS_WORDBOOK_DATA_DIR"):
        raise ValueError("--self-check 需要 IELTS_WORDBOOK_DATA_DIR 指向隔离验收目录。")
    errors = []
    window.speech.error.connect(errors.append)

    def playback():
        window.tabs.setCurrentIndex(4)
        window.speech.speak("The IELTS wordbook is ready.")
        QTimer.singleShot(3000, finish)

    def finish():
        result = {"frozen": bool(getattr(sys, "frozen", False)), "version": __version__, "errors": errors}
        try:
            result["initial_cards"] = window.db.stats()["全部"]
            result["initial_history"] = len(window.db.history())
            result["initial_sessions"] = len(window.db.sessions())
            window.tabs.setCurrentIndex(0)
            app.processEvents()
            window.grab().save(str(directory / "first_start.png"))
            parsed = parse_file(bundled_wordlist())
            result.update(bundled_cards=len(parsed.cards), parse_errors=parsed.errors,
                          voices=[{"name": v.name, "languages": v.languages} for v in window.speech.voices],
                          selected=window.voice_label.text(), database=str(window.db.path))
            imported = window.db.import_cards(parsed.cards)
            repeated = window.db.import_cards(parsed.cards)
            result.update(imported=imported, repeated=repeated,
                          all_ipa_filled=all(card.ipa for card in window.db.list_cards()))
            page = window.review
            window.tabs.setCurrentIndex(2)
            page.count.setValue(len(parsed.cards))
            page.start(False)
            checks = []
            for back in (False, True):
                for i, status in enumerate(("已掌握", "有一点印象", "完全记不得")):
                    if back:
                        page.flip()
                    card_id, position = page.session.current.id, page.session.index
                    page.grade_buttons[i].click()
                    app.processEvents()
                    checks.append(page.session.index == position + 1 and window.db.get(card_id).status == status)
            result["grade_button_checks"] = checks
            for _ in checks:
                page.undo()
            page.session.end()
            window.grab().save(str(directory / "self_check.png"))
            result["success"] = (result["initial_cards"] == 0 and result["initial_history"] == 0
                                 and result["initial_sessions"] == 0 and len(parsed.cards) == 8 and not parsed.errors and not errors
                                 and result["all_ipa_filled"] and repeated["新增"] == 0 and all(checks))
        except Exception as exc:
            result.update(success=False, error=repr(exc))
        (directory / "self_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.exit(0 if result["success"] else 1)

    QTimer.singleShot(2000, playback)
