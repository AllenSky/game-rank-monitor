"""macOS launchd scheduling for the daily and weekly Slack digests.

launchd is used rather than cron because it catches up on missed runs after the
Mac has been asleep, which matters for a once-a-day job on a laptop.
"""
import os
import plistlib
import subprocess
import sys

from .config import ROOT, load

LABEL_DAILY = "com.topgames.daily"
LABEL_WEEKLY = "com.topgames.weekly"
AGENTS = os.path.expanduser("~/Library/LaunchAgents")
WEEKDAYS = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
            "thursday": 4, "friday": 5, "saturday": 6}


def _plist_path(label):
    return os.path.join(AGENTS, f"{label}.plist")


def _parse_time(value, fallback=(9, 0)):
    try:
        hh, mm = value.split(":")
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        return fallback


def _build(label, period, cal):
    logs = os.path.join(ROOT, "data")
    os.makedirs(logs, exist_ok=True)
    return {
        "Label": label,
        "ProgramArguments": [sys.executable, "-m", "topgames", "run", period],
        "WorkingDirectory": ROOT,
        "EnvironmentVariables": {"PYTHONPATH": ROOT},
        "StartCalendarInterval": cal,
        "StandardOutPath": os.path.join(logs, f"{period}.log"),
        "StandardErrorPath": os.path.join(logs, f"{period}.error.log"),
        "RunAtLoad": False,
    }


def _load_job(path, label):
    subprocess.run(["launchctl", "unload", path],
                   capture_output=True, check=False)
    res = subprocess.run(["launchctl", "load", path], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  warning: launchctl load failed for {label}: "
              f"{res.stderr.strip() or res.stdout.strip()}")
        return False
    return True


def install_launchd(cfg=None):
    cfg = cfg or load()
    os.makedirs(AGENTS, exist_ok=True)
    installed = []

    daily = cfg["slack"]["daily"]
    if daily.get("enabled", True):
        hh, mm = _parse_time(daily.get("time", "09:00"))
        path = _plist_path(LABEL_DAILY)
        with open(path, "wb") as fh:
            plistlib.dump(_build(LABEL_DAILY, "daily", {"Hour": hh, "Minute": mm}), fh)
        if _load_job(path, LABEL_DAILY):
            installed.append(f"daily at {hh:02d}:{mm:02d}")

    weekly = cfg["slack"]["weekly"]
    if weekly.get("enabled", True):
        hh, mm = _parse_time(weekly.get("time", "09:00"))
        wd = WEEKDAYS.get(str(weekly.get("day", "monday")).lower(), 1)
        path = _plist_path(LABEL_WEEKLY)
        with open(path, "wb") as fh:
            plistlib.dump(_build(LABEL_WEEKLY, "weekly",
                                 {"Hour": hh, "Minute": mm, "Weekday": wd}), fh)
        if _load_job(path, LABEL_WEEKLY):
            installed.append(f"weekly on {weekly.get('day','monday')} "
                             f"at {hh:02d}:{mm:02d}")

    if not installed:
        print("Nothing installed -- both digests are disabled in config.json.")
        return 1
    print("Scheduled:")
    for line in installed:
        print(f"  - {line}")
    print(f"\nLogs: {os.path.join(ROOT,'data')}/daily.log, weekly.log")
    print("Re-run this after changing digest times in config.json.")
    return 0


def uninstall_launchd():
    removed = []
    for label in (LABEL_DAILY, LABEL_WEEKLY):
        path = _plist_path(label)
        if os.path.exists(path):
            subprocess.run(["launchctl", "unload", path],
                           capture_output=True, check=False)
            os.remove(path)
            removed.append(label)
    print("Removed: " + (", ".join(removed) if removed else "nothing was installed"))
    return 0


def schedule_status():
    res = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    found = [ln for ln in res.stdout.splitlines() if "com.topgames" in ln]
    for label in (LABEL_DAILY, LABEL_WEEKLY):
        path = _plist_path(label)
        state = "loaded" if any(label in ln for ln in found) else "not loaded"
        exists = "plist present" if os.path.exists(path) else "no plist"
        print(f"{label}: {exists}, {state}")
    return 0
