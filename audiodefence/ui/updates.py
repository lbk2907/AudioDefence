"""PORT ADDITION: the screens and the background work that offer a new build to the player.

The engine is in ``platform/updater.py``; this is the part the player meets.  Three pieces:

* ``UpdateService`` - one worker thread at a time, doing the waiting-on-a-network parts, handing every
  result back to the run loop with ``call_soon_threadsafe`` so nothing off the main thread touches a
  screen.  The main menu asks it to look quietly when it opens; its Check for updates button asks it to
  look and to say so either way.
* ``offer`` - the Yes, No or Skip this version the player answers.  It is the game's own alert, so it is
  read and driven the way every other screen is, rather than a Windows dialog a screen reader would
  announce differently.
* ``DownloadScreen`` - what is on screen while the files come down: it says how far along it is at
  intervals rather than on every file, because a hundred announcements a second is not progress, and
  Escape stops it.
* ``offer_restore`` and ``RestoreScreen`` - the same for files of this build that have gone missing
  (user request, 2026-09-29): asked about when the game starts, and offered by Check for updates when there
  is nothing newer, then put back from the release of the version the player already has.
* ``ask_to_install`` and ``InstallScreen`` - the Android app's last step in place of the restart: the
  downloaded app is handed to Android, which installs it (platform/updater_android.py).  Everything before
  it - the checks, the offer, the download - is the desktop's, on the phone as on a computer.

Nothing here blocks the game: the check is a single call to GitHub, and a player who never opens this
screen never waits for it.
"""
from __future__ import annotations

import logging
import threading

from ..game.parameters import GameParameters
from ..platform import updater, version
from ..platform.host import ANDROID
from ..platform.runloop import RunLoop
from ..platform.updater import UpdateError
from .host import AlertScreen
from .screens import MenuItem, MenuScreen, Screen

log = logging.getLogger('ui.updates')

#: how often the download screen says where it has got to.  Long enough not to talk over itself, short
#: enough that a slow connection does not feel like a hang.
PROGRESS_INTERVAL = 3.0


class UpdateService:
    """The background half.  One job at a time; asking again while it is busy does nothing."""

    _shared: 'UpdateService | None' = None

    @classmethod
    def shared(cls) -> 'UpdateService':
        if cls._shared is None:
            cls._shared = UpdateService()
        return cls._shared

    def __init__(self):
        self.busy = False
        self.release = None                               # the newest release, once one has been found
        self.checked = False                              # whether a check has finished this session
        self._cancel = False

    # --- the check -------------------------------------------------------------------------------
    def check(self, on_result) -> bool:
        """Look for a newer build.  `on_result(release_or_None, error_or_None)` runs on the main thread."""
        if self.busy:
            return False
        self.busy = True

        def work():
            found, problem = None, None
            try:
                found = updater.check()
            except UpdateError as exc:
                problem = str(exc)
            except Exception as exc:                      # a bug here must not take the game with it
                log.exception('the update check failed')
                problem = 'something went wrong while checking: %s' % exc
            RunLoop.main().call_soon_threadsafe(lambda: self._checked(found, problem, on_result))

        threading.Thread(target=work, name='update-check', daemon=True).start()
        return True

    def _checked(self, release, problem, on_result) -> None:
        self.busy = False
        self.checked = True
        self.release = release
        on_result(release, problem)

    # --- the download ----------------------------------------------------------------------------
    def install(self, release, on_progress, on_done) -> bool:
        """Work out what changed, fetch it, stage it.  `on_done(plan_or_None, error)` on the main thread."""
        if self.busy:
            return False
        self.busy = True
        self._cancel = False

        def work():
            plan, problem = None, None
            try:
                plan = updater.build_plan(release, cancelled=lambda: self._cancel)
                if plan.fetch is None:                    # ranges refused: the whole archive comes down
                    RunLoop.main().call_soon_threadsafe(
                        lambda: on_progress(0, release.asset_size, 'whole'))
                updater.download(plan, progress=lambda d, t, w: RunLoop.main().call_soon_threadsafe(
                    lambda d=d, t=t, w=w: on_progress(d, t, w)), cancelled=lambda: self._cancel)
                if plan.nothing_to_do:
                    problem = 'this build already has every file that release has'
                    plan = None
            except UpdateError as exc:
                problem = None if str(exc) == 'cancelled' else str(exc)
                plan = None
            except Exception as exc:
                log.exception('the update download failed')
                problem = 'something went wrong while downloading: %s' % exc
                plan = None
            RunLoop.main().call_soon_threadsafe(lambda: self._installed(plan, problem, on_done))

        threading.Thread(target=work, name='update-download', daemon=True).start()
        return True

    def cancel(self) -> None:
        self._cancel = True

    # --- files that went missing -----------------------------------------------------------------
    def find_missing(self, on_result) -> None:
        """Which files of this build are not there.  `on_result(missing)` on the main thread.  Only looks,
        so it does not wait for a download or a check to finish."""

        def work():
            try:
                missing = updater.missing_files()
            except Exception:                             # noqa: BLE001 - never worth stopping the game for
                log.exception('looking for missing files failed')
                missing = []
            RunLoop.main().call_soon_threadsafe(lambda: on_result(missing))

        threading.Thread(target=work, name='missing-files', daemon=True).start()

    def restore(self, missing, on_progress, on_done) -> bool:
        """Put the missing files back from this version's release.  `on_done(put_back, absent, error)` on
        the main thread; `put_back` is None when it was stopped."""
        if self.busy:
            return False
        self.busy = True
        self._cancel = False

        def work():
            put_back, absent, problem = None, [], None
            try:
                release = updater.current_release()
                put_back, absent = updater.restore(
                    release, missing, cancelled=lambda: self._cancel,
                    progress=lambda d, t, w: RunLoop.main().call_soon_threadsafe(
                        lambda d=d, t=t, w=w: on_progress(d, t, w)))
            except UpdateError as exc:
                problem = None if str(exc) == 'cancelled' else str(exc)
            except Exception as exc:
                log.exception('putting the missing files back failed')
                problem = 'something went wrong while downloading: %s' % exc
            RunLoop.main().call_soon_threadsafe(lambda: self._restored(put_back, absent, problem, on_done))

        threading.Thread(target=work, name='restore-files', daemon=True).start()
        return True

    def _restored(self, put_back, absent, problem, on_done) -> None:
        self.busy = False
        on_done(put_back, absent, problem)

    def _installed(self, plan, problem, on_done) -> None:
        self.busy = False
        on_done(plan, problem)


