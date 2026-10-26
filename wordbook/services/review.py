from wordbook.models.card import GRADES


class ReviewSession:
    def __init__(self, db, cards, mode="指定数量测试"):
        if not cards or len({c.id for c in cards}) != len(cards):
            raise ValueError("测试必须包含至少一张词卡，且同一轮不能有重复词卡。")
        self.db, self.cards = db, cards
        self.id = db.start_session(mode, len(cards))
        self.index = 0
        self.revealed = False
        self.paused = False
        self.ended = False
        self.answers = []  # (index, grade, history id)
        self.skips = set()

    @property
    def current(self):
        return self.cards[self.index] if self.index < len(self.cards) and not self.ended else None

    def reveal(self):
        if self.current and not self.paused:
            self.revealed = not self.revealed

    def grade(self, status):
        if not self.current or self.paused or status not in GRADES:
            raise ValueError("当前不能判定，请继续测试并选择有效的掌握度。")
        history_id = self.db.record(self.current.id, status, self.id)
        self.answers.append((self.index, status, history_id))
        self._advance()

    def skip(self):
        if self.current and not self.paused:
            self.skips.add(self.index)
            self._advance()

    def _advance(self):
        self.index += 1
        self.revealed = False
        if self.index == len(self.cards):
            self.db.session_state(self.id, "completed")

    def undo(self):
        if not self.answers or self.ended or self.paused:
            raise ValueError("本轮没有可以撤销的判定。")
        index, _, history_id = self.answers[-1]
        self.db.undo(history_id, self.id)
        self.answers.pop()
        self.index = index
        self.skips = {i for i in self.skips if i < index}
        self.revealed = True
        self.db.session_state(self.id, "active")

    def toggle_pause(self):
        if self.current:
            self.paused = not self.paused
            self.db.session_state(self.id, "paused" if self.paused else "active")

    def end(self):
        self.db.session_state(self.id, "completed" if self.index == len(self.cards) else "ended")
        self.ended = True

    def summary(self):
        return {**{s: sum(grade == s for _, grade, _ in self.answers) for s in GRADES},
                "跳过": len(self.skips), "未作答": len(self.cards) - len(self.answers) - len(self.skips)}
