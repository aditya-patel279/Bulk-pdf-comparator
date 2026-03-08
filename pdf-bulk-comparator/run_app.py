"""
run_app.py
Launcher entry-point for the PyInstaller-packaged Bulk PDF Comparator.

Starts the Streamlit server via its internal bootstrap API (no subprocess
needed — the bundled Python environment is used directly), then opens
the browser once the server is ready.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser


def resource_path(relative_path: str) -> str:
    """Return absolute path — works in source tree and when frozen by PyInstaller."""
    try:
        base: str = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def _write_streamlit_config() -> None:
    """
    Write .streamlit/config.toml next to the exe (or script).
    Streamlit reads this file before anything else, so it is the most
    reliable way to disable development mode in a frozen build.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    config_dir = os.path.join(base_dir, ".streamlit")
    os.makedirs(config_dir, exist_ok=True)

    config_path = os.path.join(config_dir, "config.toml")
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(
            "[global]\n"
            "developmentMode = false\n"
            "\n"
            "[server]\n"
            "headless = true\n"
            "port = 8501\n"
            "enableXsrfProtection = false\n"
            "enableCORS = false\n"
            "\n"
            "[browser]\n"
            "gatherUsageStats = false\n"
        )

    # Also set CWD to the exe directory so Streamlit discovers the config file
    os.chdir(base_dir)


def _open_browser_after_delay() -> None:
    time.sleep(8)
    print("  Opening browser at http://localhost:8501")
    webbrowser.open("http://localhost:8501")
    print()
    print("  Browser opened. Close this window to stop the server.")
    print("=" * 48)


def main() -> None:
    print("=" * 48)
    print("  Bulk PDF Comparator")
    print("=" * 48)
    print("  Writing config …")
    _write_streamlit_config()

    print("  Starting server …")
    print("  Browser will open automatically in ~8 seconds …")
    print()

    browser_thread = threading.Thread(target=_open_browser_after_delay, daemon=True)
    browser_thread.start()

    from streamlit.web import bootstrap  # noqa: PLC0415

    bootstrap.run(
        resource_path("streamlit_app.py"),
        False,
        [],
        {},
    )


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
