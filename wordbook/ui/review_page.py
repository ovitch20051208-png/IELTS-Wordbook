from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox,
    QSpinBox, QStackedWidget, QScrollArea, QProgressBar, QMessageBox, QFrame)

from wordbook.models.card import STATUSES, GRADES, is_phrase
from wordbook.services.review import ReviewSession
from wordbook.services.catalog import ipa_reference
from wordbook.ui.common import label, button


class ClickFrame(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ReviewPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.db, self.speech = main, main.db, main.speech
        self.session = None
        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.setup = QWidget()
        self.stack.addWidget(self.setup)
        form = QVBoxLayout(self.setup)
        form.setSpacing(18)
        form.addWidget(label("开始一次专注练习", "font-size:24px;font-weight:600"))
        form.addWidget(label("先选择抽题范围和数量。全库随机会跨越所有掌握度，已掌握的词也会出现。"))
        grid = QGridLayout()
        self.status = QComboBox()
        self.status.addItem("全部单词", "")
        for s in STATUSES:
            self.status.addItem(s, s)
        self.source, self.tag = QComboBox(), QComboBox()
        self.presets = QComboBox()
        self.presets.addItems(["5", "10", "20", "30", "50", "100", "自定义"])
        self.presets.setCurrentText("10")
        self.count = QSpinBox()
        self.count.setRange(1, 100000000)
        self.count.setValue(10)
        self.count.setEnabled(False)
        self.presets.currentTextChanged.connect(self.preset_changed)
        for row, (title, widget) in enumerate((("掌握度", self.status), ("来源", self.source), ("标签", self.tag), ("本次数量", self.presets), ("自定义数量", self.count))):
            grid.addWidget(label(title), row, 0)
            grid.addWidget(widget, row, 1)
        form.addLayout(grid)
        self.available = label()
        form.addWidget(self.available)
        actions = QHBoxLayout()
        actions.addWidget(button("开始指定数量测试", lambda: self.start(False), "primary"))
        actions.addWidget(button("全库随机测试", lambda: self.start(True), "primary"))
        form.addLayout(actions)
        form.addWidget(label("全库随机只使用数量设置，忽略上方掌握度、来源及标签，保证真正覆盖全库。\n跳过不记成绩；仅翻面不算测试。每次判定都会立即保存。"))
        form.addStretch()
        for combo in (self.status, self.source, self.tag):
            combo.currentIndexChanged.connect(self.update_available)

        self.study = QWidget()
        self.stack.addWidget(self.study)
        study = QVBoxLayout(self.study)
        self.progress_text = label()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        study.addWidget(self.progress_text)
        study.addWidget(self.progress)
        self.card_frame = ClickFrame()
        self.card_frame.setObjectName("flashcard")
        self.card_frame.clicked.connect(self.flip)
        contents = QVBoxLayout(self.card_frame)
        contents.setContentsMargins(30, 24, 30, 24)
        self.source_label = label("", "color:#64748b;font-size:12px")
        contents.addWidget(self.source_label)
        word_row = QHBoxLayout()
        self.word_label = label("", "font-size:34px;font-weight:600;color:#193b43")
        word_row.addWidget(self.word_label, 1)
        self.word_speaker = button("🔊 单词", self.speak_word)
        self.word_speaker.setToolTip("朗读当前英文单词或短语；不翻面")
        word_row.addWidget(self.word_speaker)
        contents.addLayout(word_row)
        self.ipa = label("", "font-size:17px;color:#64748b")
        self.pos_label = label("", "font-size:16px;color:#176f68;font-weight:600")
        pronunciation_row = QHBoxLayout()
        pronunciation_row.addWidget(self.pos_label)
        pronunciation_row.addWidget(self.ipa, 1)
        contents.addLayout(pronunciation_row)
        self.back = QWidget()
        back_layout = QVBoxLayout(self.back)
        back_layout.setContentsMargins(0, 12, 0, 0)
        self.meaning = label("", "font-size:23px;font-weight:600")
        back_layout.addWidget(self.meaning)
        example_row = QHBoxLayout()
        self.example = label("", "font-size:19px")
        example_row.addWidget(self.example, 1)
        self.example_speaker = button("🔊 例句", self.speak_example)
        self.example_speaker.setToolTip("仅朗读完整英文语境例句")
        example_row.addWidget(self.example_speaker)
        back_layout.addLayout(example_row)
        self.translation, self.notes = label(), label("", "color:#64748b")
        back_layout.addWidget(self.translation)
        back_layout.addWidget(self.notes)
        contents.addWidget(self.back)
        self.flip_hint = label("点击卡面 / Space 查看释义；也可直接按下方掌握度自评并进入下一词", "color:#64748b")
        contents.addWidget(self.flip_hint)
        contents.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.card_frame)
        study.addWidget(scroll, 1)
        self.flip_button = button("查看答案  [Space]", self.flip, "primary")
        study.addWidget(self.flip_button)
        grades = QHBoxLayout()
        self.grade_buttons = []
        for i, (text, grade) in enumerate(zip(("✅ 已掌握  [1]", "🟡 有一点印象  [2]", "❌ 完全记不得  [3]"), GRADES)):
            control = button(text, lambda checked=False, s=grade: self.grade(s), ("good", "medium", "bad")[i])
            control.setMinimumHeight(52)
            self.grade_buttons.append(control)
            grades.addWidget(control)
        study.addLayout(grades)
        row = QHBoxLayout()
        self.skip_button = button("跳过（不改变状态）", self.skip)
        self.undo_button = button("撤销本轮最后一次判定", self.undo)
        self.pause_button = button("暂停", self.pause)
        row.addWidget(self.skip_button)
        row.addWidget(self.undo_button)
        row.addWidget(self.pause_button)
        row.addWidget(button("结束本轮", self.end))
        study.addLayout(row)

        self.results = QWidget()
        self.stack.addWidget(self.results)
        results = QVBoxLayout(self.results)
        results.addWidget(label("本轮测试结果", "font-size:26px;font-weight:600"))
        self.summary_label = label("", "font-size:20px")
        results.addWidget(self.summary_label)
        self.result_undo = button("撤销最后一次判定并返回词卡", self.undo)
        results.addWidget(self.result_undo)
        results.addWidget(button("重新选择测试", self.reset))
        results.addWidget(button("返回首页", lambda: main.tabs.setCurrentIndex(0)))
        results.addStretch()
        self.shortcuts = []
        for key, callback in (("Space", self.flip), ("1", lambda: self.grade(GRADES[0])), ("2", lambda: self.grade(GRADES[1])), ("3", lambda: self.grade(GRADES[2]))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.setEnabled(False)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def preset_changed(self, value):
        self.count.setEnabled(value == "自定义")
        if value.isdigit():
            self.count.setValue(int(value))

    def refresh_filters(self):
        facets = self.db.facets()
        for combo, items, title in ((self.source, facets["source"], "全部来源"), (self.tag, facets["tag"], "全部标签")):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(title, "")
            for item in items:
                combo.addItem(item, item)
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.update_available()

    def update_available(self):
        n = len(self.db.list_cards(status=self.status.currentData() or "", source=self.source.currentData() or "", tag=self.tag.currentData() or ""))
        self.available.setText(f"当前筛选可抽取：{n} 张；全库随机可抽取：{self.db.stats()['全部']} 张。同一轮不重复。")

    @property
    def active(self):
        return bool(self.session and self.session.current and not self.session.ended)

    def start(self, global_random):
        try:
            cards = self.db.sample(self.count.value(), global_random=global_random,
                                   status=self.status.currentData() or "", source="" if global_random else self.source.currentData() or "",
                                   tag="" if global_random else self.tag.currentData() or "")
            self.session = ReviewSession(self.db, cards, "全库随机测试" if global_random else "指定数量测试")
            self.stack.setCurrentWidget(self.study)
            self.render()
        except Exception as exc:
            QMessageBox.information(self, "无法开始测试", str(exc))

    def render(self):
        session = self.session
        if not session:
            return
        for shortcut in self.shortcuts:
            shortcut.setEnabled(session.current is not None)
        self.speech.stop()
        if session.current is None:
            summary = session.summary()
            self.summary_label.setText("\n\n".join(f"{key}：{count}" for key, count in summary.items()) + "\n\n判定已保存，首页和单词库已同步更新。")
            self.result_undo.setEnabled(bool(session.answers) and not session.ended)
            self.stack.setCurrentWidget(self.results)
            return
        self.stack.setCurrentWidget(self.study)
        card = session.current
        self.progress_text.setText(f"第 {session.index + 1} / {len(session.cards)} 张  ·  剩余 {len(session.cards) - session.index} 张  ·  已判定 {len(session.answers)} 张" + ("  ·  已暂停" if session.paused else ""))
        self.progress.setRange(0, len(session.cards))
        self.progress.setValue(session.index)
        # IPA helps pronunciation on either side; meaning and examples stay hidden.
        self.source_label.setText(card.source if not session.paused else "暂停中")
        self.word_label.setText(card.word if not session.paused else "已暂停")
        self.meaning.setText(card.meaning)
        self.ipa.setText(card.ipa_display)
        self.pos_label.setText(card.pos)
        self.pos_label.setVisible(bool(card.pos) and not is_phrase(card.word) and not session.paused)
        self.ipa.setToolTip(ipa_reference(card.word, card.ipa))
        self.ipa.setVisible(not session.paused)
        self.example.setText(card.example_en or "暂无英文例句")
        self.translation.setText(card.example_zh)
        focus = ("★ 重点词 · " if card.focus else "") + f"优先级 {card.priority or '未设置'}  ·  {card.tags}"
        self.notes.setText(focus + ("\n" + card.note if card.note else ""))
        self.back.setVisible(session.revealed and not session.paused)
        self.flip_hint.setVisible(not session.revealed and not session.paused)
        self.flip_button.setEnabled(not session.paused)
        self.flip_button.setText("收起答案  [Space]" if session.revealed else "查看答案  [Space]")
        self.word_speaker.setEnabled(not session.paused)
        self.example_speaker.setEnabled(not session.paused and bool(card.example_en))
        for control in self.grade_buttons:
            control.setEnabled(not session.paused)
        self.skip_button.setEnabled(not session.paused)
        self.undo_button.setEnabled(bool(session.answers) and not session.paused)
        self.pause_button.setText("继续" if session.paused else "暂停")

    def flip(self):
        if self.active and self.stack.currentWidget() == self.study:
            self.session.reveal()
            self.render()

    def grade(self, status):
        if not self.active or self.session.paused or self.stack.currentWidget() != self.study:
            return
        try:
            self.session.grade(status)
            self.main.refresh()
            self.render()
        except Exception as exc:
            QMessageBox.warning(self, "保存判定失败", str(exc))

    def skip(self):
        if self.active:
            self.session.skip()
            self.render()

    def undo(self):
        if self.session:
            try:
                self.session.undo()
                self.main.refresh()
                self.render()
            except Exception as exc:
                QMessageBox.warning(self, "无法撤销", str(exc))

    def pause(self):
        if self.active:
            self.session.toggle_pause()
            self.render()

    def end(self):
        if self.active and QMessageBox.question(self, "结束本轮", "已判定结果已经保存。结束后未作答的词保持原状态，确定结束？") != QMessageBox.StandardButton.Yes:
            return
        if self.session:
            self.session.end()
            self.render()
            self.main.refresh()

    def reset(self):
        self.speech.stop()
        if self.session:
            self.session.end()
        self.session = None
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
        self.stack.setCurrentWidget(self.setup)
        self.refresh_filters()

    def speak_word(self):
        if self.active and not self.session.paused:
            self.speech.speak(self.session.current.word)

    def speak_example(self):
        if self.active and self.session.revealed and not self.session.paused:
            self.speech.speak(self.session.current.example_en)
