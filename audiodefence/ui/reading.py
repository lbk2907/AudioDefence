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

When the item has been read is predicted, the same way for every voice (user request, 2026-10-02): the
words in the line times the seconds a word the player measured in the Speech tab's Speech calibration row
(`reading_seconds`), or at DEFAULT_WORDS_PER_MINUTE until they have.  The pause before the hint counts from
that moment.  The Extra mode's story is timed the same way (ui/gameplay_screen).  A screen reader cannot be
asked when it has finished - NVDA's controller client only speaks, cancels, brailles and says whether NVDA is
running, and Prism and VoiceOver's Apple Event only hand a line over - and the game's own voices (SAPI 5, the
Mac's system voice, the phone's text-to-speech), which can, were followed to their real end at first.  That
was given up for one rule for every voice: the player's calibration and settings are what the game follows,
whatever speaks it.

A braille display is read at the reader's own pace, so it is given the item and its hint together, at once,
the way NVDA puts an object's description beside its name; the hint said later is not brailled again, which
would take the item off the display a second after it arrived (`Screen.speak_element`).
"""
from __future__ import annotations

import logging

log = logging.getLogger('ui.reading')

#: How fast the speech is taken to read until it has been measured: an ordinary speaking pace (the pace of an
#: audiobook, and about what a screen reader's default rate reads English at).  A player who listens faster
#: waits a little longer than they need, which is the side to err on.  The Extra mode's story and the hints
#: are both timed by it until the player has measured the speech (Speech calibration, ui/settings.py), and
#: the game asks for that as it starts.  Pause before hints is added as it is, 0 included: a least pause of a
#: fifth of a second, kept for a while on 2026-10-02 while nothing was measured and on the phone, was taken
#: out at the user's request - the game follows the player's setting, not an assumption of its own.
DEFAULT_WORDS_PER_MINUTE = 180.0
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
    """The time the speech is taken to need for one word, whatever speaks the game: as measured for the
    speech, or at the default pace."""
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
    """How long the speech is taken to need to read this."""
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
    __slots__ = ('hint', 'said', 'line', 'at')

    def __init__(self, hint: str, said: str, line: int, at: float):
        self.hint = hint                                  # what is read when it is due
        self.said = said                                  # the line read before it, which it waits for
        self.line = line                                  # Speech.lines as that line was handed over
        self.at = at                                      # and when


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
        """Seconds until the waiting hint is read - 0 when it is due - or None when nothing waits: the time
        the line before it is taken to need (`reading_seconds`), and then the pause, for every voice."""
        from ..game.parameters import GameParameters
        w = self.waiting
        if w is None:
            return None
        return max(0.0, w.at + reading_seconds(w.said) + GameParameters.shared().hint_pause() - now)

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
        # queued, not interrupting: speech slower than it is timed at finishes the line first.  Not brailled:
        # the display has had it since the line was (Screen.speak_element).
        speech.speak(w.hint, interrupt=False, braille='')
