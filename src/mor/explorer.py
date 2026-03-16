"""Launcher for the Streamlit ontology explorer."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    try:
        from streamlit.web import cli as stcli
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "Streamlit is not installed. Install the UI extras with: pip install -e '.[ui]'"
        ) from exc

    target = Path(__file__).with_name("explorer_app.py")
    sys.argv = ["streamlit", "run", str(target), *sys.argv[1:]]
    raise SystemExit(stcli.main())
