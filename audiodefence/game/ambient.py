"""ADAmbientManager - background ambience, storm thunder, random scare sounds and enemy/brick ambiance loops."""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..s3d.engine import S3DEngine
from .modifiers import GameModifiers

log = logging.getLogger('ambient')

PI_D = 3.14159265


class AmbientManager:
    _shared: 'AmbientManager | None' = None

    @classmethod
    def shared(cls) -> 'AmbientManager':                  # +[ADAmbientManager sharedAmbiantManager] 0x100097e64
        if cls._shared is None:
            cls._shared = AmbientManager()
        return cls._shared

    def __init__(self):
        self.ambient_name = None
        self.scare_sound = None
        self.thunder_sound = None
        self.base_sound = None
        self.scare_sound_timer = 0.0
        self.next_storm_time = 0.0
        self.enemies_playlist = None
        self.enemies_ambiant_count = None
        self.ambiant_is_playing = False
        self.enemy_ambiant_sound = None
        self.gameplay_view_controller = None              # weak
        self.playlist = None
        self.storm_playlist = None
        self.ambient_sound = None

    def start_with_random_ambient(self) -> None:          # 0x100097efc
        names = ['ambient_ruins', 'ambient_ghosttown', 'ambient_foundry']
        self.start_with_ambient(names[crand.rand() % len(names)], 0.6)

    def start_with_ambient(self, name: str, gain: float) -> None:   # startWithambient:gain: 0x100098004
        if GameModifiers.shared().storm or name == 'ambient_storm':
            self.storm_playlist = S3DEngine.engine().play_list_with_name('ambient_storm')
            if self.storm_playlist is not None:
                self.storm_playlist.activate()
            self.ambient_sound = self.storm_playlist.any_sound_containing('ambient') if self.storm_playlist else None
            if self.ambient_sound is not None:
                self.ambient_sound.set_gain(gain if gain != 0.0 else 0.6)
                self.ambient_sound.set_stream(True)
                self.ambient_sound.play(True)
            self.randomise_next_storm_time()
        else:
            self.ambient_name = name
            self.playlist = S3DEngine.engine().play_list_with_name(name)

            def on_activated(_pl=None, gain=gain):        # startWithambient:gain:_block_invoke 0x1000984a8
                self.ambient_sound = self.playlist.any_sound_containing('ambient') if self.playlist else None
                if self.ambient_sound is not None:
                    self.ambient_sound.set_spatialized(False)
                    self.ambient_sound.set_gain(gain if gain != 0.0 else 0.6)
                    self.ambient_sound.set_stream(True)
                    self.ambient_sound.play(True)
                if self.gameplay_view_controller is not None:
                    self.gameplay_view_controller.ambiant_manager_did_activate_playlist()
            if self.playlist is not None:
                self.playlist.activate(on_activated)
        self.init_enemies_ambiant()
        self.scare_sound_timer = float(crand.arc4random() % 20 + 10)

    def start_base_sound(self) -> None:                   # 0x100098718
        self.base_sound = self.playlist.any_sound_with_prefix('BASE_') if self.playlist else None
        if self.base_sound is not None:
            self.base_sound.set_planar((4.0, 0.0, 0.0))
            self.base_sound.set_spatialized(True)
            self.base_sound.play(True)

    def random_position_at_distance(self, distance: int):   # 0x1000987f8
        a = (float(crand.c_mod(crand.rand(), 360)) * PI_D) / 180.0
        return float(distance) * math.sin(a), float(distance) * math.cos(a)

    def update(self, dt: float) -> None:                  # 0x10009887c
        from .brick_manager import BrickManager
        self.scare_sound_timer = self.scare_sound_timer - dt
        amb = self.ambient_sound
        if amb is not None and amb.key == 'storm_ambient' and amb.playing:
            self.next_storm_time = self.next_storm_time - dt
            if self.next_storm_time >= 0.0:
                return                                    # no scare sounds while the storm plays
            self.randomise_next_storm_time()
            self.play_thunder()
            return
        if self.scare_sound_timer >= 0.0:
            return
        if not BrickManager.shared().number_of_active_objects_on_scene() > 3:
            x, y = self.random_position()
            self.scare_sound = self.playlist.any_sound_containing('RANDOM_') if self.playlist else None
            if self.scare_sound is not None:
                self.scare_sound.set_spatialized(True)
                self.scare_sound.set_planar((x, y, 0.0))
                self.scare_sound.set_gain(3.0)
                self.scare_sound.play(False)
        self.scare_sound_timer = float(crand.c_mod(crand.rand(), 10) + 15)

    def random_position(self):                            # 0x100098b74
        a = (float(crand.arc4random() % 360) * PI_D) / 180.0
        dist = float(crand.arc4random() % 3 + 3)
        return math.sin(a) * dist, math.cos(a) * dist

    def stop_ambient(self) -> None:                       # 0x100098c10
        if self.ambient_sound is not None:
            self.ambient_sound.stop()
        if self.storm_playlist is not None:
            self.storm_playlist.deactivate()
        self.stop_enemies_ambient_and_reset_count()
        if self.playlist is not None:
            self.playlist.deactivate()
        if self.enemies_playlist is not None:
            self.enemies_playlist.deactivate()

    def randomise_next_storm_time(self) -> None:          # 0x100098d40
        self.next_storm_time = float(crand.c_mod(crand.rand(), 30) + 10)
        log.info('Next thunder : %f', self.next_storm_time)

    def play_thunder(self) -> None:                       # 0x100098db8
        self.thunder_sound = self.storm_playlist.any_sound_containing('thunder') if self.storm_playlist else None
        if self.thunder_sound is not None:
            self.thunder_sound.play()

    def init_enemies_ambiant(self) -> None:               # 0x100098e5c
        self.enemies_playlist = S3DEngine.engine().play_list_with_name('enemiesAmbiant')
        if self.enemies_playlist is not None:
            self.enemies_playlist.activate()
        self.enemies_ambiant_count = {}

    def enemy_with_ambiant_name_appeared(self, name) -> None:   # 0x100098f48
        self.check_ambiant()

    def enemy_with_ambiant_name_killed(self, name) -> None:     # 0x100098f68
        self.check_ambiant()

    def brick_with_ambiant_started(self, name) -> None:         # 0x100098f88
        self.check_ambiant()

    def brick_with_ambiant_cleared(self, name) -> None:         # 0x100098fa8
        self.check_ambiant()

    def play_enemy_ambiant_with_name(self, name, force_stop: bool) -> None:   # 0x100098fc8
        cur = self.enemy_ambiant_sound
        if cur is not None and cur.playing:
            if cur.key == name:
                return
            if force_stop:
                cur.stop()
        log.info('Play ambiant :%s', name)
        self.enemy_ambiant_sound = self.enemies_playlist.sound(name) if self.enemies_playlist else None
        if self.enemy_ambiant_sound is not None:
            self.enemy_ambiant_sound.play(True)
            self.enemy_ambiant_sound.set_stream(True)
            self.enemy_ambiant_sound.set_gain(0.085)

    def stop_ambiant(self) -> None:                       # 0x100099144
        if self.enemy_ambiant_sound is not None:
            self.enemy_ambiant_sound.stop()

    def enemy_with_current_ambiant_is_alive(self) -> bool:   # 0x100099160
        from .brick_manager import BrickManager
        key = self.enemy_ambiant_sound.key if self.enemy_ambiant_sound is not None else None
        for t in list(BrickManager.shared().all_potential_targets()):
            if not t.can_be_shot_at():
                continue
            if t.ambiant_name is None or t.ambiant_name != key:
                continue
            if self.enemy_ambiant_sound is not None and self.enemy_ambiant_sound.playing:
                return True
        return False

    def stop_enemies_ambient_and_reset_count(self) -> None:   # 0x1000993f4
        log.info('stopEnemiesAmbientAndResetCount')
        if self.enemy_ambiant_sound is not None:
            self.enemy_ambiant_sound.stop()
        self.ambiant_is_playing = False

    def check_ambiant(self) -> None:                      # 0x100099444
        from .brick_manager import BrickManager
        bm = BrickManager.shared()
        # DIVERGENCE: the original only refuses to (re)start an ambience when the player is dead.  Ending a
        # game from the pause screen is not a death, and killGameplay's clean-up 0.1 s later reports every
        # enemy as gone, which calls this again - with a Chainsaw still in the brick that starts its
        # ambience over, after the game is already finished, and nothing is left to stop it.  killGameplay
        # clears the gameplay controller, so that is the test for "there is no game any more".
        if bm.player_is_dead or bm.gameplay_view_controller is None:
            self.stop_enemies_ambient_and_reset_count()
            return
        log.info('[AMBIANT] Checking ambiant')
        brick = bm.current_brick()
        brick_ambiant = brick.ambiant_name if brick is not None else None
        if brick_ambiant is not None:
            # the brick's own ambience wins, and the method returns here: the tail call at 0x09965c-0x099678
            # restores the frame and branches to objc_release, so nothing below runs while the current brick
            # names an ambience.  A Chainsaw arriving during a horde wave therefore does not take it over.
            log.info('[AMBIANT] Try to play brick ambiant : %s', brick_ambiant)
            self.play_enemy_ambiant_with_name(brick_ambiant, True)
            return
        # PORT ADDITION (user request, 2026-10-01): a wave can ask to be played without the music a zombie
        # brings with it.  Six of the game's enemies carry an `ambiant` in `enemies.plist` - the Chainsaw,
        # the Hulk and HulkB, the Whisperer, and the Dog and DodgeB, which is four themes between them - and
        # somebody building a wave may want the arena they chose rather than whichever zombie walked in
        # last.  One wave at a time (`custom.ZOMBIE_THEMES`), so one wave of a storyline can be quiet and
        # the next can have the Dog's theme walking in with it.
        #
        # Asked here: below the brick's own `Ambiant`, which is the wave's music rather than a zombie's and
        # wins as it always did, and above the walk over what is standing in the arena.
        if brick is not None and brick.brick_dictionary.get('NoZombieThemes'):
            log.info('[AMBIANT] %s asked for no zombie themes', brick.name)
            self.stop_ambiant()
            return
        if self.enemy_with_current_ambiant_is_alive():
            log.info('[AMBIANT]Enemy with current ambiant is alive')
            return
        for t in list(bm.all_potential_targets()):
            if t.can_be_shot_at() and t.ambiant_name is not None:
                log.info('[AMBIANT] Try to play enemy ambiant : %s', t.ambiant_name)
                self.play_enemy_ambiant_with_name(t.ambiant_name, True)
                return
        log.info('[AMBIANT] Stop ambiant ')
        self.stop_ambiant()

    def pause(self) -> None:                              # 0x100099928
        """DIVERGENCE (user request): the arena keeps its ambience through the pause menu.

        The original pauses all three of these.  The base sound and the storm are the room a player is
        standing in, and a room that falls silent the moment a menu opens is a room that has gone away; the
        enemy ambience is a zombie making a noise - a Chainsaw revving - and that is not the room, so it
        pauses with everything else the zombies are doing.
        """
        if self.enemy_ambiant_sound is not None and self.enemy_ambiant_sound.playing:
            self.enemy_ambiant_sound.pause()

    def resume(self) -> None:                             # 0x1000999e8
        if self.enemy_ambiant_sound is not None:
            self.enemy_ambiant_sound.resume()
