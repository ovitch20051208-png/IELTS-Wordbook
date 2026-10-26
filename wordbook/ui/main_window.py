from pathlib import Path
import os
import uuid

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLineEdit, QComboBox, QMessageBox, QFileDialog, QDialog, QProgressDialog,
    QFormLayout, QSpinBox, QGroupBox, QSplitter)

from wordbook import __version__
from wordbook.paths import bundled_wordlist
from wordbook.models.card import STATUSES
from wordbook.importer.txt import parse_file, export_text
from wordbook.services.tts import VOICE_HELP
from wordbook.ui.common import label, button, TableModel, table, Job, local_time
from wordbook.ui.dialogs import CardDialog, ImportPreview
from wordbook.ui.review_page import ReviewPage

STYLE = """
QMainWindow, QDialog { background:#f5f7f9; }
QWidget { font-family:'Segoe UI','Microsoft YaHei UI','Microsoft YaHei'; font-size:14px; color:#243642; }
QTabWidget::pane { border:1px solid #dce3e8; background:white; border-radius:8px; }
QTabBar::tab { padding:12px 24px; background:#edf1f4; margin-right:3px; }
QTabBar::tab:selected { background:white; color:#126e67; font-weight:600; }
QPushButton { padding:9px 16px; border:1px solid #d4dfe4; border-radius:6px; background:white; }
QPushButton:hover { background:#edf5f4; border-color:#74a8a1; }
QPushButton:disabled { color:#9aa9b1; background:#eff2f4; border-color:#e0e5e9; }
QPushButton[kind='primary'] { color:white; background:#176f68; border-color:#176f68; }
QPushButton[kind='primary']:hover { background:#11564f; }
QPushButton[kind='good'] { background:#e5f4ed; color:#16684f; }
QPushButton[kind='medium'] { background:#fff5db; color:#936309; }
QPushButton[kind='bad'] { background:#fcecec; color:#ad3d3d; }
QPushButton[kind='stat'] { text-align:left; padding:20px; font-size:19px; background:#f8fbfa; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { padding:7px; border:1px solid #d4dfe4; border-radius:5px; background:white; selection-background-color:#b0d9d1; }
QTableView { border:1px solid #e0e7ec; background:white; alternate-background-color:#f8fafb; selection-background-color:#d7eee9; selection-color:#203d39; gridline-color:#eef2f4; }
QHeaderView::section { background:#eef3f5; border:0; padding:9px; text-align:left; font-weight:600; }
QFrame#flashcard { border:1px solid #d9e5e4; border-radius:10px; background:white; }
QProgressBar { border:0; background:#e6eeed; border-radius:4px; height:8px; max-height:8px; }
QProgressBar::chunk { background:#29877d; border-radius:4px; }
QGroupBox { border:1px solid #dce3e8; border-radius:6px; margin-top:18px; padding-top:15px; }
QGroupBox::title { subcontrol-origin:margin; padding:0 8px; }
QScrollArea { border:0; }
"""


