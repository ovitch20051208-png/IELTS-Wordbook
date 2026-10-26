import os
import sys
from pathlib import Path


def data_directory() -> Path:
    # The override is only for isolated tests / portable development runs.
    override = os.environ.get("IELTS_WORDBOOK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "IELTSWordbook"


def bundled_wordlist() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "IELTS_Wordbook_Import_Template.txt"
