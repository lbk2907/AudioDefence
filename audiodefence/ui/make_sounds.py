"""PORT ADDITION (user request, 2026-10-05): the player's 3D sounds made before the game begins.

A `.sofa` in the player's `hrtf` folder with no `.mhr` as new as itself (s3d/makehrtf.py) is made when the game
starts, before the logo, on this screen, so it is plain when it is done: the screen says what it is making and
that Escape skips it, how far it has got every tenth of the way - as the phone says how far its unpacking has
got (android MainActivity) - each next file's name, and then what was made and what was not.  The game goes on
to the logo once that has been read.  Escape stops makemhr at once and goes on; what was not made is made the
next time the game starts.

It was made, at first, when Enter was pressed on Settings -> Sound -> 3D sound, in the background, and the list
did not open until the next Enter - which the user could not tell from a bug.
"""
from __future__ import annotations

import os
import threading

from .. import localization
from ..platform.runloop import RunLoop
from ..s3d import makehrtf
from .reading import reading_seconds
from .screens import MenuScreen, joined


def _name(sofa: str) -> str:
    return os.path.splitext(os.path.basename(sofa))[0]


class MakeSoundsScreen(MenuScreen):
    #: how far it has got is said at each tenth of the way, but not more often than this, in seconds
    SAY_EVERY = 2.5
    #: seconds after the last line has been read, at the measured pace, before the game goes on
    GO_ON_MARGIN = 0.5

    def __init__(self, host, files: list, then):
        names = [_name(sofa) for sofa in files]
        if len(files) == 1:
            opening = [localization.translate('Making a 3D sound from %s.' % names[0]),
                       localization.translate('Press Escape to skip it; it is made the next time the game starts.')]
        else:
            opening = [localization.translate('Making 3D sounds from %s and %d more.' % (names[0], len(files) - 1)),
                       localization.translate('Press Escape to skip them; they are made the next time the game '
                                              'starts.')]
        super().__init__(host, title=joined(opening))
        self.back_action = self.skip
        self.files, self.then = list(files), then
        self.lock = threading.Lock()
        self.working_on = 0                               # set by the worker: which file, how far, what came of each
        self.percent = 0.0
        self.results: list = []
        self.finished = False
        self.stopping = False
        self.said_file = 0                                # what has been said of it, on the main thread
        self.said_tenth = 0
        self.quiet_until = 0.0
        self.reported = False
        self.gone = False

    # --- the work, on a thread of its own --------------------------------------------------------------
    def on_present(self) -> None:
        super().on_present()                              # what it is making, and that Escape skips it
        self.quiet_until = RunLoop.main().now() + reading_seconds(localization.translate(self.title))
        threading.Thread(target=self.work, name='make 3D sounds', daemon=True).start()

    def work(self) -> None:
        for index, sofa in enumerate(self.files):
            if self.stopping:
                break
            with self.lock:
                self.working_on, self.percent = index, 0.0
            problem = makehrtf.make(sofa, progress=self.progressed, cancelled=lambda: self.stopping)
            with self.lock:
                self.results.append((sofa, problem))
            if problem == makehrtf.STOPPED:
                break
        with self.lock:
            self.finished = True

    def progressed(self, percent: float) -> None:
        with self.lock:
            self.percent = percent

    # --- what is said, on the main thread --------------------------------------------------------------
    def frame(self) -> None:
        super().frame()
        if self.reported:
            return
        with self.lock:
            working_on, percent, finished = self.working_on, self.percent, self.finished
            results = list(self.results)
        now = RunLoop.main().now()
        if finished:
            self.report(results)
            return
        if now < self.quiet_until:                        # the opening line, or the last, is still being read
            return
        if working_on != self.said_file:                  # the next file: its name, then its progress
            self.said_file, self.said_tenth = working_on, 0
            said = localization.translate('Now %s, %d of %d.' % (_name(self.files[working_on]), working_on + 1,
                                                                 len(self.files)))
            self.speak(said)
            self.quiet_until = now + reading_seconds(said)
            return
        tenth = int(percent // 10)
        if 0 < tenth < 10 and tenth > self.said_tenth:
            self.said_tenth = tenth
            said = localization.translate('%d percent' % (tenth * 10))
            self.speak(said)
            self.quiet_until = now + max(self.SAY_EVERY, reading_seconds(said))

    def report(self, results: list) -> None:
        """What was made and what was not, and on to the logo once it has been read."""
        self.reported = True
        made = [_name(sofa) for sofa, problem in results if not problem]
        lines = []
        if any(problem == makehrtf.STOPPED for _sofa, problem in results):
            lines.append(localization.translate('Skipped. What is not made yet is made the next time the game '
                                                'starts.'))
        if len(made) == 1:
            lines.append(localization.translate('3D sound ready: %s. Choose it in the Sound tab in Settings, '
                                                'under 3D sound.' % made[0]))
        elif made:
            lines.append(localization.translate('3D sounds ready: %s. Choose one in the Sound tab in Settings, '
                                                'under 3D sound.' % ', '.join(made)))
        for sofa, problem in results:
            if problem and problem != makehrtf.STOPPED:
                lines.append(localization.translate('%s could not be made into a 3D sound: %s'
                                                    % (_name(sofa), problem)))
        said = joined(lines)
        self.speak(said)
        RunLoop.main().call_later(reading_seconds(said) + self.GO_ON_MARGIN, self.go_on)

    def skip(self) -> None:
        """Escape: makemhr stopped, and on as soon as it has (`report` says so)."""
        if not self.stopping:
            self.stopping = True

    def key_down(self, event) -> None:
        if self.reported:                                 # what came of it is being read: any key goes on
            self.go_on()
            return
        super().key_down(event)

    def go_on(self) -> None:
        if self.gone:
            return
        self.gone = True
        self.then()
