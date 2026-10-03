"""ADPlayer - explosion tinnitus (with reverb swell) and the proximity heartbeat."""
from __future__ import annotations

import logging

from ..s3d.engine import S3DEngine

log = logging.getLogger('player')

#: PORT DIVERGENCE (user request): as long as a ring can last, however many blasts went into it.  One
#: explosion rings for at most 13 s (`intensity * 10 + 3`) and they add up now, so a crowd of exploding
#: zombies would otherwise leave a player deafened for minutes.  Twenty is comfortably longer than any
#: single blast can manage and still ends.
TINNITUS_MAX = 20.0


class Player:
    def __init__(self):                                   # -[ADPlayer init] 0x1000b647c
        self.tinnitus_sound = None
        self.tinnitus_duration = 0.0
        self.tinnitus_timer = 0.0
        self.tinnitus_intensity = 0.0
        self.proximity_bpm = 0.0
        self.last_heartbeat = 0.0
        self.total_time = 0.0
        engine = S3DEngine.engine()
        self.tinnitus_playlist = engine.play_list_with_name('tinnitus')
        if self.tinnitus_playlist is not None:
            self.tinnitus_playlist.activate()
        self.player_playlist = engine.play_list_with_name('player')
        if self.player_playlist is not None:
            self.player_playlist.activate()

    def update(self, dt: float) -> None:                  # 0x1000b660c
        from .brick_manager import BrickManager
        self.total_time = self.total_time + dt
        if self.tinnitus_duration > 0.0:
            if self.tinnitus_timer >= self.tinnitus_duration:
                self.stop_tinnitus()
                self.tinnitus_duration = 0.0
            else:
                self.tinnitus_timer = self.tinnitus_timer + dt
                if self.tinnitus_timer > self.tinnitus_duration * 0.8:
                    fade = 1.0 - self.tinnitus_timer / self.tinnitus_duration
                    if self.tinnitus_sound is not None:
                        self.tinnitus_sound.set_gain((fade * self.tinnitus_intensity) / 0.2)
                    S3DEngine.engine().set_reverb_volume((fade * 5.0) / 0.2 + 1.0)
        bm = BrickManager.shared()
        if bm.player_is_dead:
            return
        d2 = bm.minimum_squared_distance
        if d2 >= 9.0:
            return
        t2 = (d2 + -0.09) / 7.29
        if t2 > 1.0:
            t2 = 1.0
        closeness = 1.0 if t2 < 0.0 else 1.0 - t2
        self.proximity_bpm = closeness * 60.0 + 120.0
        if self.total_time <= self.last_heartbeat + 60.0 / self.proximity_bpm:
            return
        self.last_heartbeat = self.total_time
        heart = self.player_playlist.any_sound_containing('heart') if self.player_playlist is not None else None
        if heart is not None:
            heart.play()
            heart.set_gain(closeness * closeness * 0.7 + 0.3)
        from ..platform.haptics import Haptics            # PORT ADDITION: felt on a controller as well
        Haptics.shared().heartbeat(closeness, heart.path)

    def pause(self) -> None:
        """PORT ADDITION (user request): the ringing in a player's ears pauses with the game.

        `pauseGame` 0x10005b5fc pauses the bricks and the ambience and says nothing about the player, so
        the tinnitus rang on through the pause menu - and it loops now, so it rang on for as long as a
        player left the game sitting there.  Its timer does not advance while paused (`update` is driven by
        the timers `pauseGame` stops), so it comes back with exactly as long left as it had.
        """
        if self.tinnitus_sound is not None and self.tinnitus_sound.playing:
            self.tinnitus_sound.pause()

    def resume(self) -> None:
        if self.tinnitus_sound is not None:
            self.tinnitus_sound.resume()

    def start_tinitus_with_intensity(self, intensity: float) -> None:   # 0x1000b6940
        self.start_tinnitus_with_duration(intensity * 10.0 + 3.0, intensity * 0.8 + 0.1)

    def start_tinnitus_with_duration(self, duration: float, gain: float) -> None:   # 0x1000b6984
        # PORT DIVERGENCE (user request): a second blast makes the ringing last longer, and is heard.
        #
        # The original takes the new duration and gain whole and resets the timer, so a weak blast landing
        # while a bad one is still ringing *shortens* it - 13 seconds left becomes 4 - and quietens it.  The
        # longer of the two and the louder of the two are kept instead, so another explosion can only ever
        # add to a ring, which is what an ear does.
        running = self.tinnitus_duration > 0.0
        if running:
            # what is left of the ring plus what the new blast is worth, to TINNITUS_MAX (user request):
            # a second explosion adds to the first rather than replacing it.  The louder of the two gains
            # is kept, so a distant blast can lengthen a bad ring but never quieten one.
            duration = min(TINNITUS_MAX, duration + (self.tinnitus_duration - self.tinnitus_timer))
            gain = max(gain, self.tinnitus_intensity)
        # The recording is 14.1 s and the effect is at most 13, so one blast never outlasts its sound.  Two
        # do: the original only starts the sound when no ring is running at all, so a blast that extended a
        # ring past 14.1 s left the reverb on every enemy with nothing ringing over it.  The sound is
        # started whenever it is not playing, which covers both.
        if self.tinnitus_sound is None:
            self.tinnitus_sound = self.tinnitus_playlist.sound('tinnitus_and_background') \
                if self.tinnitus_playlist is not None else None
        if self.tinnitus_sound is not None and not self.tinnitus_sound.playing:
            # PORT DIVERGENCE (user request): looping.  The recording is 14.1 s and a ring can now run to
            # TINNITUS_MAX, so it has to come round again rather than leave the reverb sitting on every
            # enemy with nothing over it.  `stop_tinnitus` is what ends it, which the original did not
            # need to do because its ring could never outlast one playing of the file.
            self.tinnitus_sound.play(True)
        if self.tinnitus_sound is not None:
            self.tinnitus_sound.set_gain(gain)
        self.tinnitus_intensity = gain
        self.tinnitus_duration = duration
        self.tinnitus_timer = 0.0
        engine = S3DEngine.engine()
        engine.set_reverb_room_size(gain * 0.6 + 1.5)
        engine.set_reverb_dampening(10.0)
        engine.set_reverb_volume(gain * 3.0 + 3.0)

    def stop_tinnitus(self) -> None:                      # 0x1000b6b4c
        log.info('Stop tinnitus')
        # PORT DIVERGENCE: the original leaves the sound to run itself out, which it always did before the
        # ring ended.  It loops now, so ending the ring has to end it.  The fade over the last fifth has
        # taken the gain to nothing by here, so what stops is already silent.
        if self.tinnitus_sound is not None:
            self.tinnitus_sound.stop()
        engine = S3DEngine.engine()
        engine.set_reverb_room_size(1.5)
        engine.set_reverb_dampening(50.0)

    def reset_tinnitus(self) -> None:
        """PORT ADDITION (user request, 2026-10-03): a revive gives the player fresh ears.  The original's
        `revive` 0x10005bec0 says nothing to the player, so a blast heard just before the death went on ringing
        into the revived game - the sound and the reverb it swells on every enemy - for up to its full length.
        The ring is ended where it stands: the sound stops, the reverb goes back (`stop_tinnitus`; the
        ambience the revive starts again sets the rest), and nothing of it is left to extend."""
        if self.tinnitus_duration > 0.0 or (self.tinnitus_sound is not None and self.tinnitus_sound.playing):
            self.stop_tinnitus()
        self.tinnitus_duration = 0.0
        self.tinnitus_timer = 0.0
        self.tinnitus_intensity = 0.0

    def dealloc(self) -> None:                            # 0x1000b6c10
        if self.tinnitus_sound is not None:
            self.tinnitus_sound.stop()
        if self.tinnitus_playlist is not None:
            self.tinnitus_playlist.deactivate()
        if self.player_playlist is not None:
            self.player_playlist.deactivate()
