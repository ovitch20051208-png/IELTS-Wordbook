"""Apply the offline v1.1 content-only upgrade to the existing local wordbook."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wordbook.paths import data_directory
from wordbook.storage.database import Database
from wordbook.services.catalog import upgrade_catalog


def main():
    path = data_directory() / "wordbook.db"
    if not path.exists():
        raise SystemExit("No existing learning database found; no file was created.")
    db = Database(path)
    before = db.list_cards()
    history = db.history()
    result = upgrade_catalog(db)
    after = db.list_cards()

    def protected(cards):
        return {c.id: {k: v for k, v in asdict(c).items() if k not in ("ipa", "source", "updated_at")} for c in cards}

    report = {**result, "database": str(path), "total_before": len(before), "total_after": len(after),
              "empty_ipa_before": sum(not c.ipa for c in before), "empty_ipa_after": sum(not c.ipa for c in after),
              "learning_and_content_preserved": protected(before) == protected(after), "history_preserved": history == db.history(),
              "sources": db.facets()["source"]}
    output = ROOT / ".test-artifacts" / "live_content_upgrade_20261023.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report["empty_ipa_after"] or not report["learning_and_content_preserved"] or not report["history_preserved"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
