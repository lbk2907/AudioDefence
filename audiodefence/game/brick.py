"""ADBrick - one wave: its enemies, passers-by, scripted sounds, power-up schedule and ambience."""
from __future__ import annotations

import logging

from ..platform import crand
from ..platform.defaults import ns_bool_value, ns_float_value
from ..s3d.engine import S3DEngine
from . import data

log = logging.getLogger('brick')


def _sa_get(spawn_after, key):
    return spawn_after.get(key) if isinstance(spawn_after, dict) else None


class Brick:
    # -[ADBrick initBrickWithName:] 0x10009ea80
    def __init__(self, name: str, tag: int = 0):
        from .enemy import Enemy
        self.name = name
        self.tag = tag
        self.brick_dictionary = data.plist(name) or {}
        self.enemies: list = []
        self.sounds: list = []
        self.playlists: set = set()
        self.playlists_requiring_activation: set = set()
        self.playlists_activated = 0
        self.tips = self.brick_dictionary.get('Tips')
        self.power_up_dictionary = self.brick_dictionary.get('PowerUp')
        self.time_in_brick = 0.0
        self.sounds_playlist = None
        self.ambiant_name = None
        #: PORT ADDITION: the passers-by this wave brought.  They live with every other passer-by in the
        #: passer-by manager; the wave's own list is how a wave held for a hand-over of weapons holds its own
        #: and no others (`BrickManager.update`).
        self.passers_by: list = []
        #: PORT ADDITION (user request, 2026-10-03): the enemies with neither a `spawn_time` nor a
        #: `spawn_after`, in a wave that tells a part of the Extra mode's story (`Story`).  The original spawns
        #: such an enemy as its wave is made, which here would set it in the arena - heard, and there to be shot
        #: with the clock stopped - while the story is read and the wave held
        #: (`ChallengeGameplayController.narrate`).  They are spawned on the wave's first update instead, the
        #: first tick it is not held; with no story read (the referee, a wave fought again after a revive) that
        #: is the tick after it was made, which is also when the original's would first have moved.
        self.held_spawns: list = []
        enemies = self.brick_dictionary.get('Enemies') or {}
        for key, d in enemies.items():
            e = Enemy(key)
            e.random_additional_spawn_angle = 0.0
            e.parent_brick = self
            self.playlists.add(e.sounds_prefix)
            e.set_position_from_dictionary(d)
            # PORT ADDITION: a wave of the port's own can say what its zombies carry.  `Rigged` gives
            # every one of them the blast the game gives a Farty, so the wave goes up in a chain from one
            # shot; `NoBlast` refuses them the one Chain Reaction lends, whatever is in hand.  The
            # original's own waves have neither key and are untouched.
            #
            # `NoBlast` leaves an enemy's *own* explosion alone, and used to throw it away as well - which
            # silenced the Farties in Powder Keg's crowds, whose bang is theirs out of `enemies.plist` and
            # the reason a player is glad to hear one.  `blast` answers with the enemy's own first and only
            # then consults this flag, so the flag by itself says exactly what was meant.
            if self.brick_dictionary.get('Rigged'):
                from .modifiers import CHAIN_REACTION_BLAST
                e.explosion_dictionary = dict(CHAIN_REACTION_BLAST)
            elif self.brick_dictionary.get('NoBlast'):
                e.no_lent_blast = True
            e.tag = ((self.tag * 100) | 1) + len(self.enemies)
            self.enemies.append(e)
            if d.get('spawn_time') is not None:
                e.spawn_time = ns_float_value(d.get('spawn_time'))
                e.set_state(0)
            elif d.get('spawn_after') is not None:
                e.spawn_after = d.get('spawn_after')
            elif self.brick_dictionary.get('Story'):      # PORT ADDITION: see `held_spawns`
                self.held_spawns.append(e)
            else:
                e.spawn()
        self.init_passers_by()
        self.init_sounds()

    def set_tag(self, tag: int) -> None:
        self.tag = tag

    def init_sounds(self) -> None:                            # 0x10009f274
        entries = self.brick_dictionary.get('Sounds') or []
        if entries:
            self.sounds_playlist = S3DEngine.engine().play_list_with_name(self.name)

            def on_activated(_pl, entries=entries):          # initSounds block 0x10009f4c0
                from .adsound import ADSound
                for d in entries:
                    self.sounds.append(ADSound(d))
            if self.sounds_playlist is not None:
                self.sounds_playlist.activate(on_activated)
        if self.brick_dictionary.get('Ambiant') is not None:
            self.ambiant_name = self.brick_dictionary.get('Ambiant')

    def init_passers_by(self) -> None:                        # 0x10009f6b4
        from .brick_manager import BrickManager
        from .passerby import CarAlarm, JukeBox, Machine, PasserBy
        entries = self.brick_dictionary.get('PasserBy')
        if not entries:
            return
        for index, (key, d) in enumerate(entries.items()):
            if key == 'Jukebox':
                p = JukeBox(key)
            elif key in ('Car', 'Car2', 'Car3'):
                p = CarAlarm(key)
            elif key == 'Machine':
                p = Machine(key)
            else:
                p = PasserBy(key)
            p.activate_playlist()
            p.set_position_from_dictionary(d)
            p.tag = index + self.tag * 100 + len(self.enemies) + 200001
            if d.get('spawn_time') is not None:
                p.spawn_time = ns_float_value(d.get('spawn_time'))
                p.set_state(0)
            elif d.get('spawn_after') is not None:
                p.spawn_after = d.get('spawn_after')
            else:
                p.spawn()
            BrickManager.shared().add_passer_by(p)
            self.passers_by.append(p)                     # PORT ADDITION: see `passers_by`

    # --- playlists -------------------------------------------------------------------------------
    def activate_all_playlists(self) -> None:                 # 0x10009fc98
        for name in self.playlists:
            self.playlists_requiring_activation.add(name)

    def load_playlist_with_name(self, name: str) -> None:     # loadPLaylistWithName: 0x10009fdec
        pl = S3DEngine.engine().play_list_with_name(name)
        if pl is not None:
            pl.activate(lambda _pl, name=name: self.on_playlist_activated(name))

    def activate_playlists_not_in_set(self, previous: set) -> set:   # 0x10009ffc8
        remaining = set(previous)
        for name in self.playlists:
            if name in previous:
                self.playlists_activated += 1
                self.on_playlist_activated(name)
                remaining.discard(name)
            else:
                self.playlists_requiring_activation.add(name)
        self.check_all_playlists_are_loaded()
        return remaining

    def deactivate_playlists_from_set(self, names) -> None:   # 0x1000a0560
        for name in list(names):
            pl = S3DEngine.engine().play_list_with_name(name)
            if pl is not None:
                pl.deactivate(lambda _pl: None)

    def deactivate_all_playlists(self) -> None:               # 0x1000a07b8
        for name in list(self.playlists or ()):
            pl = S3DEngine.engine().play_list_with_name(name)
            if pl is not None:
                pl.deactivate(lambda _pl: None)
        if self.sounds_playlist is not None:
            self.sounds_playlist.deactivate()
        self.playlists = None

    def on_playlist_activated(self, name: str) -> None:       # 0x1000a0a1c
        for e in self.enemies:
            if e.sounds_prefix == name:
                e.init_sounds()

    def check_all_playlists_are_loaded(self) -> None:         # 0x1000a0bf4
        if self.playlists_activated == len(self.playlists):
            for e in self.enemies:
                e.init_sounds()

    def random_tip(self):                                     # 0x1000a0310
        tip = None
        if self.tips:
            tip = self.tips[crand.rand() % len(self.tips)]
            if tip is not None and not str(tip).startswith('Tip') and crand.rand() % 100 > 19:
                return tip
        generic = data.plist_ro('Tips') or []
        if generic:
            return generic[crand.rand() % len(generic)]
        return tip

    # --- run -------------------------------------------------------------------------------------
    def clear_enemies(self) -> None:                          # 0x1000a0d94
        for e in self.enemies:
            e.deactivate()

    def update(self, dt: float) -> None:                      # 0x1000a0ed0
        from .brick_manager import BrickManager
        if self.held_spawns:                                  # PORT ADDITION: see `held_spawns`
            held, self.held_spawns = self.held_spawns, []
            for e in held:
                if e.life > 0.0:                              # not cleared away meanwhile (a revive's skip)
                    e.spawn()
        self.time_in_brick += dt
        for e in list(self.enemies):
            e.update(dt)
        for s in list(self.sounds):
            s.update(dt)
        pud = self.power_up_dictionary
        if pud is None:
            return
        if pud.get('spawn_time') is None and pud.get('force_spawn_time') is None:
            return
        t = self.time_in_brick
        st = ns_float_value(pud.get('spawn_time'))
        if (t - dt) < st and t >= st:
            BrickManager.shared().try_to_pop_power_up_container()
            return
        ft = ns_float_value(pud.get('force_spawn_time'))
        if (t - dt) < ft and t >= ft:
            BrickManager.shared().force_to_pop_power_up_container_with_type(pud.get('type'))

    def stop_all_enemies_after_player_death(self) -> None:    # 0x1000a1384
        for e in self.enemies:
            e.stop_after_player_was_killed()

    def stop_brick_ambiant(self) -> None:                     # 0x1000a1578
        from .ambient import AmbientManager
        if self.ambiant_name is not None:
            AmbientManager.shared().brick_with_ambiant_cleared(self.ambiant_name)

    def brick_is_cleared(self) -> bool:                       # 0x1000a1658
        for e in self.enemies:
            if e.life > 0.0:
                log.debug('%s still alive, life = %f', e.name, e.life)
                return False
        # DIVERGENCE: initSounds 0x10009f274 builds this wave's sounds inside the playlist's activation
        # callback, so for a short window after the wave loads `sounds` is empty even though the wave has
        # some.  brickIsCleared 0x1000a1658 walks the enemies and then that empty list and answers "yes".
        # A wave whose only content is a cutscene - tutorial_7_brick_4, the closing line of "Meet The
        # Farty", has no enemies at all - therefore looked finished the instant it loaded, and the challenge
        # ended before its sound existed.  On the phone the callback lands before anything can ask; here the
        # question arrives first, because a kill produces a second deactivation right behind the one that
        # advanced the wave.  A wave that is supposed to have sounds is not cleared until it has them.
        # `sounds_playlist is not None` keeps this from hanging a wave whose playlist is missing
        # altogether: then the sounds can never be built and waiting for them would never end.
        if ((self.brick_dictionary.get('Sounds') or []) and not self.sounds
                and self.sounds_playlist is not None):
            return False
        for s in self.sounds:
            if s.blocker and s.state != 3:
                return False
        return True

    def check_spawn_on_start(self, name: str) -> None:        # 0x1000a19fc
        for e in self.enemies:
            if e.life <= 0.0:
                continue
            if _sa_get(e.spawn_after, 'enemy') != name:
                continue
            if not ns_bool_value(_sa_get(e.spawn_after, 'afterStart')):
                continue
            e.spawn_time = ns_float_value(_sa_get(e.spawn_after, 'time'))
            e.set_state(0)
        for s in self.sounds:
            if s.state == 3:
                continue
            if _sa_get(s.spawn_after, 'enemy') != name:
                continue
            if not ns_bool_value(_sa_get(s.spawn_after, 'afterStart')):
                continue
            s.spawn_time = ns_float_value(_sa_get(s.spawn_after, 'time'))
            s.set_state(1)

    def check_spawn_after_kill(self, name: str, skipped: bool) -> None:   # 0x1000a20ac
        from .brick_manager import BrickManager
        shift = float('inf')
        if skipped:
            m = float('inf')
            for e in self.enemies:
                if e.life > 0.0 and _sa_get(e.spawn_after, 'enemy') == name and e.spawn_time < m:
                    m = e.spawn_time
            shift = m + -0.100000001
        for e in self.enemies:
            if e.life <= 0.0 or _sa_get(e.spawn_after, 'enemy') != name:
                continue
            if not ns_bool_value(_sa_get(e.spawn_after, 'afterStart')):
                e.spawn_time = ns_float_value(_sa_get(e.spawn_after, 'time'))
                e.set_state(0)
            elif skipped:
                if ns_bool_value(_sa_get(e.spawn_after, 'ignoreIfSkipped')):
                    e.set_state(-1)
                else:
                    e.spawn_time = e.spawn_time - shift
        for s in list(self.sounds):
            if s.state == 3 or _sa_get(s.spawn_after, 'enemy') != name:
                continue
            if not ns_bool_value(_sa_get(s.spawn_after, 'afterStart')):
                s.spawn_time = ns_float_value(_sa_get(s.spawn_after, 'time'))
                s.set_state(1)
            elif skipped:
                if ns_bool_value(_sa_get(s.spawn_after, 'ignoreIfSkipped')):
                    s.set_state(0)
                else:
                    s.play()
        pud = self.power_up_dictionary
        if pud is not None and pud.get('spawn_after') is not None and pud.get('spawn_after') == name:
            BrickManager.shared().try_to_pop_power_up_container()

    def stop_all_sounds(self) -> None:                        # 0x1000a2b64
        for s in self.sounds:
            s.stop_with_no_callback()

    def has_skippable_sounds_playing(self) -> bool:           # 0x1000a2c98
        return any(s.skippable and s.state == 2 and s.time_in_state > 0.15 for s in self.sounds)

    def skip_all_skippable_sounds(self) -> None:              # 0x1000a2e40
        for s in list(self.sounds):
            if s.skippable and s.state == 2:
                s.skip()

    def pause(self) -> None:                                  # 0x1000a2fbc
        for e in self.enemies:
            e.pause()
        for s in self.sounds:
            s.pause()

    def resume(self) -> None:                                 # 0x1000a31c4
        for e in self.enemies:
            e.resume()
        for s in self.sounds:
            s.resume()

    def clean(self) -> None:                                  # 0x1000a33cc
        for e in self.enemies:
            e.destroy_enemy()
        self.enemies.clear()
        self.deactivate_all_playlists()
