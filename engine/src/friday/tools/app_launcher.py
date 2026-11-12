# app_launcher.py — Application launcher for Friday (Windows Start Menu / Linux .desktop)
import os
import platform
import re
import shlex
import subprocess
from difflib import get_close_matches
from pathlib import Path

from friday.core.log import log

_IS_WINDOWS = platform.system() == "Windows"

# Linux: freedesktop .desktop files
_APP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local" / "share" / "applications",
]

# Windows: Start Menu shortcut folders (all users + current user)
_WIN_APP_DIRS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]

_app_cache = None


def _parse_desktop_file(path):
    """Extract Name and Exec from a Linux .desktop file."""
    name = None
    exec_cmd = None
    in_entry = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line == "[Desktop Entry]":
                    in_entry = True
                    continue
                if line.startswith("[") and in_entry:
                    break
                if not in_entry:
                    continue
                if line.startswith("Name=") and name is None:
                    name = line[5:]
                elif line.startswith("Exec=") and exec_cmd is None:
                    exec_cmd = line[5:]
                elif line.startswith("NoDisplay=true"):
                    return None, None
    except OSError:
        return None, None
    return name, exec_cmd


def _clean_exec(exec_str):
    """Strip freedesktop field codes (%u, %U, %f, %F, %i, etc.) from Exec."""
    if not exec_str:
        return None
    cleaned = re.sub(r"%[uUfFdDnNickvm]", "", exec_str).strip()
    return cleaned if cleaned else None


def _scan_windows_apps():
    """Scan Start Menu .lnk shortcuts and build a name→shortcut-path map."""
    apps = {}
    skip_words = ("uninstall", "readme", "help", "documentation", "website", "update")
    for app_dir in _WIN_APP_DIRS:
        if not app_dir.is_dir():
            continue
        for lnk in app_dir.rglob("*.lnk"):
            name = lnk.stem
            if any(w in name.lower() for w in skip_words):
                continue
            apps.setdefault(name.lower(), {
                "name": name,
                "exec": str(lnk),   # launched via os.startfile
                "path": str(lnk),
            })
    return apps


def _scan_linux_apps():
    """Scan .desktop files and build a name→exec map."""
    apps = {}
    for app_dir in _APP_DIRS:
        if not app_dir.is_dir():
            continue
        for desktop_file in app_dir.glob("*.desktop"):
            name, exec_cmd = _parse_desktop_file(desktop_file)
            if name and exec_cmd:
                cleaned = _clean_exec(exec_cmd)
                if cleaned:
                    apps[name.lower()] = {
                        "name": name,
                        "exec": cleaned,
                        "path": str(desktop_file),
                    }
    return apps


def scan_apps():
    """Scan installed applications. Caches result."""
    global _app_cache
    if _app_cache is not None:
        return _app_cache

    _app_cache = _scan_windows_apps() if _IS_WINDOWS else _scan_linux_apps()
    log.info(f"Scanned {len(_app_cache)} launchable applications")
    return _app_cache


def find_app(query):
    """Fuzzy-match an app name. Returns (display_name, exec_cmd) or (None, None)."""
    apps = scan_apps()
    query_lower = query.lower().strip()

    # Exact match first
    if query_lower in apps:
        entry = apps[query_lower]
        return entry["name"], entry["exec"]

    # Substring match
    for key, entry in apps.items():
        if query_lower in key or key in query_lower:
            return entry["name"], entry["exec"]

    # Fuzzy match
    matches = get_close_matches(query_lower, apps.keys(), n=1, cutoff=0.5)
    if matches:
        entry = apps[matches[0]]
        return entry["name"], entry["exec"]

    return None, None


def launch(query):
    """Find and launch an app by name. Returns app name or None."""
    name, exec_cmd = find_app(query)
    if not name or not exec_cmd:
        return None
    try:
        if _IS_WINDOWS:
            os.startfile(exec_cmd)  # Opens the .lnk like a double-click
        else:
            args = shlex.split(exec_cmd)
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        log.info(f"Launched '{name}' via: {exec_cmd}")
        return name
    except Exception as e:
        log.error(f"Failed to launch '{name}': {e}")
        return None


def rescan():
    """Force a fresh scan of installed applications."""
    global _app_cache
    _app_cache = None
    return scan_apps()
