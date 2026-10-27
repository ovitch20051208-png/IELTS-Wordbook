from pathlib import Path
from wordbook.models.card import Card, ParseResult, TEXT_FIELDS, split_tags, normalize_source, is_phrase, pos_for_word


def parse_text(text: str) -> ParseResult:
    result = ParseResult()
    fields: dict[str, str] | None = None
    problems: list[str] = []
    start = 0
    version = 1

    def finish():
        if fields is None:
            return
        result.total += 1
        required = ("word", "meaning", "ipa", "source") if version >= 2 else ("word", "meaning")
        if version >= 3 and fields.get("word") and not is_phrase(fields["word"]):
            required += ("pos",)
        missing = [n for n in required if not fields.get(n, "").strip()]
        if missing:
            problems.append("缺少必填字段 " + ", ".join(missing))
        if version >= 2 and fields.get("ipa"):
            import re
            if not re.fullmatch(r"/[^/]+/(?:\s*[;；]\s*/[^/]+/)*", fields["ipa"]):
                problems.append("ipa 须使用 /英式音标/；多个读音用中文分号分隔")
        try:
            if "pos" in fields:
                fields["pos"] = pos_for_word(fields.get("word", ""), fields["pos"])
        except ValueError as exc:
            problems.append(str(exc))
        if problems:
            result.errors.append(f"第 {result.total} 张卡（第 {start} 行）：" + "；".join(problems))
        else:
            card = Card(**fields)
            card.tags = ",".join(split_tags(card.tags))
            card.source = normalize_source(card.source)
            result.cards.append(card)

    for number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if line.startswith("# IELTS-VOCAB/"):
            if fields is not None:
                problems.append(f"第 {number} 行：格式版本声明只能放在第一张卡之前")
            elif line in ("# IELTS-VOCAB/1", "# IELTS-VOCAB/2", "# IELTS-VOCAB/3"):
                version = int(line[-1])
            else:
                result.errors.append(f"第 {number} 行：不支持的导入版本 {line}")
            continue
        if not line or line.startswith("#"):
            continue
        if line == "=== CARD ===":
            finish()
            fields, problems, start = {}, [], number
            continue
        if fields is None:
            result.errors.append(f"第 {number} 行：内容不在 === CARD === 卡片内。")
            continue
        if ":" not in line:
            problems.append(f"第 {number} 行缺少英文冒号")
            continue
        name, value = line.split(":", 1)
        name = name.strip()
        if name not in TEXT_FIELDS:
            problems.append(f"第 {number} 行未知字段 {name!r}")
        elif name in fields:
            problems.append(f"第 {number} 行字段 {name} 重复")
        else:
            fields[name] = value.strip()
    finish()
    if not result.total and not result.errors:
        result.errors.append("没有发现词卡，请使用 IELTS-VOCAB/1 格式及 === CARD === 边界。")
    return result


def parse_file(path: str | Path) -> ParseResult:
    try:
        return parse_text(Path(path).read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError("TXT 编码不是 UTF-8，请在记事本中另存为 UTF-8 后重新导入。") from exc


def export_text(cards: list[Card]) -> str:
    version = 2 if all(c.ipa.strip() and c.source.strip() for c in cards) else 1
    if version == 2 and all(is_phrase(c.word) or c.pos.strip() for c in cards):
        version = 3
    lines = [f"# IELTS-VOCAB/{version}", "# UTF-8；学习状态与历史请使用完整 SQLite 备份。", ""]
    for card in cards:
        card.validate()
        lines.append("=== CARD ===")
        lines.extend(f"{name}: {getattr(card, name)}" for name in TEXT_FIELDS)
        lines.append("")
    return "\n".join(lines)