# ===================================================================================== the Yes/No offer
def notes_summary(release) -> str:
    """The release notes, shortened to something worth hearing before a Yes or No."""
    text = ' '.join((release.notes or '').split())
    if len(text) > 300:
        text = text[:300].rsplit(' ', 1)[0] + '...'
    return text


def offer(host, release, on_declined=None) -> None:
    """Ask whether to install, and do it if the answer is yes."""
    allowed, why_not = updater.can_update()
    message = 'Version %s is available. You have %s.' % (version.text(release.tag), version.text())
    notes = notes_summary(release)
    if notes:
        message += ' ' + notes
    if not allowed:
        host.push_overlay(AlertScreen(host, 'Update available', message + ' But ' + why_not + '.',
                                      [('OK', None)]))
        return
    message += ' Would you like to download and install it now?'

    def yes():
        host.push_overlay(DownloadScreen(host, release))

    # "No" is not now: the next start asks again.  "Skip this version" is never for this one: the check at
    # start-up passes it over, and a newer release is offered as usual.  Check for updates on the main menu
    # is a question the player asks, so it still offers a skipped version - which is how to change your mind.
    def no():
        if on_declined is not None:
            on_declined()

    def skip():
        GameParameters.shared().set_skipped_update(release.tag)
        Screen.speak('Version %s skipped.' % version.text(release.tag))
        if on_declined is not None:
            on_declined()

    host.push_overlay(AlertScreen(host, 'Update available', message, [
        ('Yes', yes),
        ('No', no, 'Asks again the next time the game starts.'),
        ('Skip this version', skip, 'Not offered again when the game starts, though a newer version will be. '
                                    'Check for updates on the main menu still finds it.'),
    ]))


