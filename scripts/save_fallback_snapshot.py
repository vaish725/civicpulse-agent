"""Refresh the local demo fallback snapshot from the live San Jose feed.

Run this a short while before a demo so the cached copy is recent:

    PYTHONPATH=src python3 scripts/save_fallback_snapshot.py

The saved data is real (pulled from the live government feed), just frozen
at the time this was last run, so a live demo never depends on the
government site being reachable at that exact moment.
"""

from civicpulse.config import COUNCIL_BODY_ID
from civicpulse.legistar_client import FALLBACK_SNAPSHOT_PATH, save_fallback_snapshot

if __name__ == "__main__":
    count = save_fallback_snapshot(COUNCIL_BODY_ID)
    print(f"Saved {count} real agenda items to {FALLBACK_SNAPSHOT_PATH}")
