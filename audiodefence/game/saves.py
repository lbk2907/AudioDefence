"""PORT ADDITION (user request, 2026-10-05): the player's files as a whole.

The game keeps three files in its folder (`paths.user_dir`, platform/defaults.py): save.json, the progress;
settings.json; and keys.json, the keys and the controllers' buttons.  Settings -> Miscellaneous works on them
whole:

* **Clear all saves** empties save.json - coins, diamonds, the weapons and their levels, the power-ups, the
  missions, the challenges and their stars, the statistics, the Endless high score, the tarot hand - and keeps
  the other two.  The objects that hold the progress in memory are let go, so each is made again from the
  empty file the next time it is asked for, as on a first start.
* **Open game data folder** (Windows, the Mac) shows that folder, to copy the files from or into.
* **Export backup** and **Import backup** (Android, whose folder no other app can reach) put the three files
  in one zip, "AudioDefence backup.zip" in the AudioDefence folder in Documents, written over by each export,
  and bring them back from it (user request).  Nothing goes online.  Android shows a game only the files it
  made itself, and none once it has been uninstalled, so a game installed again chooses the file in Android's
  own picker instead (Bridge.findBackup, pickFileToOpen).  A backup takes the place of all three files, and the
  game then closes, so that it starts again with them rather than with what it still had in memory.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import zipfile

from .. import paths
from ..platform import host
from ..platform.defaults import UserDefaults

log = logging.getLogger('game.saves')

#: the three files, in the order of SplitDefaults.stores
FILES = ('save.json', 'settings.json', 'keys.json')
#: the largest backup, or file in one, that Import takes: a backup is a few kilobytes
MOST = 4 * 1024 * 1024
#: what a backup is called, in the AudioDefence folder in Documents (Bridge.BACKUP_NAME)
BACKUP_NAME = 'AudioDefence backup.zip'


def clear_progress() -> None:
    """Clear all saves: save.json emptied and written, and everything that holds the progress in memory made
    again from it when next asked for."""
    from .challenge_data import ChallengeData
    from .inventory import Inventory
    from .missions import MissionManager
    from .persistent_stats import PersistentStats
    from .weapon_manager import WeaponManager
    store = UserDefaults.standard().save
    store.replace({})
    store.synchronize()
    for kind in (Inventory, ChallengeData, MissionManager, PersistentStats, WeaponManager):
        kind._shared = None
    log.info('all saves cleared')


def open_folder() -> bool:
    """Open game data folder: the folder in File Explorer, or in the Finder on the Mac."""
    folder = paths.user_dir()
    try:
        if host.MAC:
            subprocess.Popen(['open', folder])
        else:
            os.startfile(folder)                          # Windows only, which is where this is offered
    except (OSError, AttributeError) as exc:
        log.warning('the game data folder could not be opened: %s', exc)
        return False
    return True


def write_backup(path: str) -> None:
    """The three files, as they are now, in one zip at `path`."""
    UserDefaults.standard().synchronize()
    folder = paths.user_dir()
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as backup:
        for name in FILES:
            source = os.path.join(folder, name)
            if os.path.exists(source):
                backup.write(source, name)


def read_backup(path: str):
    """{file name: contents} from the backup at `path`, or None if it is not one.  A backup is a zip with
    save.json in it, and settings.json and keys.json if it has them, each a JSON object.  They are found by
    name wherever they are in it, so a computer's game folder zipped by hand is taken as well."""
    found = {}
    try:
        if os.path.getsize(path) > MOST:
            return None
        with zipfile.ZipFile(path) as backup:
            for info in backup.infolist():
                name = info.filename.replace('\\', '/').rsplit('/', 1)[-1]
                if name in FILES and name not in found and info.file_size <= MOST:
                    found[name] = json.loads(backup.read(info).decode('utf-8-sig'))
    except (OSError, ValueError, EOFError, RuntimeError, NotImplementedError, zipfile.BadZipFile,
            zipfile.LargeZipFile):                        # not a zip, damaged, locked, or not JSON inside
        return None
    if 'save.json' not in found or not all(isinstance(contents, dict) for contents in found.values()):
        return None
    return found


def restore(found: dict) -> None:
    """Import backup: the backup's files in place of the player's, written at once, and nothing more written
    after them (UserDefaults.frozen) - the game is closed next, and starts again with them."""
    defaults = UserDefaults.standard()
    for store, name in zip(defaults.stores, FILES):
        if name in found:
            store.replace(found[name])
            store.synchronize()
    UserDefaults.frozen = True
    log.info('backup imported: %s', ', '.join(name for name in FILES if name in found))