class MainWindow(QMainWindow):
    def __init__(self, db, speech):
        super().__init__()
        self.db, self.speech = db, speech
        self.jobs = set()
        self._refreshing = False
        self.setWindowTitle(f"IELTS Wordbook v{__version__} · 本地雅思词库")
        self.resize(1220, 860)
        self.setMinimumSize(960, 700)
        self.setStyleSheet(STYLE)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(14)
        layout.addWidget(label("IELTS Wordbook", "font-size:28px;font-weight:700;color:#176f68"))
        layout.addWidget(label("离线学习 · 英式英语 · 每一次进步都保存在本机", "color:#64748b"))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(body)
        self.build_home()
        self.build_library()
        self.review = ReviewPage(self)
        self.tabs.addTab(self.review, "测试 / 复习")
        self.build_history()
        self.build_settings()
        self.tabs.currentChanged.connect(lambda _: self.speech.stop())
        self.statusBar().showMessage("准备就绪 · 数据自动保存")
        self.speech.error.connect(self.speech_error)
        self.speech.message.connect(lambda message: self.statusBar().showMessage(message, 5000))
        self.speech.voices_changed.connect(self.update_voices)
        self.refresh()
        QTimer.singleShot(0, lambda: self.update_voices(self.speech.voices))

    def build_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(label("今天，从一张卡片开始", "font-size:24px;font-weight:600"))
        grid = QGridLayout()
        self.stat_buttons = {}
        for index, state in enumerate(("全部",) + STATUSES):
            control = button(state, lambda checked=False, s=state: self.open_category(s), "stat")
            control.setMinimumHeight(108)
            grid.addWidget(control, index // 3, index % 3)
            self.stat_buttons[state] = control
        layout.addLayout(grid)
        self.last_test = label()
        layout.addWidget(self.last_test)
        row = QHBoxLayout()
        row.addWidget(button("开始测试 / 全库随机", lambda: self.tabs.setCurrentIndex(2), "primary"))
        self.initial_button = button("导入示例词卡", lambda: self.import_path(bundled_wordlist()), "primary")
        row.addWidget(self.initial_button)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(label("掌握度随最近一次判定更新。正面也可直接自评，点击“查看答案”可阅读释义。\n首次启动词库为空，可新增词卡或导入自己的 TXT；示例词卡需手动确认导入。"))
        layout.addStretch()
        self.tabs.addTab(page, "首页 / 概览")

    def build_library(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索英文单词 / 短语或中文释义…")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(button("新增词卡", lambda: self.edit_card(new=True), "primary"))
        search_row.addWidget(button("编辑 / 详情", self.edit_card))
        search_row.addWidget(button("删除", self.delete_card))
        layout.addLayout(search_row)
        filters = QHBoxLayout()
        self.library_status = QComboBox()
        self.library_status.addItem("全部状态", "")
        for status in STATUSES:
            self.library_status.addItem(status, status)
        self.library_source, self.library_priority, self.library_tag = QComboBox(), QComboBox(), QComboBox()
        for combo in (self.library_status, self.library_source, self.library_priority, self.library_tag):
            combo.setMinimumWidth(125)
            combo.currentIndexChanged.connect(self.refresh_library)
            filters.addWidget(combo, 1)
        filters.addWidget(button("清空筛选", self.clear_filters))
        layout.addLayout(filters)
        self.library_count = label()
        layout.addWidget(self.library_count)
        self.library_model = TableModel([("英文单词 / 短语", "word"), ("英式音标", "ipa"), ("中文释义", "meaning"), ("掌握度", "status"), ("重点", "priority"), ("来源", "source"), ("标签", "tags")])
        self.library_view = table(self.library_model)
        self.library_view.setColumnWidth(0, 225)
        self.library_view.setColumnWidth(1, 210)
        self.library_view.setColumnWidth(2, 220)
        self.library_view.setColumnWidth(3, 110)
        self.library_view.setColumnWidth(4, 65)
        self.library_view.setColumnWidth(5, 140)
        self.library_view.doubleClicked.connect(lambda _: self.edit_card())
        layout.addWidget(self.library_view, 1)
        layout.addWidget(label("双击查看 / 编辑，详情中可试听单词和英文例句。A、五星阅读词及阅读高频1300可用上方筛选专门复习。", "color:#64748b"))
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.refresh_library)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        self.tabs.addTab(page, "单词库")

    def build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(label("复习历史", "font-size:22px;font-weight:600"))
        row = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索历史中的英文单词 / 短语…")
        self.history_session = QComboBox()
        self.history_session.setMinimumWidth(320)
        self.history_status = QComboBox()
        self.history_status.addItems(["全部结果", *STATUSES])
        row.addWidget(self.history_search, 1)
        row.addWidget(self.history_session)
        row.addWidget(self.history_status)
        layout.addLayout(row)
        self.history_model = TableModel([("判定时间", "reviewed_at"), ("英文词卡", "word_snapshot"), ("本次结果", "status"), ("原状态", "previous_status"), ("方式", "origin_label"), ("记录状态", "record_state"), ("会话", "session_id")])
        self.history_view = table(self.history_model)
        self.history_view.setColumnWidth(0, 170)
        self.history_view.setColumnWidth(1, 200)
        self.history_view.setColumnWidth(2, 110)
        self.session_model = TableModel([("开始时间", "started_at"), ("模式", "mode"), ("计划张数", "total"), ("会话状态", "state_label"), ("结束时间", "ended_at")])
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.history_view)
        splitter.addWidget(table(self.session_model))
        splitter.setSizes([440, 160])
        layout.addWidget(splitter, 1)
        layout.addWidget(label("手动调整与已撤销判定同样保留；删除词卡后仍保存原英文及历史。时间按本机时区显示。", "color:#64748b"))
        self.history_search.textChanged.connect(self.filter_history)
        self.history_status.currentIndexChanged.connect(self.filter_history)
        self.history_session.currentIndexChanged.connect(self.filter_history)
        self.tabs.addTab(page, "复习历史")

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(16)
        group = QGroupBox("导入 / 导出与完整备份")
        actions = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(button("导入单词 TXT", self.choose_import, "primary"))
        row.addWidget(button("导出全部词卡 TXT", self.export_txt))
        actions.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(button("完整备份 SQLite", self.backup))
        row2.addWidget(button("恢复完整备份…", self.restore))
        actions.addLayout(row2)
        actions.addWidget(label("TXT 用于交换学习内容，不包含状态或历史。完整备份包含词卡、掌握度、复习记录和设置。恢复会替换现有数据，并自动保留恢复前备份。"))
        layout.addWidget(group)
        speech_group = QGroupBox("离线英语朗读 · Windows SAPI5")
        speech_form = QFormLayout(speech_group)
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumContentsLength(35)
        self.voice_combo.currentIndexChanged.connect(self.voice_changed)
        speech_form.addRow("本机发音人 / 语言", self.voice_combo)
        self.voice_label = label("检测中…")
        speech_form.addRow("当前选择", self.voice_label)
        self.speed_combo = QComboBox()
        self.speed_combo.addItem("1.0× 标准", 1.0)
        self.speed_combo.addItem("0.8× 慢速（约）", 0.8)
        self.speed_combo.setCurrentIndex(1 if self.db.setting("tts_speed", 1.0) < 0.95 else 0)
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 5)
        self.repeat_spin.setSuffix(" 次")
        self.repeat_spin.setValue(self.db.setting("tts_repeat", 1))
        self.speech.speed = self.speed_combo.currentData()
        self.speech.repeat = self.repeat_spin.value()
        self.speed_combo.currentIndexChanged.connect(self.speech_settings_changed)
        self.repeat_spin.valueChanged.connect(self.speech_settings_changed)
        speech_form.addRow("语速", self.speed_combo)
        speech_form.addRow("重复播放", self.repeat_spin)
        tts_actions = QHBoxLayout()
        tts_actions.addWidget(button("🔊 测试当前语音", lambda: self.speech.speak("The British English wordbook is ready. Beyond one's means. One-sided.")))
        tts_actions.addWidget(button("停止朗读", self.speech.stop))
        speech_form.addRow(tts_actions)
        speech_form.addRow(label(VOICE_HELP, "color:#64748b;font-size:12px"))
        self.tts_error = label("", "color:#a56509")
        speech_form.addRow(self.tts_error)
        layout.addWidget(speech_group)
        layout.addWidget(label("数据文件：" + str(self.db.path), "color:#64748b"))
        layout.addWidget(button("打开数据目录", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.db.path.parent)))))
        layout.addWidget(label(f"版本 {__version__} · 无账号、无付费 API · 仅首次安装依赖与可选语音包需要联网", "color:#64748b;font-size:12px"))
        layout.addStretch()
        self.tabs.addTab(page, "导入 / 导出与设置")

    def refresh(self):
        self._refreshing = True
        try:
            stats = self.db.stats()
            for state, control in self.stat_buttons.items():
                control.setText(f"{state}\n{stats[state]} 张")
            self.initial_button.setVisible(stats["全部"] == 0 and bundled_wordlist().exists())
            self.last_test.setText("最近测试：" + local_time(stats["最近测试"]))
            facets = self.db.facets()
            for combo, items, title in ((self.library_source, facets["source"], "全部来源"), (self.library_priority, facets["priority"], "全部优先级"), (self.library_tag, facets["tag"], "全部标签")):
                current = combo.currentData()
                combo.blockSignals(True)
                combo.clear()
                combo.addItem(title, "")
                for item in items:
                    combo.addItem(item, item)
                combo.setCurrentIndex(max(0, combo.findData(current)))
                combo.blockSignals(False)
            self.review.refresh_filters()
            self._history_rows = self.db.history()
            sessions = self.db.sessions()
            selected = self.history_session.currentData()
            self.history_session.blockSignals(True)
            self.history_session.clear()
            self.history_session.addItem("全部测试会话 / 手动调整", "")
            for session in sessions:
                self.history_session.addItem(local_time(session["started_at"]) + " · " + session["mode"], session["id"])
                session["state_label"] = {"active": "进行中", "paused": "已暂停", "completed": "已完成", "ended": "提前结束", "interrupted": "上次退出中断"}.get(session["state"], session["state"])
            self.history_session.setCurrentIndex(max(0, self.history_session.findData(selected)))
            self.history_session.blockSignals(False)
            self.session_model.replace(sessions)
        finally:
            self._refreshing = False
        self.refresh_library()
        self.filter_history()

    def refresh_library(self):
        if self._refreshing:
            return
        cards = self.db.list_cards(self.search.text(), self.library_status.currentData() or "", self.library_source.currentData() or "", self.library_priority.currentData() or "", self.library_tag.currentData() or "")
        self.library_model.replace(cards)
        self.library_count.setText(f"当前显示 {len(cards)} 张 / 全库 {self.db.stats()['全部']} 张")

    def filter_history(self):
        if self._refreshing or not hasattr(self, "_history_rows"):
            return
        query, session, status = self.history_search.text().strip().casefold(), self.history_session.currentData(), self.history_status.currentText()
        rows = []
        for source in self._history_rows:
            if query and query not in source["word_snapshot"].casefold():
                continue
            if session and source["session_id"] != session:
                continue
            if status != "全部结果" and status != source["status"]:
                continue
            row = dict(source)
            row["origin_label"] = "手动调整" if row["origin"] == "manual" else "测试"
            row["record_state"] = "已撤销" if row["undone_at"] else "有效" + (" · 词卡已删除" if row["word_id"] is None else "")
            rows.append(row)
        self.history_model.replace(rows)

    def clear_filters(self):
        self.search.clear()
        for combo in (self.library_status, self.library_source, self.library_priority, self.library_tag):
            combo.setCurrentIndex(0)

    def open_category(self, status):
        self.clear_filters()
        self.library_status.setCurrentIndex(max(0, self.library_status.findData("" if status == "全部" else status)))
        self.tabs.setCurrentIndex(1)

    def selected_card(self):
        index = self.library_view.currentIndex()
        if not index.isValid():
            QMessageBox.information(self, "请选择词卡", "请先在列表中选择一张词卡。")
            return None
        return self.library_model.rows[index.row()]

    def allow_change(self):
        if self.review.active:
            QMessageBox.information(self, "测试进行中", "请先在测试页结束本轮，再修改、导入或恢复词库。已判定的学习记录会保留。")
            return False
        return True

    def edit_card(self, checked=False, new=False):
        if not self.allow_change():
            return
        card = None if new else self.selected_card()
        if not new and card is None:
            return
        dialog = CardDialog(self.db, self.speech, card, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def delete_card(self):
        if not self.allow_change():
            return
        card = self.selected_card()
        if card and QMessageBox.question(self, "删除词卡", f"确定删除“{card.word}”？\n词卡会从词库移除，既有复习历史仍保留原英文。") == QMessageBox.StandardButton.Yes:
            self.db.delete(card.id)
            self.refresh()

    def run_job(self, title, function, callback):
        progress = QProgressDialog(title, "", 0, 0, self)
        progress.setWindowTitle("请稍候")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.show()
        job = Job(function, self)
        self.jobs.add(job)

        def success(result):
            progress.close()
            progress.deleteLater()
            callback(result)

        def failure(message):
            progress.close()
            progress.deleteLater()
            QMessageBox.warning(self, "操作未完成", message)

        job.succeeded.connect(success, Qt.ConnectionType.QueuedConnection)
        job.failed.connect(failure, Qt.ConnectionType.QueuedConnection)
        job.finished.connect(lambda: self.jobs.discard(job))
        job.finished.connect(job.deleteLater)
        job.start()

    def choose_import(self):
        if not self.allow_change():
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择单词 TXT（推荐 IELTS-VOCAB/2，含英式音标）", "", "单词 TXT (*.txt);;所有文件 (*)")
        if path:
            self.import_path(path)

    def import_path(self, path):
        if not self.allow_change():
            return

        def parse_preview():
            result = parse_file(path)
            return result, self.db.preview_import(result.cards)

        def preview_ready(data):
            result, counts = data
            dialog = ImportPreview(self, result, counts)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                policy = dialog.policy.currentData()

                def imported(actual):
                    self.refresh()
                    QMessageBox.information(self, "导入完成", f"新增 {actual['新增']} 张，更新 {actual['更新']} 张，重复/跳过 {actual['重复']} 张。\n格式错误 {len(result.errors)} 项未导入（详见预览）。\n既有学习状态与历史已保留。")

                self.run_job("事务导入词卡，正在保存…", lambda: self.db.import_cards(result.cards, policy), imported)

        self.run_job("读取 TXT 并计算导入预览…", parse_preview, preview_ready)

    def export_txt(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出全部词卡（不含学习记录）", "IELTS_Wordbook_Export.txt", "TXT (*.txt)")
        if not path:
            return

        def write():
            target = Path(path)
            staging = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                staging.write_text(export_text(self.db.list_cards()), encoding="utf-8")
                os.replace(staging, target)
            finally:
                if staging.exists():
                    staging.unlink()
            return target

        self.run_job("导出全部词卡…", write, lambda target: QMessageBox.information(self, "导出完成", str(target)))

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "完整 SQLite 备份", "IELTS_Wordbook_Backup.db", "SQLite 完整备份 (*.db)")
        if path:
            self.run_job("保存完整备份…", lambda: self.db.backup(path), lambda _: QMessageBox.information(self, "备份完成", "词卡、状态、历史和设置已备份到：\n" + path))

    def restore(self):
        if not self.allow_change():
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择完整 SQLite 备份", "", "SQLite 完整备份 (*.db)")
        if not path:
            return
        if QMessageBox.warning(self, "确认恢复", "恢复会用所选备份替换当前全部词卡、状态、历史和设置。\n软件会先自动保存恢复前的完整备份。\n确定继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        def restored(safety):
            # Do not write an old in-memory session into the restored database.
            self.review.session = None
            self.review.reset()
            self.db.interrupt_sessions()
            self.speed_combo.blockSignals(True)
            self.repeat_spin.blockSignals(True)
            self.speed_combo.setCurrentIndex(1 if self.db.setting("tts_speed", 1.0) < 0.95 else 0)
            self.repeat_spin.setValue(self.db.setting("tts_repeat", 1))
            self.speed_combo.blockSignals(False)
            self.repeat_spin.blockSignals(False)
            self.speech_settings_changed()
            self.update_voices(self.speech.voices)
            self.refresh()
            QMessageBox.information(self, "恢复完成", "已恢复全部数据。恢复前备份保存在：\n" + str(safety))

        self.run_job("校验备份并恢复…", lambda: self.db.restore(path), restored)

    def update_voices(self, voices):
        saved = self.db.setting("tts_voice", "")
        ids = {voice.id for voice in voices}
        from wordbook.services.tts import preferred_voice
        chosen = saved if saved in ids else preferred_voice(voices)
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        self.voice_combo.addItem("请选择发音人" if voices else "无可用 SAPI5 发音人", "")
        for voice in voices:
            self.voice_combo.addItem(voice.label, voice.id)
        self.voice_combo.setCurrentIndex(max(0, self.voice_combo.findData(chosen)))
        self.voice_combo.blockSignals(False)
        # Startup detection can finish after the first UI event. Never erase the
        # user's saved voice while the initial list is still empty/unavailable.
        self.voice_changed(persist=False)
        if self.speech.last_error:
            self.tts_error.setText(self.speech.last_error)

    def voice_changed(self, index=None, *, persist=True):
        self.speech.stop()
        voice_id = self.voice_combo.currentData() or ""
        self.speech.voice_id = voice_id
        if persist:
            self.db.set_setting("tts_voice", voice_id)
        voice = next((v for v in self.speech.voices if v.id == voice_id), None)
        if not voice:
            self.voice_label.setText("未选择可用的发音人，朗读暂不可用；学习功能可正常使用。")
        else:
            kind = "英式英语" if "en-GB" in voice.languages else "当前为其他语言/口音（不是英式英语）"
            self.voice_label.setText(voice.label + " · " + kind)
            self.tts_error.setText("")

    def speech_settings_changed(self):
        self.speech.speed = self.speed_combo.currentData()
        self.speech.repeat = self.repeat_spin.value()
        self.db.set_setting("tts_speed", self.speech.speed)
        self.db.set_setting("tts_repeat", self.speech.repeat)

    def speech_error(self, message):
        self.tts_error.setText(message)
        self.statusBar().showMessage(message, 12000)

    def closeEvent(self, event):
        if self.jobs:
            QMessageBox.information(self, "操作进行中", "正在处理文件或保存数据，请等待当前操作完成后再退出。")
            event.ignore()
            return
        if self.review.active:
            if QMessageBox.question(self, "退出软件", "本轮尚未完成，已判定的结果均已保存。确定结束本轮并退出？") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.review.session.end()
        self.speech.close()
        event.accept()