# ==================================================================================== the download screen
class DownloadScreen(MenuScreen):
    """What is on screen while the update comes down.  One row: stop."""

    def __init__(self, host, release):
        super().__init__(host, title='Downloading update')
        self.release = release
        self.plan = None
        self.done = 0
        self.total = 0
        self.finished = False
        self._last_said = 0.0
        self.items = [MenuItem('Stop', self._stop, hint='Press Enter to stop downloading.')]
        self.back_action = self._stop

    def on_present(self) -> None:
        if ANDROID:                                       # the whole app, every time: nothing to work out
            self.speak('Downloading update %s, %s.' % (version.text(self.release.tag),
                                                       updater.size_text(self.release.asset_size)))
        else:
            self.speak('Downloading update %s. Working out what has changed.' % version.text(self.release.tag))
        started = UpdateService.shared().install(self.release, self._progress, self._done)
        if not started:
            self.speak('Another update job is already running.')
            self.host.pop_overlay()

    # --- from the worker -------------------------------------------------------------------------
    def _progress(self, done: int, total: int, _what: str) -> None:
        self.done, self.total = done, total
        now = RunLoop.main().now()
        if now - self._last_said < PROGRESS_INTERVAL:
            return
        self._last_said = now
        if total > 0:
            self.speak('%d per cent' % int(100.0 * done / total))

    def _done(self, plan, problem) -> None:
        self.finished = True
        if problem:
            self.host.pop_overlay()
            self.host.push_overlay(AlertScreen(self.host, 'Update failed', problem + '.', [('OK', None)]))
            return
        if plan is None:                                  # cancelled, or nothing to do
            self.host.pop_overlay()
            return
        self.plan = plan
        self.host.pop_overlay()
        self._ask_to_restart(plan)

    def _ask_to_restart(self, plan) -> None:
        if ANDROID:
            ask_to_install(self.host, plan.staging, self.release.tag, message=
                           'Version %s downloaded. Android installs it on a screen of its own, which asks '
                           'you to confirm. Your progress is kept. Install now?' % version.text(self.release.tag))
            return
        message = ('%s downloaded. The game has to close to put the new files in place, and it will '
                   'start again by itself. Your progress is kept. Restart now?'
                   % updater.size_text(plan.download_size or 0))
        ask_to_restart(self.host, plan.staging, plan.remove, message)

    # --- stopping --------------------------------------------------------------------------------
    def _stop(self) -> None:
        if self.finished:
            return
        UpdateService.shared().cancel()
        self.speak('Stopping the download.')


# ================================================================================ files that went missing
def file_names(missing) -> str:
    """The first few missing files by name, as a player hears them: a whole folder gone is not read out."""
    return ', '.join(name.rsplit('/', 1)[-1] for name in missing[:3])


def offer_restore(host, missing, newest: bool = False) -> None:
    """Ask whether to download the missing files again, and do it if the answer is yes.  `newest` is for
    Check for updates, which has just found there is nothing newer and says so first.

    Each case is a whole sentence, written inside the alert that says it, so that a translator is given the
    sentence rather than pieces of English to fit round (verify_localization finds text in the call that
    carries it)."""
    count, names = len(missing), file_names(missing)
    allowed, why_not = updater.can_update()

    def yes():
        host.push_overlay(RestoreScreen(host, missing))

    # "No" is not now, as it is for an update: the next start asks again (user request, 2026-09-29).
    def no():
        pass

    host.push_overlay(AlertScreen(host, 'Missing files', ' '.join(part for part in (
        'You have the newest version, %s.' % version.text() if newest else '',
        "One of the game's files is missing: %s." % names if count == 1 else
        "%i of the game's files are missing: %s." % (count, names) if count <= 3 else
        "%i of the game's files are missing, among them %s." % (count, names),
        'But ' + why_not + '.' if not allowed else
        'Would you like to download it again?' if count == 1 else 'Would you like to download them again?',
    ) if part), [('OK', None)] if not allowed else [
        ('Yes', yes),
        ('No', no, 'Asks again the next time the game starts.'),
    ]))


class RestoreScreen(MenuScreen):
    """What is on screen while the missing files come down.  One row: stop."""

    def __init__(self, host, missing):
        super().__init__(host, title='Downloading missing files')
        self.missing = list(missing)
        self.finished = False
        self._last_said = 0.0
        self.items = [MenuItem('Stop', self._stop, hint='Press Enter to stop downloading.')]
        self.back_action = self._stop

    def on_present(self) -> None:
        self.speak('Downloading the missing files.')
        if not UpdateService.shared().restore(self.missing, self._progress, self._done):
            self.speak('Another update job is already running.')
            self.host.pop_overlay()

    def _progress(self, done: int, total: int, _what: str) -> None:
        now = RunLoop.main().now()
        if now - self._last_said < PROGRESS_INTERVAL:
            return
        self._last_said = now
        if total > 0:
            self.speak('%d per cent' % int(100.0 * done / total))

    def _done(self, put_back, absent, problem) -> None:
        self.finished = True
        self.host.pop_overlay()
        if problem:
            self.host.push_overlay(AlertScreen(self.host, 'Download failed', problem + '.', [('OK', None)]))
            return
        if put_back is None:                              # stopped
            return
        one = len(put_back) == 1
        # A language file, or the readme, is read when it is wanted.  Anything else - a sound, a part of
        # the program - may have been looked for already, when the game started.
        restart = any('/' in name and not name.startswith('localization/') for name in put_back)
        self.host.push_overlay(AlertScreen(self.host, 'Missing files', ' '.join(part for part in (
            'The missing file is back.' if one else 'The %i missing files are back.' % len(put_back),
            ('Restart the game to use it.' if one else 'Restart the game to use them.') if restart else '',
            '%i could not be found in the release: %s.' % (len(absent), file_names(absent)) if absent else '',
        ) if part), [('OK', None)]))

    def _stop(self) -> None:
        if self.finished:
            return
        UpdateService.shared().cancel()
        self.speak('Stopping the download.')


