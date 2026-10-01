"""PORT ADDITION (Android build): find a newer app and hand it to Android to install.  On the phone this
module is `platform.updater` (see platform/__init__.py), so ui/updates.py drives it with the same screens
as the desktop's: the quiet check when the main menu opens, Check for updates, Yes, No and Skip this
version, and a download that says how far it has got.

**The check is the desktop's.**  The latest release of the same repository, compared with this app's
`VERSION` by `version.is_newer`.  What the phone takes from the release is the app,
`AudioDefence-Android-<version>.apk`, uploaded beside the Windows and Mac zips; the desktop updater only
looks at zips, so the two never take each other's file.

**The network is Java's.**  `Bridge.fetchText` and `Bridge.download` use HttpURLConnection, which trusts
the phone's own certificates: the Python inside the app may have no certificate store to check GitHub's
against.  A download runs on a thread of its own here while this one reads how far it has got.

**Installing is Android's.**  The whole app comes down each time - an APK cannot be patched in place -
and `Bridge.installApk` hands it to Android's PackageInstaller, which asks the player to confirm on a
screen of its own and replaces the app, closing the game.  Progress cannot be lost by it: the saves are in
the app's files folder (``paths.user_dir``), which Android keeps across an update; only uninstalling
the app removes them.  Android installs nothing from an app until the player has allowed that app, once,
in its settings; ui/updates.py asks for that first (`allowed_to_install`, `open_install_settings`).

**A download waits** in ``updates/<version>`` of the save folder with a marker, as a desktop one does, so
a player who answers Not yet, cancels Android's screen, or whose app Android closes when it is allowed
to install is offered it again at the next start without fetching it again.

Missing files are not looked for: the phone's game data is unpacked from the APK at every install
(MainActivity), so a file gone missing is back by the next update, and a sound cannot be fetched on its
own from a release that has no zip for the phone.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading

from . import version
from .. import paths
from .jbridge import bridge

log = logging.getLogger('platform.updater')

#: the repository the app updates itself from.  The same as `REPOSITORY` in platform/updater.py, which the
#: phone cannot import (it reads zips with remotezip, which the APK leaves out): change both together.
REPOSITORY = 'lbk2907/AudioDefence'
LATEST_RELEASE = 'https://api.github.com/repos/%s/releases/latest' % REPOSITORY
RELEASES_PAGE = 'https://github.com/%s/releases' % REPOSITORY
USER_AGENT = 'AudioDefence-Updater'
TIMEOUT = 20
#: the app's name on a release, before and after its version: AudioDefence-Android-26.10.01-1.apk
ASSET_PREFIX = 'AudioDefence-Android-'
ASSET_SUFFIX = '.apk'
#: written beside the APK once it has all come down: it is then an update waiting to be installed
READY_MARKER = 'ready.json'
#: how often a running download is asked how far it has got
POLL = 0.25

#: PackageInstaller's statuses that are worth more than Android's own words (android.content.pm)
STATUS_FAILURE_CONFLICT = 5
STATUS_FAILURE_STORAGE = 6


class UpdateError(Exception):
    """Something went wrong that the player should be told about, in words they can act on.

    The words go into a line of the screen's own - "Could not check for updates: %s." - which is
    translated as it is said, the words in the gap with it.  `message=` is how the localization tools
    find them to offer a translator."""

    def __init__(self, message: str):
        super().__init__(message)


class Release:
    def __init__(self, data: dict):
        self.tag = str(data.get('tag_name') or '')
        self.name = str(data.get('name') or self.tag)
        self.notes = str(data.get('body') or '').strip()
        self.url = str(data.get('html_url') or RELEASES_PAGE)
        self.asset_name = ''
        self.asset_url = ''
        self.asset_size = 0
        apps = sorted((asset for asset in data.get('assets') or () if self.suits(str(asset.get('name', '')))),
                      key=lambda asset: str(asset.get('name', '')).lower())
        if apps:
            self.asset_name = str(apps[0]['name'])
            self.asset_url = str(apps[0]['browser_download_url'])
            self.asset_size = int(apps[0].get('size') or 0)

    @staticmethod
    def suits(name: str) -> bool:
        low = name.lower()
        return low.startswith(ASSET_PREFIX.lower()) and low.endswith(ASSET_SUFFIX)

    def __repr__(self) -> str:
        return '<Release %s %s>' % (self.tag, self.asset_name or 'no app')


class Plan:
    """What installing a release takes: always the whole app, so never nothing."""

    nothing_to_do = False

    def __init__(self, release: Release, folder: str):
        self.release = release
        self.staging = os.path.join(folder, os.path.basename(release.asset_name))   # the APK, once it is down
        self.fetch = [release.asset_name]
        self.remove = []

    @property
    def download_size(self) -> int:
        return self.release.asset_size


# ================================================================================== what can be done here
def can_update() -> tuple:
    """(allowed, why not).  The app can always look; whether Android lets it install is asked at the end,
    when there is something to install (`allowed_to_install`)."""
    return True, ''


def updates_dir() -> str:
    path = os.path.join(paths.user_dir(), 'updates')
    os.makedirs(path, exist_ok=True)
    return path


def pending_update():
    """An app already downloaded and not yet installed: (apk, tag, []), or (None, '', [])."""
    root = os.path.join(paths.user_dir(), 'updates')
    best = (None, '', [])
    if not os.path.isdir(root):
        return best
    here = version.current()
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        try:
            with open(os.path.join(folder, READY_MARKER), encoding='utf-8') as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            continue
        tag = str(saved.get('tag') or '')
        apk = os.path.join(folder, os.path.basename(str(saved.get('apk') or '')))
        # one whose version is already running has been installed: its folder is left over, not waiting
        if tag and os.path.isfile(apk) and version.is_newer(tag, here) and (
                not best[1] or version.is_newer(tag, best[1])):
            best = (apk, tag, [])
    return best


def clean_up_staging() -> None:
    """Throw away half-finished downloads, and apps that have been installed since.  An app waiting to be
    installed (`pending_update`) is kept."""
    root = os.path.join(paths.user_dir(), 'updates')
    if not os.path.isdir(root):
        return
    keep, _tag, _remove = pending_update()
    keep = os.path.dirname(keep) if keep else None
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path) and path != keep:
            shutil.rmtree(path, ignore_errors=True)


# ============================================================================================ the check
def _api(url: str) -> dict:
    answer = str(bridge().fetchText(url, 'application/vnd.github+json', USER_AGENT, TIMEOUT * 1000) or '')
    code, _newline, body = answer.partition('\n')
    code = int(code) if code.isdigit() else 0
    if code == 0:
        log.info('could not reach GitHub: %s', body)
        raise UpdateError(message='could not reach GitHub. Check your internet connection')
    if code == 404:
        raise UpdateError(message='there are no releases to update to yet')
    if code in (403, 429):
        raise UpdateError(message='GitHub is asking us to wait before checking again. Try later')
    if code != 200:
        raise UpdateError(message='GitHub answered with an error, number %d' % code)
    try:
        return json.loads(body)
    except ValueError as exc:
        raise UpdateError(message='GitHub sent something we could not read') from exc


def check() -> Release | None:
    """The newest release when it is newer than this app, else None.  Runs on a worker thread."""
    release = Release(_api(LATEST_RELEASE))
    if not release.tag:
        raise UpdateError(message='the newest release has no version number')
    here = version.current()
    if not here:
        log.info('this app has no version, so %s is not offered', release.tag)
        return None
    if not version.is_newer(release.tag, here):
        log.info('%s is the newest release and this app is %s', release.tag, here)
        return None
    if not release.asset_url:
        raise UpdateError(message='release %s has no app to download for Android' % release.tag)
    return release


# ========================================================================================= the download
def build_plan(release: Release, cancelled=None) -> Plan:
    folder = os.path.join(updates_dir(), re.sub(r'[^\w.\-]', '_', release.tag) or 'release')
    os.makedirs(folder, exist_ok=True)
    return Plan(release, folder)


def _ready(plan: Plan) -> bool:
    apk, tag, _remove = pending_update()
    return apk == plan.staging and tag == plan.release.tag


def download(plan: Plan, progress=None, cancelled=None) -> str:
    """Fetch the app to `plan.staging`, saying how far it has got as `progress(done, total, 'whole')`.
    Raises UpdateError('cancelled') when `cancelled()` comes true."""
    release = plan.release
    if _ready(plan):                                      # down already, from a download put off
        return plan.staging
    part = plan.staging + '.part'
    phone = bridge()
    outcome = []
    worker = threading.Thread(target=lambda: outcome.append(str(phone.download(
        release.asset_url, part, USER_AGENT, TIMEOUT * 1000) or '')), name='apk-download', daemon=True)
    worker.start()
    stopping = False
    while worker.is_alive():
        worker.join(POLL)
        if cancelled is not None and cancelled() and not stopping:
            phone.cancelDownload()
            stopping = True
        if progress is not None:
            done, total = (int(n) for n in phone.downloadProgress())
            progress(done, total or release.asset_size, 'whole')
    result = outcome[0] if outcome else 'error the download stopped'
    if result:
        try:
            os.remove(part)
        except OSError:
            pass
        if result == 'cancelled':
            raise UpdateError(message='cancelled')
        log.info('the app did not come down: %s', result)
        code = result.split()[1] if result.startswith('http ') else ''
        if code.isdigit():
            raise UpdateError(message='GitHub answered with an error, number %d' % int(code))
        raise UpdateError(message='the download did not finish. Check your internet connection')
    if release.asset_size and os.path.getsize(part) != release.asset_size:
        os.remove(part)
        raise UpdateError(message='the download came out the wrong size. Try again')
    os.replace(part, plan.staging)
    with open(os.path.join(os.path.dirname(plan.staging), READY_MARKER), 'w', encoding='utf-8') as fh:
        json.dump({'tag': release.tag, 'apk': os.path.basename(plan.staging)}, fh)
    return plan.staging


def apply(*a, **k):
    """The desktop's hand-off to a script; the phone hands the app to Android instead (`hand_to_installer`)."""
    raise UpdateError('the app is installed by Android')                 # never reached: ui/updates.py


