"""Synthetic test vocabulary; independent of any user's wordbook."""
from wordbook.importer.txt import export_text
from wordbook.models.card import Card

CARD_COUNT = 160


def sample_cards():
    return [
        Card(
            word=f"test word {i:03d}", meaning=f"测试释义 {i}",
            ipa="" if i % 2 == 0 else "/test/",
            example_en=f"This is test sentence {i}.", example_zh=f"这是测试例句 {i}。",
            source="剑21T1" if i % 2 == 0 else "测试来源",
            priority="A" if i % 2 == 0 else "B",
            tags="阅读,测试重点" if i % 2 == 0 else "听力,测试标签",
            note=f"自动生成的测试数据 {i}",
        )
        for i in range(CARD_COUNT)
    ]


def sample_text():
    return export_text(sample_cards())