def ask_to_restart(host, staging: str, remove, message: str) -> None:
    """Offer the restart that puts a downloaded update in place.

    Saying no is not the end of it: the files stay where they are and the next start offers them again,
    which is what the wording promises."""

    def yes():
        try:
            updater.apply(staging, remove)
        except UpdateError as exc:
            host.push_overlay(AlertScreen(host, 'Update failed', str(exc) + '.', [('OK', None)]))
            return
        host.quit_game()

    def later():
        Screen.speak('The update is ready. It will be offered again the next time you start the game.')

    host.push_overlay(AlertScreen(host, 'Update ready', message,
                                  [('Restart now', yes), ('Not yet', later)]))


# ================================================================ handing the app to Android (Android build)
def ask_to_install(host, apk: str, tag: str, message: str) -> None:
    """PORT ADDITION (Android build): the phone's ask_to_restart.  "Not yet" keeps the download, and the next
    start offers it again, as on the desktop."""

    def yes():
        host.push_overlay(InstallScreen(host, apk, tag))

    def later():
        Screen.speak('The update is ready. It will be offered again the next time you start the game.')

    host.push_overlay(AlertScreen(host, 'Update ready', message, [('Install now', yes), ('Not yet', later)]))


class InstallScreen(MenuScreen):
    """PORT ADDITION (Android build): what is on screen while Android installs the app.  One row: leave.

    Android installs nothing from an app until the player has allowed that app once, in its settings.  When
    that is still to do, the setting is opened, and the screen waits for the player to come back to the game
    with it on.  Then the app goes to Android's PackageInstaller, which asks the player on a screen of its
    own and closes the game to replace it.  Neither of Android's screens is the game's, so the game cannot
    read them out; what is said before each is what the player needs to get through it.  Some versions of
    Android close the app when it is allowed to install, and then the next start offers the download again
    (``check_on_start``)."""

    #: how often Android is asked whether anything has changed
    POLL = 0.5

    def __init__(self, host, apk: str, tag: str):
        super().__init__(host, title='Installing update')
        self.apk, self.tag = apk, tag
        self.state = ''                                   # 'allowing', then 'installing'; '' once it is over
        self.left = False                                 # whether the player has gone to Android's settings
        self._last_asked = 0.0
        self.items = [MenuItem('Leave', self._leave, hint='Press Enter to leave the update for now. It is '
                                                          'offered again the next time you start the game.')]
        self.back_action = self._leave

    def on_present(self) -> None:
        if updater.allowed_to_install():
            self._hand_over()
            return
        self.state = 'allowing'
        self.speak("Android has to allow this app to install updates, once. Opening that setting now. Turn on "
                   "Allow from this source, then go back to the game. The game cannot read Android's settings "
                   "out, so use TalkBack there if you need it, and turn it off again when you come back.")
        if not updater.open_install_settings():
            self._finish(title='Update not installed',
                         message="The setting could not be opened. In Android's settings, find Install unknown "
                                 'apps, allow Audio Defence there, and start the game again.')

    def frame(self) -> None:
        if not self.state:
            return
        now = RunLoop.main().now()
        if now - self._last_asked < self.POLL:
            return
        self._last_asked = now
        if self.state == 'allowing':
            if not updater.in_foreground():
                self.left = True
            elif updater.allowed_to_install():
                self._hand_over()
            elif self.left:
                self._finish(title='Update not installed',
                             message='This app is still not allowed to install updates, so the update was not '
                                     'installed. It is offered again the next time you start the game.')
            return
        state, status, said = updater.installer_state()
        if state == 'aborted':
            self._finish(title='Update not installed',
                         message='The update was not installed. It is offered again the next time you start the '
                                 'game.')
        elif state == 'done':
            self._finish(title='Update installed', message='The update is installed. Start the game again to use it.')
        elif state == 'failed':
            self._finish(title='Update failed', message=(
                'There is not enough free space on the phone for the update.'
                if status == updater.STATUS_FAILURE_STORAGE else
                'Android would not put the update over the app on this phone, which was most likely signed with a '
                'different key.' if status == updater.STATUS_FAILURE_CONFLICT else
                'Android could not install the update: %s.' % (said or status)))

    def _hand_over(self) -> None:
        self.state = 'installing'
        self.speak('Handing the update to Android. In a moment Android asks on a screen of its own whether to '
                   'update the app, which the game cannot read out: use TalkBack to press Update if you need '
                   'it. The game closes while Android installs it, and your progress is kept. When it is done, '
                   'start the game again.')
        updater.hand_to_installer(self.apk)

    def _finish(self, title: str, message: str) -> None:
        self.state = ''
        if self.host.top() is self:
            self.host.pop_overlay()
        self.host.push_overlay(AlertScreen(self.host, title, message, [('OK', None)]))

    def _leave(self) -> None:
        self.state = ''
        if self.host.top() is self:
            self.host.pop_overlay()
        Screen.speak('The update is ready. It will be offered again the next time you start the game.')


