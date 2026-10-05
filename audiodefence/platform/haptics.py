"""PORT ADDITION: what a game controller makes you feel - and, on Android, the phone itself.

The phone game has no vibration at all - the original never calls AudioServicesPlaySystemSound with the
vibrate sound - so everything here is the port's own, for players with a controller in their hands, and
since 2026-10-05 for a phone in them (user request; `_phone`, below):

* the **heartbeat** that plays when a zombie is close (``ADPlayer``'s proximity heartbeat, player.py) is
  felt on each beat, harder the closer the zombie is, as the sound is louder;
* a **hit** on a zombie is felt as hard as the damage it did - a Micro SMG round a tap, a Sawn-off blast or
  a Bazooka a jolt - gunfire sharp, a melee blow a heavy thud; a shield that stops a shot is a small knock;
* a zombie **killed**, by anything, is a thump of its own;
* a **diamond** shot down is two bright ticks, a power-up **container** shot open a crack, and the power-up
  **taking effect** after its announcement a swell into the thing itself;
* an **explosion** - a grenade, a rocket, the fireworks, a Farty or a car going up - is a rumble, heavier
  the closer it is;
* a gust of the **tornado** pushing the zombies back is a soft push;
* the **Minigun** is felt the whole time it fires, under the hits it lands rather than in place of them,
  and the **Tesla** coil's zap is a crack of its own on top of the kill it makes;
* **dying** - a zombie reaching you - is a long, heavy shudder;
* and the **menus** are felt: a click as the cursor moves from one element or tab to the next, a firmer
  one when something is activated - a setting stepped or toggled, a button pressed - and a pair of knocks
  going into a screen, the other way round coming back out of it.

What happens in one pass of the game loop is felt as one pulse: a shotgun blast into three zombies is one
jolt, firmer for the extra two, not three buzzes over each other.  Settings -> Miscellaneous -> Joystick vibration scales
it all (light, medium, strong) or turns it off.

Every pad that can rumble does, through SDL.  A DualSense on USB is played its fine haptics instead
(haptic_audio.py): the heartbeat recording the game has just played, felt as it is heard, and a waveform of
its own for each of the rest.  Nothing here waits: a pulse is sent and the pad times it.

On Android the same pulse is felt in the phone as well, at Settings -> Miscellaneous -> Phone vibration's
strength (`_phone`).  This is the module the phone uses too: haptic_audio.py is not in the app, and is only
reached for a DualSense, which the phone does not see.
"""
from __future__ import annotations

import logging

from . import host

log = logging.getLogger('platform.haptics')

#: Settings -> Miscellaneous -> Joystick vibration: how much of each pulse is felt.  Strong is everything
#: the pad has - a waveform is played at its full height and a motor at full - so more than this has to come
#: from the pulses themselves (haptic_audio.fat, RUMBLE_AS_WELL), not from here.  The three are set well
#: apart (user request): at 0.6 / 0.85 / 1 the top two felt alike, a waveform being felt by its height the
#: way a sound is heard by it - 0.85 of full is barely a decibel and a half down - where a third, two
#: thirds and full are three different things.  All three were then lifted a little (user request), the
#: pulses themselves having as much in them as they can hold.
LEVEL_SCALE = {'off': 0.0, 'light': 0.4, 'medium': 0.7, 'strong': 1.0}

#: what a DualSense feels through its motors as well as its fine haptics: the big, low things, where the
#: motors have the weight the little actuators cannot give.  The rest is the fine haptics alone, which are
#: finer than a motor and do not drown the game's sound.
RUMBLE_AS_WELL = frozenset({'explosion', 'death', 'kill', 'powerup_use'})

