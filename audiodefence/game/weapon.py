"""ADWeapon and ADMeleeWeapon.

Weapon states, named by -[ADWeapon stateToString]: 0 Idle, 1 Switching, 2 Shooting, 3 Continuous,
4 Continuous to tail, 5 Continuous Empty, 6 Reload Down, 7 Reload Empty, 8 Reload Up.

QUIRK kept: -[ADWeapon update:] advances timeInState and lastAnnouncerSpeech by the wall-clock time
between calls (CACurrentMediaTime), not by the timer's dt; only fireRateTimer uses dt.
"""
from __future__ import annotations

import logging
import math
import time

from ..platform import crand
from ..platform.defaults import ns_bool_value, ns_float_value, ns_int_value
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .modifiers import RUSTY_JAM_PERCENT, GameModifiers

log = logging.getLogger('weapon')

STATE_NAMES = ('Idle', 'Switching', 'Shooting', 'Continuous', 'Continuous to tail', 'Continuous Empty',
               'Reload Down', 'Reload Empty', 'Reload Up')   # 0x1000152d4..0x100015334


def ca_current_media_time() -> float:
    return time.perf_counter()


def _get(d, key):
    return d.get(key) if isinstance(d, dict) else None


def _c_div(a: int, b: int) -> int:
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


#: PORT DIVERGENCE: a weapon's sounds start where the sound does (user request).  Some of the game's own
#: recordings open with a moment of nothing - the Machine Gun's shot has 133 milliseconds of it, its tail
#: 133 and its deploy 145, the Grenade Launcher's shot 109, the Tactical Rifle's deploy 104 - and the
#: original plays them from the top, so the press and the sound are that far apart.  Tapping the Machine
#: Gun, which is what it is for, that silence is the gap between the shots; letting go of it after a burst,
#: it is the gap before the gun winds down.  The files are left alone: each sound is started past its own
#: silence instead (S3DSound.skip_to), measured once from what the decoder already holds
#: (decoder.lead_in), and only up to a quarter of a second, in case the quiet is the sound itself.
_LEAD_IN: dict = {}

#: PORT DIVERGENCE (user request): the shots in each continuous-fire loop.  Every "_conti" recording is a
#: whole number of shots, cut in the quiet just before one, so a shot ends at each multiple of the loop's
#: length over this number - and that is where a burst that has been let go of stops
#: (`Weapon.burst_can_end`).  Measured from the files: the Tactical Rifle's 1.601 s holds 8 shots (0.200 s
#: each), the Machine Gun's 2.409 s 36 (0.067 s) and the Micro SMG's 1.160 s 25 (0.046 s).  A loop not
#: listed is taken to hold a shot every `fireRate`.
_SHOTS_IN_LOOP = {'weapon_gun_tactical_conti': 8, 'weapon_gun_machinegun_conti': 36,
                  'weapon_gun_microsmg_conti': 25}

#: How far a playing sound's position moves at a time: OpenAL Soft mixes in 10 ms updates, and
#: AL_SEC_OFFSET steps by exactly that (measured), so two looks at it 10 ms apart can find it 0, 10 or 20 ms
#: further on (`Weapon.burst_can_end`).
_MIX_STEP = 0.01


def _at_the_sound(sound):
    """Have this sound start where the recording does, not where the file does; returns it, to wrap the
    place it is taken from the playlist."""
    if sound is None or not sound.path:
        return sound
    lead = _LEAD_IN.get(sound.path)
    if lead is None:
        from ..s3d import decoder
        if not decoder.is_cached(sound.path):             # not decoded yet: ask again next time, rather
            return sound                                  # than remember that it has no silence in it
        lead = _LEAD_IN[sound.path] = decoder.lead_in(sound.path)
    sound.skip_to = lead
    return sound


