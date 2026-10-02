"""PORT ADDITION (user request, 2026-10-02): how long the speech takes to read a line, and an item's hint read
on its own after it.

VoiceOver reads an element - its label and its traits - and then, once it has finished and a moment has
passed, the element's hint, on its own; a player can turn hints off in VoiceOver's own settings.  The port
used to read the two as one sentence ("Language, English. The language the port's own text...").  It reads
them as VoiceOver does now: the item first, then, once the item has been read and the pause chosen in the
Speech tab has passed (`GameParameters.hint_pause`), its hint.  With Hints off in that tab there is no hint.

Anything the player does in between takes the hint away, so it never talks over what they did next: a key
(ui/host.py), a touch on the phone (android_main.py), and anything said - the cursor moving, a change being
announced, the speech being stopped (`Speech.lines` counts all of those).  An item read again has its hint
read again.

When the item has been read is known for the game's own voice: SAPI 5, the Mac's system voice and the
phone's text-to-speech say when they have finished (`Speech.still_speaking`, built for the Extra mode's
story).  A screen reader cannot be asked - NVDA's controller client only speaks, cancels, brailles and says
whether NVDA is running, and Prism and VoiceOver's Apple Event only hand a line over - so its reading is
timed from the words in the line (`reading_seconds`), at the pace the player measured in the Speech tab's
Speech calibration row, or at DEFAULT_WORDS_PER_MINUTE until they have.  The story's screen uses the same
timing (ui/gameplay_screen.StoryScreen).

A braille display is read at the reader's own pace, so it is given the item and its hint together, at once,
the way NVDA puts an object's description beside its name; the hint said later is not brailled again, which
would take the item off the display a second after it arrived (`Screen.speak_element`).
"""
from __future__ import annotations

import logging

log = logging.getLogger('ui.reading')

#: How fast a screen reader is taken to read: an ordinary speaking pace (the pace of an audiobook, and about
#: what a screen reader's default rate reads English at).  A player who listens faster waits a little longer
#: than they need, which is the side to err on.  The Extra mode's story and the hints both time a screen
#: reader by it until the player has measured their own (Speech calibration, ui/settings.py).
DEFAULT_WORDS_PER_MINUTE = 180.0
#: PORT ADDITION (user request, 2026-10-02): seconds a screen reader's hint waits after its item even with
#: Pause before hints at 0, until Speech calibration has been done.  Timed at the default pace above, the
#: end of the item is a guess, and a guess a little early hands the hint over before the item is done; a
#: fifth of a second keeps the two apart.  Once the pace has been measured, 0 means 0.  The game's own
#: voices say when they have finished, so for them 0 is already "right after the voice ends" and this
#: does not apply.
UNCALIBRATED_LEAST_PAUSE = 0.2
#: A measured pace outside these cannot be a press at the end of the reading, and is turned away: faster
#: than even the fastest listeners set a screen reader with its rate boost, or slower than one at its
#: slowest rate.
FASTEST_WORDS_PER_MINUTE = 1200.0
SLOWEST_WORDS_PER_MINUTE = 60.0
#: how often a waiting hint looks to see whether it is due
POLL = 0.05


def word_count(text) -> int:
    return len(str(text or '').split())


def seconds_per_word() -> float:
    """The time a screen reader is taken to need for one word: as measured, or at the default pace."""
    from ..game.parameters import GameParameters
    measured = GameParameters.shared().speech_word_time()
    return measured if measured is not None else 60.0 / DEFAULT_WORDS_PER_MINUTE


def measured_pace(seconds: float, words: int):
    """A calibration's result: seconds a word, or 'early' or 'late' when the press cannot have been at the
    end of the reading (FASTEST_WORDS_PER_MINUTE, SLOWEST_WORDS_PER_MINUTE)."""
    per_word = seconds / max(1, words)
    if per_word < 60.0 / FASTEST_WORDS_PER_MINUTE:
        return 'early'
    if per_word > 60.0 / SLOWEST_WORDS_PER_MINUTE:
        return 'late'
    return per_word


def reading_seconds(text) -> float:
    """How long a screen reader is taken to need to read this."""
    return word_count(text) * seconds_per_word()


def hint_for(element) -> str:
    """What is read after `element` on its own: its hint, in a controller's words when those are chosen -
    or nothing, with Hints off in the Speech tab."""
    from ..game.parameters import GameParameters
    if not GameParameters.shared().speak_hints():
        return ''
    return element.spoken_hint()


def with_hint(element) -> str:
    """The element and its hint as one line, for reading a whole screen out in one go (the phone's
    two-finger swipe), where there is no pause to put between them: with Hints off, the element alone."""
    from .screens import joined
    return joined([element.spoken(), hint_for(element)])


class _Waiting:
    __slots__ = ('hint', 'said', 'line', 'at', 'quiet_since')

    def __init__(self, hint: str, said: str, line: int, at: float):
        self.hint = hint                                  # what is read when it is due
        self.said = said                                  # the line read before it, which it waits for
        self.line = line                                  # Speech.lines as that line was handed over
        self.at = at                                      # and when
        self.quiet_since = None                           # the game's own voice: when it fell quiet


class Hints:
    """The one hint waiting to be read, if there is one."""

    _shared: 'Hints | None' = None

    @classmethod
    def shared(cls) -> 'Hints':
        if cls._shared is None:
            cls._shared = Hints()
        return cls._shared

    def __init__(self):
        self.waiting: _Waiting | None = None
        self._timer = None

    def follow(self, said: str, hint: str) -> None:
        """`said` has just been handed to the speech; `hint` is read after it.  Any hint still waiting goes."""
        from ..platform.runloop import RunLoop
        from ..platform.speech import Speech
        self.cancel()
        if not hint:
            return
        loop = RunLoop.main()
        self.waiting = _Waiting(hint, said, Speech.shared().lines, loop.now())
        # a run-loop timer, not the screen's frame: it runs under any screen, the paused game's included
        self._timer = loop.schedule_timer(POLL, self._check, True)

    def cancel(self) -> None:
        """The player did something, or something else was said: the waiting hint is not read."""
        self.waiting = None
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def due_in(self, now: float):
        """Seconds until the waiting hint is read - 0 when it is due - or None while the game's own voice is
        still reading the line before it, or when nothing waits."""
        from ..game.parameters import GameParameters
        from ..platform.speech import Speech
        w = self.waiting
        if w is None:
            return None
        params = GameParameters.shared()
        pause = params.hint_pause()
        speaking = Speech.shared().still_speaking()
        if speaking is None:                              # a screen reader: the time the line takes to read
            if params.speech_word_time() is None:         # at a guessed pace: never quite at once
                pause = max(pause, UNCALIBRATED_LEAST_PAUSE)
            return max(0.0, w.at + reading_seconds(w.said) + pause - now)
        if speaking:
            w.quiet_since = None
            return None
        if w.quiet_since is None:                         # the game's own voice has just finished
            w.quiet_since = now
        return max(0.0, w.quiet_since + pause - now)

    def _check(self) -> None:
        from ..platform.runloop import RunLoop
        from ..platform.speech import Speech
        w = self.waiting
        speech = Speech.shared()
        if w is None or speech.lines != w.line:           # something else has been said, or stopped
            self.cancel()
            return
        if self.due_in(RunLoop.main().now()) != 0.0:
            return
        self.cancel()
        # queued, not interrupting: a screen reader slower than it is timed at finishes the line first.  Not
        # brailled: the display has had it since the line was (Screen.speak_element).
        speech.speak(w.hint, interrupt=False, braille='')