def size_text(byte_count: int) -> str:
    """'42.1 megabytes' - what a speech engine should say, not '42.1 MB'."""
    if byte_count >= 1 << 20:
        return '%.1f megabytes' % (byte_count / float(1 << 20))
    if byte_count >= 1 << 10:
        return '%.0f kilobytes' % (byte_count / float(1 << 10))
    return '%d bytes' % byte_count


# ========================================================================================= installing it
def allowed_to_install() -> bool:
    """Whether Android lets this app install apps: Install unknown apps, in its settings."""
    return bool(bridge().canInstallPackages())


def open_install_settings() -> bool:
    """Open that setting, for this app.  False when the phone has no such screen to open."""
    return bool(bridge().openInstallSettings())


def in_foreground() -> bool:
    """Whether the game is the app on the screen, rather than Android's settings or its install screen."""
    return bool(bridge().inForeground())


def hand_to_installer(apk: str) -> None:
    """Give the app to Android's PackageInstaller.  `installer_state` follows it from there."""
    bridge().installApk(apk)


def installer_state() -> tuple:
    """(state, status, Android's words): state is '' before anything, 'preparing' while the app is copied
    to Android, 'confirm' once Android's screen is up, 'done', 'aborted' when the player said no there, or
    'failed', with PackageInstaller's status number and what Android said about it."""
    state, _newline, rest = str(bridge().installState() or '').partition('\n')
    status, _newline, said = rest.partition('\n')
    return state, int(status) if status.lstrip('-').isdigit() else 0, said.strip()


# ======================================================================= the desktop's names, unused here
def missing_files() -> list:
    return []


def current_release():
    return None


def restore(*a, **k):
    raise UpdateError('nothing is missing')                              # never reached: missing_files
