"""ADSound - a scripted narration / effect sound inside a brick (plist "Sounds" entries)."""
from __future__ import annotations

import logging
import math
import re

from ..platform.defaults import ns_bool_value, ns_float_value
from ..s3d.engine import S3DEngine
from .parameters import GameParameters

log = logging.getLogger('adsound')

_POINT = re.compile(r'\{\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\}')


def cg_point_from_string(text) -> tuple:
    """CGPointFromString: "{x, y}" (anything else gives {0, 0})."""
    m = _POINT.search(str(text or ''))
    if not m:
        return 0.0, 0.0
    return float(m.group(1)), float(m.group(2))


class ADSound:
    # -[ADSound initWithDictionary:] 0x1000b2d68
    def __init__(self, d: dict):
        from .brick_manager import BrickManager
        self.squared_distance_from_final_position = float('inf')
        self.name = d.get('name')
        self.spawn_after = d.get('spawn_after')
        self.spawn_time = ns_float_value(d.get('spawn_time'))
        self.speed = ns_float_value(d.get('speed'))
        self.gain = ns_float_value(d.get('gain'))
        self.loop = ns_bool_value(d.get('loop'))
        self.blocker = ns_bool_value(d.get('blocker'))
        self.skippable = ns_bool_value(d.get('skippable'))
        self.stops_other_sounds = ns_bool_value(d.get('stopsOtherSounds'))
        self.start_music_before_end = ns_float_value(d.get('startMusicBeforeEnd'))
        self.speed = 2.0                                     # initWithDictionary: hardcodes this;
        # no scripted sound in any of the game's plists carries a `speed` key, so nothing is lost
        self.position = (0.0, 0.0)
        self.final_position = (0.0, 0.0)
        self.orientation = (0.0, 0.0)
        if d.get('spawn_distance') is not None and d.get('spawn_angle') is not None:
            a = ns_float_value(d.get('spawn_angle')) * 3.14159265 / 180.0
            dist = ns_float_value(d.get('spawn_distance'))
            self.position = (dist * math.sin(a), dist * math.cos(a))
        if d.get('position') is not None:
            self.position = cg_point_from_string(d.get('position'))
            if d.get('finalPosition') is not None:
                self.final_position = cg_point_from_string(d.get('finalPosition'))
                dx = self.final_position[0] - self.position[0]
                dy = self.final_position[1] - self.position[1]
                n = math.sqrt(dx * dx + dy * dy)
                self.orientation = (dx / n, dy / n) if n else (float('nan'), float('nan'))
        self.playlist = S3DEngine.engine().play_list_with_name(BrickManager.shared().current_brick_name())
        self._state = -99
        self.time_in_state = 0.0
        self.started_main_menu_music = False
        self.sound_was_playing = False
        self.sound = None
        # PORT DIVERGENCE: `initWithDictionary:` 0x1000b2d68 is `set_state(1 if spawn_time != 0 else 0)`,
        # and asks the wrong question of a line a player wrote.  State 1 is "its clock is running" and state
        # 0 is "parked until something triggers it" - `checkSpawnOnStart:` 0x1000a19fc and
        # `checkEnemiesSpawnAfterKill:` 0x1000a20ac move a sound out of 0, `update` 0x1000b3914 has no
        # branch for it at all, and `ignoreIfSkipped` parks a sound by putting it back there.  So a sound
        # at 0 seconds with nothing to wait for is parked for ever, and a blocker that never plays holds
        # its wave for ever with it.
        #
        # In the original's own data the two questions are the same question, so this is not a bug there:
        # all 131 scripted sounds in the game's plists were counted, and every one of them either names a
        # `spawn_after` and has no `spawn_time` (30 of them) or has a non-zero `spawn_time` and nothing to
        # wait for (101).  None is in the gap, so this changes the state of none of them.  A player's
        # cutscene *is* in the gap - "at the start" is what a line usually wants, and `game/custom.py`
        # writes `at: 0` for it - so the question asked here is the one that was meant.
        self.set_state(0 if self.spawn_after is not None else 1)
        self.init_sound()

    @property
    def state(self) -> int:
        return self._state

    def set_state(self, state: int) -> None:                 # 0x1000b44f0
        if self._state == state:
            return
        self._state = state
        self.time_in_state = 0.0

    def init_sound(self) -> None:                             # 0x1000b3594
        key = self.name or ''
        params = GameParameters.shared()
        if 'BUTTONMODE' in key:
            key = key.replace('BUTTONMODE', 'buttonMode' if params.button_mode else 'gestureMode')
        if 'CONTROLMODE' in key:
            scheme = params.control_scheme
            if scheme == 1:
                key = key.replace('CONTROLMODE', 'gyroMode')
            if scheme == 2:
                key = key.replace('CONTROLMODE', 'swipeMode')
            if scheme == 3:
                key = key.replace('CONTROLMODE', 'tiltMode')
        self.sound = self.playlist.sound(key) if self.playlist is not None else None

    def update(self, dt: float) -> None:                      # 0x1000b3914
        if self._state == 2:
            dur = self.sound.duration if self.sound is not None else 0.0
            if self.start_music_before_end > 0.0 and not self.started_main_menu_music:
                # The menu music comes in under the end of a challenge's closing line, so it is already
                # running when the score screen arrives: 30 lines carry a lead-in, all but one of 3 s.
                # bastard_tutorial_7_4, the closing line of "Meet The Farty", is 2.65 s long against that
                # same 3 s lead, so the threshold is -0.35 s and the test passes on the line's first tick:
                # the music starts with the line rather than 3 s before it ends.  That is the original's
                # own answer to a line shorter than its lead-in, and it still gives 2.65 s of music before
                # the screen changes - within a third of a second of what every other challenge gets.
                if self.time_in_state > dur - self.start_music_before_end and dur > 0.0:
                    self.started_main_menu_music = True
                    from ..app import App
                    App.delegate().start_menu_music('main_menu_theme')
            if dur != 0.0 or self.name == 'silence':
                if self.time_in_state > dur:
                    self.finish_sound_with_skip(False)
                    self.time_in_state += dt
                    return
            if self.orientation[0] != 0.0 or self.orientation[1] != 0.0:
                px, py = self.position
                self.position = (px + dt * (self.orientation[0] * self.speed),
                                 py + dt * (self.orientation[1] * self.speed))
                if self.sound is not None:
                    self.sound.set_planar((self.position[0], self.position[1], 0.0))
                fx = self.final_position[0] - self.position[0]
                fy = self.final_position[1] - self.position[1]
                d2 = fx * fx + fy * fy
                if d2 < self.squared_distance_from_final_position:
                    self.squared_distance_from_final_position = d2
                else:
                    self.speed = 0.0
        elif self._state == 1:
            if self.time_in_state > self.spawn_time:
                self.play()
        self.time_in_state += dt

    def skip(self) -> None:                                   # 0x1000b404c
        self.finish_sound_with_skip(True)

    def finish_sound_with_skip(self, skipped: bool) -> None:  # 0x1000b4060
        from .brick_manager import BrickManager
        if self.sound is not None:
            self.sound.stop()
        self.set_state(3)
        BrickManager.shared().sound_or_enemy_with_name_was_deactivated(self.name, skipped)

    def play(self) -> None:                                   # 0x1000b416c
        from .brick_manager import BrickManager
        if self.stops_other_sounds:
            BrickManager.shared().stop_all_sounds_in_current_brick()
        if self.position[0] != 0.0 or self.position[1] != 0.0:
            if self.sound is not None:
                self.sound.set_spatialized(True)
                self.sound.set_planar((self.position[0], self.position[1], 0.0))
        if self.sound is not None:
            self.sound.play(self.loop)
            if self.gain > 0.0:
                self.sound.set_gain(self.gain)
        self.set_state(2)
        self.speak_tutorial_text()
        BrickManager.shared().check_spawn_on_start(self.name)

    def speak_tutorial_text(self) -> None:
        """PORT ADDITION: the tutorial announcer tells you to tilt, swipe or tap a corner of a phone.  None
        of that reaches a keyboard, so its lines are also spoken with the keys that are actually bound - see
        game/tutorial_text.py.  Settings -> Miscellaneous -> Tutorial text chooses when, or turns it off."""
        from ..platform.speech import Speech
        from .parameters import GameParameters
        from .tutorial_text import text_for
        mode = GameParameters.shared().tutorial_text_mode()
        if mode == 'off' or self.sound is None:
            return
        text = text_for(getattr(self.sound, 'key', None))
        if text is None:
            return
        if mode == 'after':
            self.sound.add_3d_sound_end_callback(lambda _s, t=text: Speech.shared().speak(t, False))
        else:
            Speech.shared().speak(text, False)

    def stop_with_no_callback(self) -> None:                  # 0x1000b4438
        if self._state in (2, 1):
            self.set_state(3)
            if self.sound is not None:
                self.sound.stop()

    def pause(self) -> None:                                  # 0x1000b45c0
        self.sound_was_playing = bool(self.sound is not None and self.sound.playing)
        if self.sound is not None:
            self.sound.pause()

    def resume(self) -> None:                                 # 0x1000b4674
        if self.sound_was_playing and self.sound is not None:
            self.sound.resume()