class Weapon:
    # -[ADWeapon initWithDictionary:] 0x100013f94
    def __init__(self, d: dict | None):
        from .inventory import Inventory
        self.time_in_continous = 0.0
        self.time_since_last_shot = 0.0
        self.shot_once = False
        self.fire_rate_timer = 0.0
        self.continuous_sound = None
        self.continuous_warning = None
        self.empty_loop = None                            # PORT ADDITION: the warning an empty gun makes
        self.reload_sound = None                          # PORT ADDITION: the one reload actually started
        self.burst_left = None                            # PORT ADDITION: see let_the_shot_finish
        self.burst_at = 0.0
        self.tick_seconds = 0.01                          # PORT ADDITION: how long the last update: was ago
        self.last_announcer_speech = 0.0
        self.previous_tick_time = 0.0
        self.dropped_magasine = False
        self.switching_time = 0.0
        self._state = 0
        self.time_in_state = 0.0
        self.playlist = None
        self.weapon_manager = None
        self.num_shots_fired = 0

        self.name = _get(d, 'name')
        self.range = ns_float_value(_get(d, 'range'))
        self.multihit = ns_bool_value(_get(d, 'multihit'))
        self.continuous_fire = ns_bool_value(_get(d, 'continuousFire'))
        self.explosive = ns_bool_value(_get(d, 'explosive'))
        level = _get(d, f'level_{Inventory.shared().level_for_weapon(self.name)}')
        self.fire_rate = ns_float_value(_get(level, 'fireRate'))
        self.damages = ns_float_value(_get(level, 'damages'))
        self._spread = ns_float_value(_get(level, 'spread'))
        self.critical_spread = ns_float_value(_get(level, 'criticalSpread'))
        self.critical_chance = ns_float_value(_get(level, 'criticalChance'))
        self.critical_multiplier = ns_float_value(_get(level, 'criticalMultiplier'))
        self.continuous_spread = ns_float_value(_get(level, 'continuous_spread'))
        if _get(level, 'dispersal') is not None:
            self.dispersal = ns_float_value(_get(level, 'dispersal'))
        else:
            self.dispersal = 100.0
        self.explosion_radius = ns_float_value(_get(level, 'explosionRadius'))
        self.projectile_speed = ns_float_value(_get(level, 'projectileSpeed'))
        self.reload_time = ns_float_value(_get(level, 'reloadTime'))
        self.time_before_explode = ns_float_value(_get(level, 'timeBeforeExplode'))
        self.capacity = ns_int_value(_get(level, 'capacity'))
        self.switching_time = 1.0
        self.bullets_in_clip = self.capacity
        self.bullets_total = 0x7fffffff
        self.time_since_last_shot = 0.0
        self.fire_sound_prefix = f'weapon_gun_{self.name}_fire'
        self.click_sound_prefix = f'weapon_gun_{self.name}_empty'
        self.playlist = S3DEngine.engine().play_list_with_name(self.name) if self.name is not None else None
        if self.playlist is not None:
            self.playlist.activate()
        self.prepare_burst_sounds()                       # PORT ADDITION: see prepare_burst_sounds
        self.set_state(0)
        mods = GameModifiers.shared()
        # PORT DIVERGENCE: once for each card that asked, where the original asks only whether one did.
        # The tenth is taken off what is left each time, as the original takes it off the whole.
        # PORT DIVERGENCE (user request): both, once for each card that asked.  The original is an
        # `if/elif`, so Golden Bullet silenced a card that took bullets away - and with four decks that is
        # a real hand: Golden Bullet in the level-3 deck and Hair Trigger in the level-4 one.  Each card
        # takes its tenth of what is there, up or down, and two opposite cards cancel out.
        for _ in range(mods.times('goldenBullet')):
            bonus = max(_c_div(self.capacity, 10), 1)
            self.capacity = self.capacity + bonus
            self.bullets_in_clip = self.capacity
        for _ in range(mods.times('lessBullets')):
            malus = max(_c_div(self.capacity, 10), 1)
            self.capacity = self.capacity - malus
            if self.capacity == 0:
                self.capacity = 1
            self.bullets_in_clip = self.capacity
        if mods.brokenGuns and not isinstance(self, MeleeWeapon):
            # PORT ADDITION (user request, 2026-10-05): Empty Chambers - every gun arrives empty, with no
            # rounds to reload from, so it only clicks; the melee weapon is untouched
            self.bullets_in_clip = 0
            self.bullets_total = 0
        if mods.spread_modifier() != 0.0:
            self.continuous_spread = mods.spread_modifier() + self.continuous_spread
            self._spread = mods.spread_modifier() + self._spread
        self.last_announcer_speech = 5.0                  # 0x40a00000
        self.critical_chance = mods.head_shot_modifier() * self.critical_chance
        self.previous_tick_time = ca_current_media_time()

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.name} state={self._state}>'

    # --- properties ------------------------------------------------------------------------------
    @property
    def state(self) -> int:
        return self._state

    @property
    def spread(self) -> float:                            # 0x100016180
        return self.continuous_spread if self._state == 3 else self._spread

    @spread.setter
    def spread(self, value: float) -> None:               # setSpread: 0x100016bdc
        self._spread = float(value)

    def set_state(self, state: int) -> None:              # 0x100015210
        if self._state == state:
            return
        if self._state == 4 and self.continuous_sound is not None:
            self.continuous_sound.stop()                  # DIVERGENCE: the loop finishing its shot goes with
        self._state = state                               # state 4, whatever ends it (see burst_can_end)
        self.time_in_state = 0.0

    def state_to_string(self) -> str:                     # 0x100015240
        if 0 <= self._state <= 8:
            return STATE_NAMES[self._state]
        return f'Default : {self._state}'

    def change_state(self, state: int) -> bool:           # 0x100015148
        if self._state == state:
            return False
        old = self._state
        if state == 2:
            if self.ready_to_shoot():
                self.set_state(2)
        else:
            self.set_state(state)
        return (1 if old != 0 else 0) != self._state      # QUIRK: compares a bool with the new state

    def ready_to_shoot(self) -> bool:                     # 0x10001537c
        st = self._state
        if st in (6, 8, 1, 2):
            return False
        return st != 3

    def is_reloading(self) -> bool:                       # 0x10001667c
        st = self._state
        return st == 8 or st == 7 or st == 6

    # --- update ----------------------------------------------------------------------------------
    def update(self, dt: float) -> None:                  # 0x100014c8c
        now = ca_current_media_time()
        previous = self.previous_tick_time
        self.previous_tick_time = ca_current_media_time()
        self.tick_seconds = min(max(now - previous, 0.01), 0.05)   # PORT ADDITION: see burst_can_end
        self.update_low_ammo_warning()                    # PORT ADDITION: it lives with the clip now
        st = self._state
        if st == 0:
            if self.continuous_sound is not None and self.continuous_sound.playing:
                self.continuous_sound.stop()
            self.stop_empty_loop()                        # PORT ADDITION: nothing is left sounding at rest
        elif st == 1:
            if self.time_in_state > self.switching_time:
                self.set_state(0)
        elif st == 2:
            if self.time_in_state > self.fire_rate:
                self.set_state(0)
        elif st == 3:
            if self.fire_rate_timer > self.fire_rate:
                self.fire_rate_timer = 0.0
                if not self.resolve_shoot():
                    # DIVERGENCE: 0x100014c8c plays the click first and stops the gun after it, so the
                    # "Reload" call-out starts underneath the gun still firing and its first word is lost.
                    # The gun stops first here.  And the call-out is not held back for the shot that runs
                    # the clip out (`announce=True`): the five-second gate is right for the clicks that
                    # follow, and wrong for the one moment the player needs to be told (user request).
                    if self.continuous_sound is not None:
                        self.continuous_sound.stop()
                    self.stop_low_ammo_warning()
                    self.play_click_sound(announce=True)
                    self.set_state(5)
            self.fire_rate_timer = self.fire_rate_timer + dt
            self.time_in_continous = self.time_in_state
        elif st == 4:
            if self.burst_can_end(self.tick_seconds):     # DIVERGENCE: see let_the_shot_finish
                self.end_burst()
        elif st == 5:
            if self.start_empty_loop():                   # PORT ADDITION: held, it warns until it is let go
                pass
            elif self.time_in_state > self.fire_rate:
                self.time_in_state = 0.0
                self.play_click_sound()
        elif st == 6:
            if self.time_in_state > 0.1:
                self.set_state(7)
                self.bullets_in_clip = 0
        elif st == 8:
            # PORT DIVERGENCE: the reload takes as long as the modifiers say (Quick Hands, Heavy Hands).
            # `reloadTimeModifier` 0x1000de77c is the original's own - 1.2 with fasterReloadTime, 0.8 with
            # slowerReloadTime - and the original only ever writes the number to its log; no card sets
            # either flag and no reload reads it.  It is a speed, so the time is divided by it: 1.2 makes
            # a 2 s reload take 1.67 s, 0.8 makes it take 2.5 s.  Which way round was never shipped, so
            # this is the port's reading of a number the original chose.
            if self.time_in_state > self.reload_time / GameModifiers.shared().reload_time_modifier():
                self.set_state(0)
                self.reload_sound = None                  # PORT ADDITION: it has played itself out
                if self.bullets_total >= self.capacity:
                    self.bullets_in_clip = self.capacity
                else:
                    self.bullets_in_clip = self.bullets_total
                if self.weapon_manager is not None:
                    self.weapon_manager.weapon_did_finish_reloading()
        elapsed = now - previous
        self.last_announcer_speech = elapsed + self.last_announcer_speech
        self.time_in_state = elapsed + self.time_in_state

    # --- firing ----------------------------------------------------------------------------------
    def single_shot(self) -> None:                        # 0x10001540c
        if not self.ready_to_shoot():
            return
        if self.resolve_shoot():
            self.play_single_shoot_sound()
            self.change_state(2)
        else:
            self.play_click_sound()

    def continuous_start(self) -> None:                   # 0x1000154a4
        if not self.continuous_fire:
            self.single_shot()
            return
        if not self.ready_to_shoot():
            return
        if not self.resolve_shoot():
            self.change_state(5)
            return
        self.change_state(3)
        pl = self.playlist
        self.continuous_sound = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_conti')) \
            if pl else None
        if self.continuous_sound is not None:
            self.continuous_sound.set_spatialized(False)
            self.continuous_sound.set_gain(0.6)
            self.continuous_sound.play(True)
        self.update_low_ammo_warning()                    # due from this shot, if the clip is low enough

    def continuous_stop(self) -> None:                    # 0x1000157f8
        self.stop_empty_loop()                            # PORT ADDITION: let go, and the warning stops
        if self._state == 3:
            # DIVERGENCE (user request): the loop is not stopped here but left to finish its shot
            self.let_the_shot_finish()
            self.change_state(4)
            if self.burst_can_end(self.tick_seconds):     # let go at the very end of a shot
                self.end_burst()
            return
        if self._state == 4:                              # let go again while the shot finishes (a
            return                                        # touch both ended and cancelled): it finishes
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        if self._state == 5:
            self.change_state(0)

    def let_the_shot_finish(self) -> None:
        """DIVERGENCE (user request): a burst that is let go of ends at the end of a shot, and the gun winds
        down from there, with nothing in between.

        `continuousStop` 0x1000157f8 stops the "_conti" loop the moment the trigger is let go, wherever it
        is, and state 4 of `update:` 0x100014c8c plays the "_tail" once 0.2 s have gone by since the burst
        began.  A hold only turns into continuous fire after 0.2 s, so a short one gave the loop a few
        hundredths of a second: the shot in it was cut off, there was silence until the 0.2 s were up, and
        then the gun wound down - heard as a burst chopped short (user report, the Tactical Rifle, with a log
        of 60-80 ms of loop and 120-140 ms of silence).  Held for longer, the 0.2 s had gone by already and
        the tail came at once, but over a loop still stopped in the middle of a shot.

        Here the loop plays on to the end of the shot it is in, and to the end of the shot nearest 0.2 s if
        the burst is younger than that - so the original's shortest burst is kept, filled with the gun
        rather than with silence - and `burst_can_end` stops it there and plays the tail at once.  The shots
        come from the recording, not from `fireRate`: each loop is a whole number of them
        (`_SHOTS_IN_LOOP`), and their spacing is not the gun's - the Tactical Rifle fires every 0.25 s over a
        recording with a shot every 0.2.  No bullet is fired while the shot finishes: state 4 has never
        fired one.  Anything that takes the gun out of state 4 first stops the loop with it (`set_state`)."""
        loop = self.continuous_sound
        self.burst_left = None
        if loop is None or not loop.playing or loop.duration <= 0.0:
            return                                        # nothing sounding: the original's 0.2 s, as it was
        length, shot = loop.duration, self.shot_length(loop)
        at = self.burst_at = loop.elapsed_time()
        soonest = at
        if self.time_in_state < length * 0.5:             # the loop has not come round yet, so `at` is
            soonest = max(at, loop.skip_to + 0.2 - shot * 0.5)   # how long it has played: 0.2 s, to a shot
        self.burst_left = math.ceil(soonest / shot - 1e-6) * shot - at

    def shot_length(self, loop) -> float:
        shots = _SHOTS_IN_LOOP.get(loop.key)
        if shots:
            return loop.duration / shots
        return self.fire_rate if self.fire_rate > 0.0 else loop.duration

    def burst_can_end(self, tick: float) -> bool:
        """State 4: whether the loop has reached the end of its shot, or will have before the next look -
        `tick` is how long until then, and half a mixing step is allowed for the position moving in steps.
        So it stops in the last 15 ms or so of the shot, where it is quietest, and never after: a few
        milliseconds of the next shot would be heard as a click.  A look that comes too late, after the
        next shot has begun, lets that one finish too."""
        loop = self.continuous_sound
        if self.burst_left is None:
            return self.time_in_state + self.time_in_continous > 0.2   # the original's test, 0x100014c8c
        if loop is None or not loop.playing:
            return True
        at = loop.elapsed_time()
        self.burst_left -= (at - self.burst_at) % loop.duration
        self.burst_at = at
        while self.burst_left < -0.002:                   # looked at too late, and the next shot has begun:
            self.burst_left += self.shot_length(loop)     # that one is finished too
        return self.burst_left < tick + _MIX_STEP * 0.5

    def end_burst(self) -> None:
        """The loop stops and the gun winds down at once - state 4's end in `update:` 0x100014c8c."""
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        self.burst_left = None
        self.change_state(0)
        self.play_continuous_tail()

    def prepare_burst_sounds(self) -> None:
        """DIVERGENCE (user request): the loop and the tail are loaded when the gun is made or deployed.

        A weapon's sounds are not marked `preload` in its playlist, so each is loaded the first time it is
        played: the first burst's tail was loaded on the spot, a beat late, and if the background decoder
        had not reached the file yet its opening silence was not known either (`_at_the_sound`), so the
        Machine Gun's tail could come 133 ms later still.  The files are decoded on the background thread,
        ahead of the rest (`decoder.decode_async`), and loaded and measured on the main one when ready."""
        if not self.continuous_fire or self.playlist is None:
            return
        from ..s3d import decoder
        engine, playlist = S3DEngine.engine(), self.playlist
        prefixes = (f'weapon_gun_{self.name}_conti', f'weapon_gun_{self.name}_tail')
        for sound in playlist.sounds_matching(lambda key: key.startswith(prefixes)):
            if sound.loaded:
                continue

            def ready(sound=sound):
                if playlist.active and not sound.loaded:  # not if the gun was put away for good meanwhile
                    sound.activate()
                _at_the_sound(sound)
            decoder.decode_async(sound.path, lambda ready=ready: engine.dispatch(ready))

    def stop_firing_now(self) -> None:
        """PORT ADDITION: stop this weapon where it stands - the loop, the warning loop, the state.

        `continuous_stop` hands state 3 over to state 4, which lets the loop finish its shot and then plays
        the tail, from `update:`.  That is right while the weapon is in hand, and wrong the moment it is
        not: only the current weapon is updated (`ADWeaponManager update:`), so a gun switched away from
        mid-burst was left in state 3 with its "_conti" loop playing and nobody to stop it - and since the
        gun the player then held had never been started, it never ran dry, so no reload was called out
        either.
        The same holds when the player dies with the trigger down.
        """
        self.stop_empty_loop()
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        self.stop_low_ammo_warning()
        if self._state in (3, 4, 5):
            self.play_continuous_tail()                   # the gun spins down, as it would have
        self.set_state(0)
        self.fire_rate_timer = 0.0
        self.time_in_continous = 0.0

    def play_continuous_tail(self) -> None:               # 0x1000158b0
        tail = _at_the_sound(
            self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_tail')) if self.playlist else None
        if tail is None:
            return
        # DIVERGENCE: a weapon has one sound per file, so playing the tail again while the last one is still
        # sounding restarts it (S3DSound.play: active -> stop, then _restart_play).  The Machine Gun's tail
        # runs 1.8 seconds and a burst can be a tenth of that, so tapping the trigger cut the wind-down off
        # and started it again, over and over.  The second one gets a voice of its own instead, the way an
        # overlapping shot does (S3DEngine.play_copy_of, -[ADWeapon playSingleShootSound]).
        if tail.playing and S3DEngine.engine().play_copy_of(tail):
            return
        tail.set_spatialized(False)
        tail.set_gain(0.6)
        tail.play(False)

    def running_low(self) -> bool:
        """Whether the clip is down to its last fifth, which is what the warning loop answers to
        (`-[ADWeapon resolveShoot]` 0x100015a1c)."""
        return float(self.bullets_in_clip) <= float(self.capacity) * 0.2

    def update_low_ammo_warning(self) -> None:
        """DIVERGENCE: the low-ammo loop sounds for as long as the clip is low (user request).

        `continuousStart` 0x1000154a4 starts it with the burst and `continuousStop` 0x1000157f8 stops it
        with the burst, so it is only ever heard *underneath* the gun - and over a burst it is 12 dB
        quieter than the gun's own "_conti" loop, which is playing at the same instant.  Held down that
        still works, because the beeps keep coming and the ear picks the rhythm out; fired in taps it is
        one beep under one shot, and it is not heard at all.

        It keeps the original's timing and not its level: it sounds while the gun is firing and stops with
        it (user request), which is the original's own `continuousStart`/`continuousStop` pairing, but it
        is heard, where in the original it was 12 dB under the gun's loop and was not.  It beeped between
        bursts here for a day and that was wrong - a warning that never stops is a warning nobody hears.
        """
        wanted = (self.continuous_fire and self.playlist is not None
                  and self._state == 3                  # firing, and not switching or reloading
                  and self.bullets_in_clip > 0 and self.running_low())
        if not wanted:
            self.stop_low_ammo_warning()
            return
        if self.continuous_warning is not None:
            return
        self.continuous_warning = _at_the_sound(
            self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_warningloop'))
        if self.continuous_warning is None:
            return
        self.continuous_warning.set_spatialized(False)
        self.continuous_warning.set_gain(0.6)
        self.continuous_warning.play(True)

    def stop_low_ammo_warning(self) -> None:
        """Let the loop go and forget it; `update_low_ammo_warning` starts a new one when one is due."""
        if self.continuous_warning is not None:
            self.continuous_warning.stop()
            self.continuous_warning = None

    def resolve_shoot(self) -> bool:                      # 0x100015a1c
        if self.bullets_in_clip < 1 or self.bullets_total < 1:
            return False
        self.num_shots_fired = self.num_shots_fired + 1
        self.bullets_in_clip = self.bullets_in_clip - 1
        self.bullets_total = self.bullets_total - 1
        if GameModifiers.shared().rustyWeapons:
            # PORT DIVERGENCE: 1 in the original; see modifiers.RUSTY_JAM_PERCENT.  Only the clip goes -
            # bulletsTotal is untouched, so a jam costs the reload and no ammunition.
            if crand.c_mod(crand.rand(), 100) < RUSTY_JAM_PERCENT:
                self.bullets_in_clip = 0
        if self.continuous_sound is not None:
            self.continuous_sound.set_gain(0.6)
        if self.weapon_manager is not None:
            self.weapon_manager.shot()
        return True

    def play_single_shoot_sound(self) -> None:            # 0x100015c80
        """Picks random "_fire_" sounds until one is not playing (busy loop in the original);
        below 20% of the clip a random "_warning" sound is layered on top.

        DIVERGENCE: the original waits on the main thread (100015d38..100015dc4) for as long as every
        "_fire_" sound of the weapon is still playing - `-[S3DSound playing]` stays YES until the file has
        played to its end (csl::Abst_SoundFile::vfunc_7 0x1000e4be4: current frame < stop frame).  The fire
        sounds last 1 to 1.7 s while the Tactical Rifle fires every 0.25 s and the Micro SMG every 0.2 s,
        so quick shots froze the whole game for up to a second after the hit sounds (played by
        resolveShoot) had started.  When every fire sound is still playing the port gives the shot a source
        of its own (S3DEngine.play_copy_of), so the shots overlap; only if that fails does it fall back to
        restarting the sound closest to its end, which is heard as a cut."""
        pl = self.playlist
        fire = None
        warning = None
        while fire is None or fire.playing:
            if fire is not None:
                candidates = pl.sounds_matching(lambda k: '_fire_' in k)
                if all(c.playing for c in candidates):
                    fire = _at_the_sound(min(candidates, key=lambda c: c.duration - c.elapsed_time()))
                    if S3DEngine.engine().play_copy_of(fire):     # let this shot overlap the last one
                        if warning is not None:
                            warning.set_spatialized(False)
                            warning.set_gain(0.6)
                            warning.play(False)
                        return
                    break
            fire = _at_the_sound(pl.any_sound_containing('_fire_')) if pl is not None else None
            if fire is None:
                # DIVERGENCE: the original spins forever here when no "_fire_" sound exists.
                log.warning('%s has no _fire_ sound', self.name)
                return
            if float(self.bullets_in_clip) > float(self.capacity) * 0.2:
                continue
            warning = _at_the_sound(pl.any_sound_with_suffix('_warning'))
        fire.set_spatialized(False)
        fire.set_gain(0.6)
        fire.play(False)
        if warning is not None:
            warning.set_spatialized(False)
            warning.set_gain(0.6)
            warning.play(False)

    def empty_click(self):
        """The weapon's own "_empty" recording, or None: not every gun has one."""
        if self.playlist is None:
            return None
        return _at_the_sound(self.playlist.any_sound_with_prefix(self.click_sound_prefix))

    def empty_warning(self):
        """PORT ADDITION: what a gun with no "_empty" recording answers with instead (user request).

        The Machine Gun, the Claymore and the melee weapons have no empty click in `game/sounds/_weapons`,
        so pulling an empty trigger made no sound at all.  Each of them has a short warning of its own, and
        that is what answers now - once for a press, and looping while the trigger is held.  It loops with a
        rhythm already in it: the Machine Gun's is 0.57 s holding 0.36 s of alert, so it beeps and rests.

        Nothing is taken from anywhere else.  This recording is never played by the game as it stands, since
        `anySoundWihSuffix:@"_warning"` 0x100015dec asks for a name ending in "_warning" and the file is
        "_warning_b", so it does not match in the original either.  The *looping* warning is left alone on
        purpose: it is the low-ammo loop under continuous fire, and if an empty gun used it too, running low
        and running out would be the same sound.  A gun that has its own click is untouched.
        """
        if self.playlist is None:
            return None
        return _at_the_sound(self.playlist.any_sound_matching(
            lambda k: '_warning' in k and 'warningloop' not in k))

    def start_empty_loop(self) -> bool:
        """PORT ADDITION: hold an empty trigger and the warning keeps sounding until it is let go.  True
        when that is the answer for this gun, so the caller does not click as well."""
        if self.empty_click() is not None:
            return False
        if self.empty_loop is not None:                   # already warning: asking `playing` here would
            return True                                   # restart it, since play: on a live sound does
        source = self.empty_warning()
        if source is None:
            return False
        # a voice of its own (S3DSound.copy): the press plays this same recording, and playing a sound that
        # is already sounding restarts it - the two would cut each other, and a restart pending at the
        # moment the trigger is let go would start the warning again after it had been stopped
        loop = source.copy()
        loop.set_spatialized(False)
        loop.set_gain(0.6)
        loop.play(True)
        self.empty_loop = loop
        self.announce_reload()                            # said once, when the warning starts
        return True

    def stop_empty_loop(self) -> None:
        if self.empty_loop is not None:
            self.empty_loop.stop()
            self.empty_loop = None

    def announce_reload(self, announce: bool = False) -> None:
        """The announcer's "Reload", or "Out of ammo" with nothing left to reload with.  `announce`
        (PORT ADDITION) says it whatever the five-second gate says: the shot that ran the clip out is the
        moment it is for."""
        from .parameters import GameParameters
        if not GameParameters.shared().last_announcer_value():
            return
        if self.last_announcer_speech <= 5.0 and not announce:
            return
        self.last_announcer_speech = 0.0
        announcer = S3DEngine.engine().play_list_with_name('announcer')
        if self.bullets_total >= 1:
            snd = announcer.any_sound_containing('reload') if announcer else None
        else:
            snd = announcer.any_sound_containing('outofammo') if announcer else None
        if snd is not None:
            snd.play()

    def play_click_sound(self, announce: bool = False) -> None:   # 0x100015f0c
        """The empty click and the call-out: what a press on an empty trigger answers with."""
        click = self.empty_click() or self.empty_warning()
        if click is not None:
            click.set_spatialized(False)
            click.play(False)
        self.announce_reload(announce)

    # --- reload / deploy -------------------------------------------------------------------------
    def reload(self) -> None:                             # 0x1000161cc
        from .parameters import GameParameters
        self.stop_empty_loop()                            # PORT ADDITION: it is being reloaded now
        if self.bullets_total == 0:
            if not GameParameters.shared().last_announcer_value():
                return
            if self.last_announcer_speech <= 5.0:
                return
            self.last_announcer_speech = 0.0
            announcer = S3DEngine.engine().play_list_with_name('announcer')
            snd = announcer.any_sound_containing('outofammo') if announcer else None
            if snd is not None:
                snd.play()
            return
        if self.is_reloading():
            return
        Tracker.shared().reload_weapon_with_remaining_bullets(self.bullets_in_clip, self.name)
        snd = _at_the_sound(
            self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_reloadfull')) if self.playlist else None
        self.reload_sound = snd                           # PORT ADDITION: so pause and interrupt find this one
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.6)
            snd.play(False)
        self.change_state(8)

    def interrupt_reload(self) -> None:                   # 0x10001652c
        # DIVERGENCE: the original asks the playlist for a sound with the reload prefix and stops that,
        # and `anySoundWithPrefix:` returns a random one of them - not necessarily the one playing.  A
        # weapon with more than one reload sound could therefore be interrupted and go on reloading
        # aloud.  The sound `reload` started is remembered now, and that is the one stopped.
        snd = self.reload_sound
        if snd is None and self.playlist is not None:
            snd = self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_reloadfull')
        if snd is not None:
            snd.stop()
        self.reload_sound = None
        self.set_state(0)

    def deploy(self) -> None:                             # 0x1000166e4
        from .parameters import GameParameters
        self.change_state(1)
        self.time_since_last_shot = self.fire_rate
        self.prepare_burst_sounds()                       # PORT ADDITION: see prepare_burst_sounds
        pl = self.playlist
        snd = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_deploy')) if pl else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.6)
            snd.play(False)
        if GameParameters.shared().last_announcer_value():
            voice = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_voice')) if pl else None
            if voice is not None:
                voice.set_spatialized(False)
                voice.set_gain(0.6)
                voice.play(False)

    # --- pausing (PORT ADDITION) ------------------------------------------------------------------
    def pause(self) -> None:
        """Hold the weapon exactly where it is while the game is paused.

        DIVERGENCE: `pauseGame` 0x10005b5fc stops the timers and pauses the bricks and the ambience, and
        says nothing about the weapon.  Two things followed.  The reload sound is not a brick's, so it
        played on through the pause.  And `update:` 0x100014c8c advances `timeInState` by the wall clock
        between calls rather than by the timer's dt (the quirk at the top of this file), so the whole
        length of the pause was credited to the reload on the first pass after resuming: pausing during a
        reload finished it, however long the reload was.  Pausing mid-reload was a way to reload for
        free, which is what this stops."""
        for sound in (self.reload_sound, self.continuous_sound, self.continuous_warning):
            if sound is not None:
                sound.pause()

    def resume(self) -> None:
        for sound in (self.reload_sound, self.continuous_sound, self.continuous_warning):
            if sound is not None:
                sound.resume()
        # The pause must not count towards the state this weapon is in: start the wall clock again here.
        self.previous_tick_time = ca_current_media_time()

    def clean(self) -> None:                              # 0x100016a2c
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        self.stop_low_ammo_warning()

    def dealloc(self) -> None:                            # 0x100016a78 (called where ARC would release it)
        log.info('Dealloc weapon')
        if self.playlist is not None:
            self.playlist.deactivate()


class MeleeWeapon(Weapon):
    def update(self, dt: float) -> None:                  # -[ADMeleeWeapon update:] 0x10000740c
        if self._state == 2 and self.time_in_state > self.fire_rate:
            self.set_state(0)
        self.time_in_state = self.time_in_state + dt

    def single_shot(self) -> None:                        # 0x1000074c0
        self.set_state(2)
        if self.weapon_manager is not None:
            self.weapon_manager.did_shot_with_melee()

    def play_hit_sound(self) -> None:                     # 0x100007538
        """Not spatialised, as the original has it.

        REVERTED (user request): a version of this port placed the hit on the enemy that was struck and
        played `_miss_` at the player for the swing, on the reasoning that a blow you can hear the
        direction of is what an audio game is for.  Players did not want it.  `_hit_` is the swing and
        the impact in one recording, so splitting the two across two positions cut across the sound
        rather than opening it up, and it was a deliberate change to a game that was not asking for one:
        a melee weapon sounding from the hand is what the original does, on purpose, and this port's
        business is that game rather than a better idea of it."""
        snd = _at_the_sound(self.playlist.any_sound_containing('_hit_')) if self.playlist else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.8)
            snd.play(False)

    def play_miss_sound(self) -> None:                    # 0x100007610
        """Not spatialised, and right not to be: a miss is your own swing, and it hit nothing."""
        snd = _at_the_sound(self.playlist.any_sound_containing('_miss_')) if self.playlist else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.8)
            snd.play(False)
