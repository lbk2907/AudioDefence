"""PORT ADDITION (Android build): updating is not part of the phone's app - it is updated by installing a
newer one.  On the phone this module is `platform.updater` (see platform/__init__.py).

This keeps the names ui/updates.py imports; nothing here reaches the network.
"""
from __future__ import annotations


class UpdateError(Exception):
    pass


def can_update():
    return False, 'Updating is not available in the Android app. Install a newer one instead.'


def clean_up_staging() -> None:
    pass


def pending_update():
    return None, None, None


def check():
    return None


def build_plan(*a, **k):
    return None


def download(*a, **k):
    return None


def apply(*a, **k):
    return None


def size_text(n) -> str:
    return '%d bytes' % n


def missing_files() -> list:
    return []


def current_release():
    return None


def restore(*a, **k):
    raise UpdateError('Updating is not available in the Android app.')