#: kind -> (low-frequency motor, high-frequency motor, milliseconds) at strength s: the heavy motor is the
#: thump, the light one the buzz, so a melee blow is mostly thump and a bullet's hit mostly buzz
SHAPES = {
    'heartbeat': lambda s: (s, 0.1 * s, 70),
    'hit': lambda s: (0.85 * s, s, int(70 + 80 * s)),
    'melee': lambda s: (s, 0.4 * s, int(90 + 90 * s)),
    'blocked': lambda s: (0.15 * s, 0.5 * s, 40),
    'kill': lambda s: (0.95 * s, 0.65 * s, 180),
    'explosion': lambda s: (s, 0.6 * s, int(250 + 350 * s)),
    'gust': lambda s: (0.4 * s, 0.2 * s, 350),
    'death': lambda s: (s, 0.9 * s, 1000),
    # the menus: a click firm enough to be felt through a thumb on the stick, but short, since the cursor
    # can move as fast as the key repeats.  Going into a screen and coming back out are longer and heavier.
    'minigun': lambda s: (0.4 * s, 0.75 * s, 160),        # the gun itself, kept up while it fires
    'zap': lambda s: (0.4 * s, s, 120),                   # the Tesla coil taking one: bright and sharp
    'menu': lambda s: (0.7 * s, s, 60),
    'toggle': lambda s: (0.8 * s, s, 90),
    'enter': lambda s: (0.7 * s, 0.9 * s, 120),
    'back': lambda s: (0.9 * s, 0.45 * s, 120),
    'diamond': lambda s: (0.1 * s, s, 90),                # bright and quick, where a kill is a low thump
    'powerup': lambda s: (0.8 * s, 0.9 * s, 220),         # the crate cracking open
    'powerup_use': lambda s: (s, 0.7 * s, 600),           # and the power-up taking hold: a long swell,
                                                          # as long as its start sound where it has one
}

#: PORT ADDITION (Android): the menus' pulses as the phone's own clicks (Bridge.vibrate): 1 a tick, 2 a
#: click, 3 a click and then a lighter one going into a screen, 4 the other way round coming out.  Anything
#: else - everything in a game - is 0, a pulse of the shape's strength and length.
PHONE_STYLES = {'menu': 1, 'toggle': 2, 'enter': 3, 'back': 4}

#: the damage a hit does, as how hard it is felt: every hit that lands is well felt - a Micro SMG round
#: (5 damage) is 0.68, a Revolver's (10) 0.71 - and damage adds the rest, up to the full jolt at 80, a
#: Bazooka's or a Claymore's at their best.  The floor was 0.5, which left a small gun's hit faint.
FULL_DAMAGE = 80.0
HIT_FLOOR = 0.6


def damage_strength(damage: float) -> float:
    return min(1.0, HIT_FLOOR + (1.0 - HIT_FLOOR) * (max(0.0, damage) / FULL_DAMAGE) ** 0.6)


