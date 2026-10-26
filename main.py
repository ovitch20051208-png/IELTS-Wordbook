"""Windows desktop entry point. Importing it has no side effects."""
import logging
import sys


def main():
    from PySide6.QtCore import QLockFile, QTranslator, QLibraryInfo
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox
    from wordbook.paths import data_directory
    from wordbook.storage.database import Database
    from wordbook.services.tts import SpeechService
    from wordbook.services.catalog import upgrade_catalog
    from wordbook.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("IELTS Wordbook")
    app.setOrganizationName("IELTSWordbook")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    translator = QTranslator(app)
    if translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=directory / "wordbook.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    lock = QLockFile(str(directory / "wordbook.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "IELTS Wordbook", "相同数据目录的程序已经在运行，请切换到现有窗口。")
        return 0
    speech = None
    try:
        db = Database(directory / "wordbook.db")
        content_update = upgrade_catalog(db)
        if content_update["backup"]:
            logging.info("Content upgrade: %s", content_update)
        db.interrupt_sessions()
        speech = SpeechService()
        window = MainWindow(db, speech)

        def exception_handler(kind, value, trace):
            logging.error("Unhandled error", exc_info=(kind, value, trace))
            QMessageBox.warning(window, "操作未完成", f"{value}\n\n已写入错误日志：{directory / 'wordbook.log'}")

        sys.excepthook = exception_handler
        window.show()
        if "--self-check" in sys.argv:
            from wordbook.services.diagnostics import schedule_self_check
            schedule_self_check(app, window, directory)
        return app.exec()
    except Exception as exc:
        logging.exception("Startup failed")
        QMessageBox.critical(None, "启动失败", f"{exc}\n\n数据目录：{directory}\n请查看 wordbook.log。已有数据不会被自动删除。")
        return 1
    finally:
        if speech:
            speech.close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
