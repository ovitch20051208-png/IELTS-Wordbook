from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPlainTextEdit, QComboBox, QDialogButtonBox, QMessageBox, QWidget, QScrollArea)

from wordbook.models.card import Card, STATUSES, TEXT_FIELDS, POS_OPTIONS, is_phrase
from wordbook.ui.common import label, button, local_time, TableModel, table


class CardDialog(QDialog):
    def __init__(self, db, speech, card=None, parent=None):
        super().__init__(parent)
        self.db, self.speech, self.card = db, speech, card
        self.saved_id = None
        self.setWindowTitle("编辑词卡" if card else "新增词卡")
        self.resize(850, 740)
        layout = QVBoxLayout(self)
        layout.addWidget(label("修改后点击保存。音标只填写已经核实的内容，缺失时可以留空。"))
        body = QWidget()
        form = QFormLayout(body)
        form.setSpacing(12)
        self.fields = {}
        names = ("英文单词 / 短语 *", "词性（单词填写，词组留空）", "中文释义 *", "英式音标", "英文语境例句", "例句中文翻译", "来源（如 剑21T1 | 剑20T3）", "优先级", "标签（英文逗号分隔）", "备注")
        for field, title in zip(TEXT_FIELDS, names):
            value = getattr(card, field) if card else ""
            if field == "pos":
                edit = QComboBox()
                edit.setEditable(True)
                edit.addItems(POS_OPTIONS)
                edit.setCurrentText(value)
                edit.lineEdit().setPlaceholderText("n. / v. / adj. / adv.；多个词性用分号分隔")
            else:
                edit = QPlainTextEdit(value) if field in ("meaning", "example_en", "example_zh", "note") else QLineEdit(value)
            if isinstance(edit, QPlainTextEdit):
                edit.setFixedHeight(70)
                edit.setTabChangesFocus(True)
            self.fields[field] = edit
            if field in ("word", "example_en"):
                row = QHBoxLayout()
                row.addWidget(edit, 1)
                speaker = button("🔊 试听", lambda checked=False, f=field: self.speech.speak(self.value(f)))
                speaker.setToolTip("朗读英文单词/短语" if field == "word" else "朗读完整英文例句")
                row.addWidget(speaker)
                if field == "word":
                    self.word_speaker = speaker
                else:
                    self.example_speaker = speaker
                form.addRow(title, row)
            else:
                form.addRow(title, edit)
        self.fields["ipa"].setPlaceholderText("音标待补充（不会自动生成）")
        self.fields["priority"].setPlaceholderText("A / B 或其他自定义等级")
        self.fields["word"].textChanged.connect(self.update_pos_control)
        self.update_pos_control()
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.setCurrentText(card.status if card else "未测试")
        form.addRow("当前掌握度", self.status)
        if card:
            form.addRow("学习记录", label(f"累计判定 {card.review_count} 次  ·  最近 {local_time(card.last_reviewed_at)}"))
            form.addRow("创建时间", label(local_time(card.created_at)))
            form.addRow("历史", button("查看这张词卡的复习历史", self.show_history))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.error_label = label("", "color:#ba3838")
        layout.addWidget(self.error_label)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        controls.accepted.connect(self.save)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.finished.connect(lambda _: self.speech.stop())

    def value(self, field):
        widget = self.fields[field]
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return (widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()).strip()

    def update_pos_control(self):
        phrase = is_phrase(self.value("word"))
        control = self.fields["pos"]
        control.setEnabled(not phrase)
        if phrase:
            control.setCurrentText("")
        control.setToolTip("词组不需要词性，此项保持空白。" if phrase else "按当前释义填写缩写，例如 n.、v.、adj.、adv.。")

    def save(self):
        try:
            data = asdict(self.card) if self.card else {}
            data.update({f: self.value(f) for f in TEXT_FIELDS}, status=self.status.currentText())
            card = Card(**data)
            card.validate()
            if self.card:
                self.db.update(self.card.id, card)
                self.saved_id = self.card.id
            else:
                status = card.status
                card.status = "未测试"
                self.saved_id = self.db.add(card)
                if status != "未测试":
                    self.db.record(self.saved_id, status, origin="manual")
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))

    def show_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.card.word + " · 复习历史")
        dialog.resize(950, 450)
        layout = QVBoxLayout(dialog)
        model = TableModel([("时间", "reviewed_at"), ("结果", "status"), ("方式", "origin"), ("撤销时间", "undone_at"), ("会话", "session_id")])
        rows = self.db.history(self.card.id)
        for row in rows:
            row["origin"] = "手动调整" if row["origin"] == "manual" else "测试"
        model.replace(rows)
        layout.addWidget(table(model))
        layout.addWidget(button("关闭", dialog.accept))
        dialog.exec()


class ImportPreview(QDialog):
    def __init__(self, main, result, counts):
        super().__init__(main)
        self.main, self.result = main, result
        self.setWindowTitle("TXT 导入预览")
        self.resize(1000, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(label("正确词卡会在确认后整批提交。错误词卡不会写入，全部错误原因列在下方。"))
        self.policy = QComboBox()
        self.policy.addItem("合并空白字段、来源和标签；保留已有非空内容、状态和历史（默认）", "merge")
        self.policy.addItem("仅追加来源和标签；不修改其他内容、状态和历史", "sources")
        layout.addWidget(self.policy)
        self.counts = label("", "font-size:16px;font-weight:600")
        layout.addWidget(self.counts)
        model = TableModel([("英文", "word"), ("词性", "pos"), ("中文释义", "meaning"), ("英式音标", "ipa"), ("来源", "source"), ("标签", "tags")])
        model.replace(result.cards)
        layout.addWidget(table(model), 1)
        errors = QPlainTextEdit("\n".join(result.errors) or "没有发现格式错误。")
        errors.setReadOnly(True)
        errors.setMaximumHeight(135)
        layout.addWidget(errors)
        self.controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.controls.button(QDialogButtonBox.StandardButton.Ok).setText("确认导入有效词卡")
        self.controls.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(result.cards))
        self.controls.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.controls.accepted.connect(self.accept)
        self.controls.rejected.connect(self.reject)
        layout.addWidget(self.controls)
        self.set_counts(counts)
        self.policy.currentIndexChanged.connect(self.recalculate)

    def set_counts(self, counts):
        self.counts.setText(f"解析 {self.result.total} 张 · 有效 {len(self.result.cards)} 张 · 预计新增 {counts['新增']} · 更新 {counts['更新']} · 重复/跳过 {counts['重复']} · 错误 {len(self.result.errors)} 项")

    def recalculate(self):
        policy = self.policy.currentData()
        self.main.run_job("重新计算导入预览…", lambda: self.main.db.preview_import(self.result.cards, policy), self.set_counts)
