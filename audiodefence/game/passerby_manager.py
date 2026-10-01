"""ADPasserByManager - owns every passer-by: modifier cows/cars/jukebox/machine and brick "PasserBy" entries."""
from __future__ import annotations

import logging

from ..platform import crand
from .modifiers import GameModifiers

log = logging.getLogger('passerby')


class PasserByManager:
    def __init__(self):                                   # -[ADPasserByManager init] 0x1000d570c
        self.passers_by: list = []
        self.next_cow = 0.0
        self.next_car = 0.0

    def start_timers(self) -> None:                       # 0x1000d57c0
        mods = GameModifiers.shared()
        if mods.cows:
            self.randomize_next_cow()
        if mods.cars:
            self.randomize_next_car()
        if mods.jukebox:
            self.add_jukebox()
        if mods.machine:
            self.add_machine()

    def all_passer_by(self) -> list:                      # 0x1000d5964
        return self.passers_by

    def add_passer_by(self, p) -> None:                   # 0x1000d5974
        self.passers_by.append(p)

    def remove_all_passers_by(self) -> None:              # 0x1000d59a0
        self.passers_by.clear()

    def clean(self) -> None:                              # 0x1000d59bc
        for p in list(self.passers_by):                   # makeObjectsPerformSelector:@selector(deactivatePlaylist)
            p.deactivate_playlist()

    def update(self, dt: float) -> None:                  # 0x1000d59e4
        from .brick_manager import BrickManager
        # fast enumeration (a mutation during it would raise in the original)
        for p in list(self.passers_by):
            p.update(dt)
        bm = BrickManager.shared()
        # PORT DIVERGENCE (user request, 2026-09-30): `update:` 0x1000d59e4 returns here for any mode but
        # Endless, so the cows and the cars a modifier asks for arrive only there.  `startTimers` 0x1000d57c0
        # sets their clocks whatever the mode is and then nothing ever reads them again, while the Jukebox
        # and the Generator it adds itself have always worked anywhere - so three of the four already did
        # what a challenge would want and two of them did nothing.  A challenge a player writes can ask for
        # all four (`game/custom.ARENA_EXTRAS`), so a challenge counts here as well.
        #
        # Nothing of the game's own changes: not one of the original's 45 challenges carries a `Modifiers`
        # key at all, and of the port's six arenas that do, none names `cows` or `cars`.  Modes 3 and 4 - the
        # looping scenario and the menu demo - are left as they were, being nobody's to write.
        if bm.mode not in (1, 2):
            return
        mods = GameModifiers.shared()
        if mods.cows:
            if self.next_cow < 0.0:
                self.generate_cow()
            elif not bm.player_is_dead:
                self.next_cow = self.next_cow - dt
        if mods.cars:
            if self.next_car < 0.0:
                self.generate_car()
            elif not bm.player_is_dead:
                self.next_car = self.next_car - dt

    def generate_cow(self) -> None:                       # 0x1000d5d04
        from .brick_manager import BrickManager
        from .passerby import PasserBy
        name = self.available_playlist_name_in_array(['Cow', 'Cow2'])
        if name is None:
            # DIVERGENCE: generateCow 0x1000d5d04 returns here without touching nextCow, which is already
            # below zero, so update: called it again on every tick for as long as both cow playlists were
            # busy - a lookup and a failed allocation every frame.  The timer is re-rolled instead.
            self.randomize_next_cow()
            return
        p = PasserBy(name)
        p.init_sounds()
        p.set_random_position()
        p.tag = len(self.passers_by) + 200001
        p.spawn()
        # DIVERGENCE: generateCow 0x1000d5d04 appends the cow and then hands it to ADBrickManager
        # addPasserBy:, which forwards straight back to this manager's addPasserBy: and appends it again.
        # The duplicate was updated alongside the original, so cows moved and aged at twice their speed.
        # Cars do the same at 0x1000d5f08.  Each is added once.
        self.passers_by.append(p)
        self.randomize_next_cow()

    def generate_car(self) -> None:                       # 0x1000d5f08
        from .passerby import CarAlarm
        name = self.available_playlist_name_in_array(['Car', 'Car2', 'Car3'])
        if name is None:
            return
        c = CarAlarm(name)
        c.init_sounds()
        c.set_random_position_at_distance(6)
        c.tag = len(self.passers_by) + 200001
        c.spawn()
        self.passers_by.append(c)
        self.randomize_next_car()

    def randomize_next_car(self) -> None:                 # 0x1000d60e4
        self.next_car = float(crand.c_mod(crand.rand(), 45) + 25)

    def randomize_next_cow(self) -> None:                 # 0x1000d6140
        self.next_cow = float(crand.c_mod(crand.rand(), 35) + 15)

    def available_playlist_name_in_array(self, names: list):   # 0x1000d619c
        for p in list(self.passers_by):
            if p.can_be_shot_at():
                if p.sounds_prefix in names:              # removeObject: removes every equal object
                    names = [n for n in names if n != p.sounds_prefix]
        if not names:
            return None
        return names[crand.rand() % len(names)]

    def add_jukebox(self) -> None:                        # 0x1000d63d4
        from .passerby import JukeBox
        j = JukeBox('Jukebox')
        j.init_sounds()
        j.set_random_position()
        j.set_state(0)
        j.spawn_time = 2.0
        j.tag = len(self.passers_by) + 200000
        self.add_passer_by(j)

    def add_machine(self) -> None:                        # 0x1000d64e4
        from .passerby import Machine
        m = Machine('Machine')
        m.init_sounds()
        m.set_random_position_at_distance(6)
        m.set_state(0)
        m.spawn_time = 2.0
        m.tag = len(self.passers_by) + 200000
        self.add_passer_by(m)

    def pause(self) -> None:                              # 0x1000d65f8
        for p in list(self.passers_by):
            p.pause()

    def resume(self) -> None:                             # 0x1000d672c
        for p in list(self.passers_by):
            p.resume()