class Haptics:
    _shared: 'Haptics | None' = None

    @classmethod
    def shared(cls) -> 'Haptics':
        if cls._shared is None:
            cls._shared = Haptics()
        return cls._shared

    def __init__(self):
        self.sent: list = []                              # the last pulses, for tests: (low, high, ms)
        self.phone_sent: list = []                        # the phone's, for tests: (strength, ms, style)
        self.played: list = []                            # the last haptics played, for tests: (what, gain)
        self.pending: dict = {}                           # kind -> [strongest, how many] this pass
        self.flush_due = False

    # --- what the game calls -------------------------------------------------------------------------
    def heartbeat(self, closeness: float, recording: str | None = None) -> None:
        """One beat, felt at once.  `closeness` is ADPlayer's, 0 at the edge of hearing to 1 at arm's
        length; the beat's strength follows the sound's own gain curve (closeness squared * 0.7 + 0.3).
        `recording` is the heartbeat file the game has just played, which a DualSense plays as it is."""
        strength = max(0.0, min(1.0, closeness)) ** 2 * 0.7 + 0.3
        self._send({'heartbeat': [strength, 1]}, recording)

    def hit(self, damage: float, melee: bool = False) -> None:
        """A zombie hit for `damage`, by a melee weapon or by anything else: a bullet, a blast, a
        power-up."""
        self._add('melee' if melee else 'hit', damage_strength(damage))

    def blocked(self) -> None:
        """A shot a zombie's shield stopped."""
        self._add('blocked', 0.5)

    def kill(self) -> None:
        self._add('kill', 0.8)

    #: how often the Minigun's own feel is asked for while it fires.  Short enough that the pulses run into
    #: one another, long enough that the grips are not given the same waveform sixty times a second.
    SUSTAIN = 0.12

    def minigun_firing(self) -> None:
        """The Minigun while it fires, asked for every SUSTAIN seconds.  It goes through the pass's own
        pulse like everything else, so a hit it lands is felt over it rather than instead of it: the
        motors take the stronger of the two and the grips play both (user request)."""
        self._add('minigun', 0.55)

    def zap(self) -> None:
        """The Tesla coil taking a zombie: a crack over the kill it makes."""
        self._add('zap', 0.95)

    def diamond(self) -> None:
        """A diamond shot down: yours, and felt as its own thing rather than as a kill."""
        self._add('diamond', 0.9)

    def power_up_container(self) -> None:
        """A power-up container shot open, with the announcement to come."""
        self._add('powerup', 0.9)

    def power_up_started(self, seconds: float | None = None) -> None:
        """The power-up taking effect, once its announcement has been read - the Minigun in your hands,
        the Fireworks going up, the Tornado turning, the Tesla coil on.  `seconds` is how long the thing
        that starts it takes - the launch sound, or the Minigun's spin-up - so what is felt and what is
        heard end together (user request); without it, the shape's own 600 ms."""
        self._send({'powerup_use': [1.0, 1]}, seconds=seconds)

    def explosion(self, distance: float) -> None:
        """An explosion `distance` from the player: full within a metre or so, and never less than half,
        since a blast is a blast even across the arena."""
        self._add('explosion', max(0.5, min(1.0, 1.0 - (distance - 1.0) / 14.0)))

    def gust(self) -> None:
        self._add('gust', 0.6)

    def player_killed(self) -> None:
        self._add('death', 1.0)

    def menu(self) -> None:
        """The cursor moving through a menu: to the next element, or the next tab.  Sent at once rather
        than gathered into the next pass, a menu being no game loop."""
        self._send({'menu': [0.85, 1]})

    def toggled(self) -> None:
        """Something activated: a setting stepped or toggled, a button pressed.  Firmer than moving the
        cursor, a change being worth more than a step (user request)."""
        self._send({'toggle': [0.9, 1]})

    def screen_entered(self) -> None:
        """A screen opened, or the one you were on replaced."""
        self._send({'enter': [1.0, 1]})

    def screen_left(self) -> None:
        """A screen closed: the same two knocks the other way round, so going back feels like going back."""
        self._send({'back': [0.9, 1]})

    def sample(self) -> None:
        """What Settings plays when the strength is changed: a hit at that strength, at once - a hit being
        what is felt most often, and what the strength is usually being chosen for."""
        self._send({'hit': [0.8, 1]})

    # --- one pulse per pass --------------------------------------------------------------------------
    def _add(self, kind: str, strength: float) -> None:
        entry = self.pending.setdefault(kind, [0.0, 0])
        entry[0] = max(entry[0], strength)
        entry[1] += 1
        if not self.flush_due:
            self.flush_due = True
            from .runloop import RunLoop
            RunLoop.main().call_soon(self._flush)

    def _flush(self) -> None:
        events, self.pending, self.flush_due = self.pending, {}, False
        if events:
            self._send(events)

    def _send(self, events: dict, recording: str | None = None, seconds: float | None = None) -> None:
        """events: kind -> [strongest, count].  Several of a kind are the strongest, and a little more for
        each of the rest; the pulse sent is the strongest of the kinds on each motor, and the longest.

        `seconds` makes this pulse last that long instead of the shape's own time, waveform and all, so
        what is felt runs with the sound it goes with."""
        from ..game.parameters import GameParameters
        from .pad import Pads
        pads = Pads.shared()
        strengths = {kind: min(1.0, s + 0.1 * (n - 1)) for kind, (s, n) in events.items()}
        long_ms = int(seconds * 1000) if seconds else 0
        if host.ANDROID:
            self._phone(strengths, long_ms)
        scale = LEVEL_SCALE.get(GameParameters.shared().vibration_level(), 0.0)
        if not pads.pads or scale <= 0.0:
            return
        fine = set()
        if pads.dualsenses and GameParameters.shared().fine_haptics() and self._fine_available():
            from .haptic_audio import WAVES, HapticAudio
            audio = HapticAudio.shared()
            for kind, s in strengths.items():
                if kind == 'heartbeat' and recording:
                    wave = audio.recording(recording)
                else:
                    wave = WAVES.sized(kind, seconds) if seconds else WAVES.get(kind)
                audio.play(wave, s * scale)
                self.played = (self.played + [(kind, round(s * scale, 3))])[-20:]
            fine = set(pads.dualsenses)
        low, high, ms = self._shape(strengths, scale)
        self._pulse(low, high, long_ms or ms, skip=fine)
        if fine:                                          # and the motors too, for the big ones
            heavy = {kind: s for kind, s in strengths.items() if kind in RUMBLE_AS_WELL}
            if heavy:
                low, high, ms = self._shape(heavy, scale)
                self._pulse(low, high, long_ms or ms, skip=set(pads.pads) - fine)

    @staticmethod
    def phone_kind() -> int:
        """PORT ADDITION (Android): what the phone's motor can do (Bridge.vibrationKind): 0 there is none, 1
        it is on or off only, 2 it has haptics, 3 haptics with clicks of its own.  0 off the phone."""
        if not host.ANDROID:
            return 0
        try:
            from .jbridge import bridge
            return int(bridge().vibrationKind())
        except Exception as exc:
            log.debug('the phone did not say how it vibrates: %s', exc)
            return 0

    @staticmethod
    def _fine_available() -> bool:
        from .haptic_audio import HapticAudio
        return HapticAudio.shared().available()

    def _phone(self, strengths: dict, long_ms: int) -> None:
        """PORT ADDITION (Android, user request, 2026-10-05): the pulse a controller is given, felt in the
        phone, at Settings -> Miscellaneous -> Phone vibration's strength: the stronger of its two motors,
        the phone having one, and its length.  A menu's click alone is the phone's own click or tick
        (PHONE_STYLES).  The phone decides how it can play it (Bridge.vibrate): at that strength where it has
        haptics, as plain vibration, shorter for weaker, where it has not."""
        from ..game.parameters import GameParameters
        scale = LEVEL_SCALE.get(GameParameters.shared().phone_vibration_level(), 0.0)
        if scale <= 0.0:
            return
        low, high, ms = self._shape(strengths, scale)
        style = PHONE_STYLES.get(next(iter(strengths)), 0) if len(strengths) == 1 else 0
        strength = max(0.0, min(1.0, max(low, high)))
        ms = int(long_ms or ms)
        self.phone_sent = (self.phone_sent + [(round(strength, 3), ms, style)])[-20:]
        try:
            from .jbridge import bridge
            bridge().vibrate(float(strength), ms, style)
        except Exception as exc:                          # the phone's vibration must not stop the game
            log.debug('the phone could not vibrate: %s', exc)

    @staticmethod
    def _shape(strengths: dict, scale: float):
        """The one pulse these events come to: the strongest of them on each motor, and the longest."""
        low = high = 0.0
        ms = 0
        for kind, s in strengths.items():
            k_low, k_high, k_ms = SHAPES[kind](s)
            low, high, ms = max(low, k_low * scale), max(high, k_high * scale), max(ms, k_ms)
        return low, high, ms

    def _pulse(self, low: float, high: float, ms: int, skip=frozenset()) -> None:
        from .pad import Pads
        pads = Pads.shared()
        if all(iid in skip for iid in pads.pads):
            return
        self.sent = (self.sent + [(round(low, 3), round(high, 3), ms)])[-20:]
        for iid, pad in list(pads.pads.items()):
            if iid in skip:
                continue
            rumble = getattr(pad, 'rumble', None)
            if rumble is None:
                continue
            try:
                rumble(max(0.0, min(1.0, low)), max(0.0, min(1.0, high)), int(ms))
            except Exception as exc:                      # a pad that went mid-pulse must not stop the game
                log.debug('rumble failed: %s', exc)