def check_now(host, speak) -> None:
    """A check the player asked for, with the main menu's Check for updates button.

    The quiet check at start-up says nothing when there is no update, which is right when nobody asked;
    a check somebody pressed has to answer either way, or it looks broken."""
    service = UpdateService.shared()
    if service.busy:
        speak('Already checking. One moment.')
        return

    def result(release, problem):
        if problem:
            speak('Could not check for updates: %s.' % problem)
            return
        if release is not None:
            offer(host, release)                          # which puts back any missing file as well
            return

        def found(missing):
            if missing:
                offer_restore(host, missing, newest=True)
            else:
                speak('You have the newest version, %s.' % version.text())

        service.find_missing(found)

    if service.check(result):
        speak('Checking for updates.')


# ================================================================== the check the main menu starts quietly
def check_on_start(host, screen) -> None:
    """Called when the main menu opens.  Says nothing unless there is a build worth offering.

    The answer comes back seconds later, by which time the player may have walked into the armoury or
    started a game.  Interrupting that with an alert would be rude and, mid-wave, unfair, so the offer is
    only made while the menu that asked for it is still the screen in front."""
    updater.clean_up_staging()                        # half-finished downloads, and applied ones
    # An update that was downloaded and then put off is already on disk: finish that rather than ask
    # GitHub anything.  This runs whether or not the startup check is switched on, because the player
    # has already said yes to this one.
    waiting, tag, remove = updater.pending_update()
    if waiting is not None and ANDROID:
        ask_to_install(host, waiting, tag, message=
                       'Version %s was downloaded and is waiting. Android installs it on a screen of its '
                       'own, which asks you to confirm. Your progress is kept. Install now?' % version.text(tag))
        return
    if waiting is not None:
        allowed, _why_not = updater.can_update()
        if allowed:
            ask_to_restart(host, waiting, remove,
                           'Version %s was downloaded and is waiting. The game has to close to put it '
                           'in place, and it will start again by itself. Your progress is kept. '
                           'Restart now?' % version.text(tag))
            return
    params = GameParameters.shared()
    if not params.check_updates():
        return
    service = UpdateService.shared()
    if service.checked:                                   # once a session is enough
        return
    allowed, why_not = updater.can_update()
    if not allowed:
        log.info('not offering updates: %s', why_not)
        service.checked = True
        return

    # Missing files are looked for first, without the network, and asked about as the update is (user
    # request, 2026-09-29): at every start until they are back, and not at all with the startup check
    # switched off.  A newer version is offered in their place when there is one, since installing it puts
    # them back too.
    def missing_found(missing):
        if missing:
            log.info('%d files of this build are missing', len(missing))

        def result(release, problem):
            if problem:
                log.info('the quiet update check did not work out: %s', problem)
            elif release is not None and release.tag == params.skipped_update():
                log.info('%s was already declined', release.tag)
            elif release is not None:
                if host.top() is not screen:
                    log.info('%s is available, but the player has moved on; not interrupting', release.tag)
                    return
                offer(host, release)
                return
            if not missing:
                return
            if host.top() is not screen:
                log.info('files are missing, but the player has moved on; not interrupting')
                return
            offer_restore(host, missing)

        service.check(result)

    service.find_missing(missing_found)
