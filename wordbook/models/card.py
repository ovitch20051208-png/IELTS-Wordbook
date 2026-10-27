from dataclasses import dataclass, field
from datetime import datetime, timezone
import re

STATUSES = ("未测试", "已掌握", "有一点印象", "完全记不得")
GRADES = STATUSES[1:]
TEXT_FIELDS = ("word", "pos", "meaning", "ipa", "example_en", "example_zh", "source", "priority", "tags", "note")
POS_OPTIONS = ("", "n.", "v.", "adj.", "adv.", "n.; v.", "n.; adj.", "adj.; adv.", "pron.", "prep.", "conj.", "det.", "num.", "interj.", "aux.", "vt.", "vi.")


def is_phrase(word: str) -> bool:
    # Slash-separated single-word forms such as stimulus / stimuli are still words.
    forms = [part.strip() for part in word.strip().split("/")]
    return any(len(part.split()) > 1 for part in forms)


def normalize_pos(value: str) -> str:
    aliases = {"n": "n.", "noun": "n.", "名词": "n.", "v": "v.", "verb": "v.", "动词": "v.",
               "adj": "adj.", "adjective": "adj.", "形容词": "adj.", "adv": "adv.", "adverb": "adv.", "副词": "adv.",
               "pron": "pron.", "pronoun": "pron.", "代词": "pron.", "prep": "prep.", "preposition": "prep.", "介词": "prep.",
               "conj": "conj.", "conjunction": "conj.", "连词": "conj.", "det": "det.", "determiner": "det.", "限定词": "det.",
               "num": "num.", "numeral": "num.", "数词": "num.", "interj": "interj.", "interjection": "interj.", "感叹词": "interj.",
               "aux": "aux.", "auxiliary": "aux.", "助动词": "aux.", "vt": "vt.", "及物动词": "vt.", "vi": "vi.", "不及物动词": "vi."}
    parts = []
    for raw in re.split(r"\s*[;；,，/、]\s*", value.strip()):
        if not raw:
            continue
        key = raw.strip().casefold().rstrip(".")
        if key not in aliases:
            raise ValueError(f"无法识别词性“{raw}”，请使用 n.、v.、adj.、adv. 等；多个词性用分号分隔。")
        pos = aliases[key]
        if pos not in parts:
            parts.append(pos)
    return "; ".join(parts)


def pos_for_word(word: str, pos: str) -> str:
    return "" if is_phrase(word) else normalize_pos(pos)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def normalize_word(word: str) -> str:
    return " ".join(word.strip().casefold().split())


def split_tags(value: str) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in re.split(r"[,，\n]", value) if t.strip()))


def split_sources(value: str) -> list[str]:
    sources = []
    for source in re.split(r"\s*[|｜,，;；]\s*", value):
        source = source.strip()
        match = re.match(r"(?:剑(?:桥(?:雅思)?)?|Cambridge\s*(?:IELTS)?\s*|C)\s*(\d+)\s*(?:Test\s*|T\s*)(\d+)", source, re.I)
        if match:
            source = f"剑{int(match[1])}T{int(match[2])}"
        if source and source not in sources:
            sources.append(source)
    return sources


def normalize_source(value: str) -> str:
    return " | ".join(split_sources(value))


@dataclass
class Card:
    word: str
    meaning: str
    ipa: str = ""
    example_en: str = ""
    example_zh: str = ""
    source: str = ""
    priority: str = ""
    tags: str = ""
    note: str = ""
    id: str = ""
    status: str = "未测试"
    review_count: int = 0
    last_reviewed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    pos: str = ""

    @property
    def pos_display(self) -> str:
        return "" if is_phrase(self.word) else (self.pos or "待补充")

    @property
    def ipa_display(self) -> str:
        return self.ipa or "音标待补充"

    @property
    def focus(self) -> bool:
        return self.priority.upper() == "A" or bool(set(split_tags(self.tags)) & {"五星阅读词", "阅读高频1300"})

    def validate(self) -> None:
        if not self.word.strip() or not self.meaning.strip():
            raise ValueError("英文单词/短语、中文释义不能为空。")
        if self.status not in STATUSES:
            raise ValueError("无效的掌握状态。")
        if not is_phrase(self.word):
            normalize_pos(self.pos)
        for name in TEXT_FIELDS:
            if "\n" in getattr(self, name) or "\r" in getattr(self, name):
                raise ValueError(f"{name} 不可包含换行；请在同一行中输入完整内容（界面会自动换行）。")


@dataclass
class ParseResult:
    cards: list[Card] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total: int = 0
