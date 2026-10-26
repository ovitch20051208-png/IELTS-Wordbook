from dataclasses import dataclass, field
from datetime import datetime, timezone
import re

STATUSES = ("未测试", "已掌握", "有一点印象", "完全记不得")
GRADES = STATUSES[1:]
TEXT_FIELDS = ("word", "meaning", "ipa", "example_en", "example_zh", "source", "priority", "tags", "note")


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
        for name in TEXT_FIELDS:
            if "\n" in getattr(self, name) or "\r" in getattr(self, name):
                raise ValueError(f"{name} 不可包含换行；请在同一行中输入完整内容（界面会自动换行）。")


@dataclass
class ParseResult:
    cards: list[Card] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total: int = 0
