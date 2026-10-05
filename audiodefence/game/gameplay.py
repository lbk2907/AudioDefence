"""Gameplay screens: ADGameplayViewController (endless), ADChallengeGameplayViewController,
ADOpenerGameplayViewController, and the input objects they own.

UIKit pieces are replaced by small models that keep the original decisions:
* ``InfiniteScrollView`` - ADInfiniteScrollView: turning.  The heading is derived from a content offset
  over a ``line.png``-wide strip (430 points in the iPhone nib), exactly as -sendOffsetToDelegate does.
  All four gameplay scroll views receive identical input, so one instance stands for them.
* ``MotionManager`` - ADMotionManager: fed by the keyboard instead of CoreMotion (see ``KeyboardMotion``).
* ``AccessibleGameView`` - ADAccessibleGameView: the VoiceOver game surface.  Keys press/release
  "touches" at the centre of the quadrant the original button mode assigns to each action.
* ``WeaponTouchArea`` - ADWeaponTouchArea / ADButtonWithSwipe logic (used when no screen reader runs).

The screen (``host``) is only asked to present things; it never decides game logic.
"""
from __future__ import annotations

import logging
import math

from ..platform import host as system
from ..platform.cfloat import f32
from ..platform.runloop import RunLoop
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .ambient import AmbientManager
from .brick_manager import BrickManager
from .ingame_stats import InGameStats, notify_stats
from .missions import MissionManager
from .modifiers import GameModifiers
from .parameters import GameParameters

log = logging.getLogger('gameplay')

LINE_PNG_WIDTH = 430.0          # line@2x.png is 860 px wide -> 430 points (iPhone nib, all scroll views)
VIEW_WIDTH = 480.0              # iPhone landscape view, used only to place quadrant "touches"
VIEW_HEIGHT = 320.0


# ============================================================================================ motion
class MotionManager:
    """ADMotionManager.  The port has no CoreMotion: ``KeyboardMotion`` supplies yaw and tilt."""
    _shared: 'MotionManager | None' = None

    @classmethod
    def shared(cls) -> 'MotionManager':                   # +[ADMotionManager sharedInstance] 0x100005830
        if cls._shared is None:
            cls._shared = MotionManager()
        return cls._shared

    def __init__(self):
        self.last_gyro_angle = 0.0
        self.last_tilt_angle = 0.0
        self.running = False
        self.source = None                                # KeyboardMotion

    def start_motion_manager(self) -> None:               # 0x100005950
        self.running = True

    def destroy_motion_manager(self) -> None:             # 0x100005c58
        self.running = False

    def get_yaw_difference(self) -> float:                # 0x100005c9c
        return f32(self.source.take_yaw_difference()) if (self.running and self.source) else 0.0

    def get_tilt_angle(self) -> float:                    # 0x100005dec
        return f32(self.source.tilt_angle()) if (self.running and self.source) else 0.0


class KeyboardMotion:
    """PORT INPUT: stands in for the device attitude.

    Holding Left/Right turns the virtual device: for the gyro scheme the yaw changes by
    ``yaw_rate`` radians per second; for the tilt scheme the device is held at ``tilt`` radians.
    Turning right lowers the heading (the same direction as the original's rightward swipe)."""

    def __init__(self, yaw_rate: float = 2.0, tilt: float = 0.5):
        self.yaw_rate = yaw_rate
        self.tilt = tilt
        self.direction = 0                                # -1 left, +1 right
        self._yaw_accum = 0.0
        self._last = RunLoop.main().now()

    def set_direction(self, direction: int) -> None:
        self._advance()
        self.direction = direction

    def _advance(self) -> None:
        now = RunLoop.main().now()
        rate = self.yaw_rate * GameParameters.shared().turn_speed_factor()
        self._yaw_accum += -self.direction * rate * (now - self._last)
        self._last = now

    def take_yaw_difference(self) -> float:
        self._advance()
        value, self._yaw_accum = self._yaw_accum, 0.0
        return value

    def tilt_angle(self) -> float:
        # DIVERGENCE (user request, 2026-09-29): the device leans the way that turns it *left* when the angle
        # is positive.  `getTiltAngle` 0x100005dec reads the attitude's pitch, whose sign in landscape follows
        # which way round the phone is held (statusBarOrientation), and `tiltDidMoveFromAngle:` 0x10009cfe8
        # scales it by -15 and the sensitivity; this stood in for it with the sign the other way, so under
        # Tilt the right key and a stick pushed right turned left, against Gyro and Swipe.
        return -self.direction * self.tilt


# ======================================================================================= scroll view
class InfiniteScrollView:
    def __init__(self, image_width: float = LINE_PNG_WIDTH):
        # -[ADInfiniteScrollView awakeFromNib] 0x10009c4b0
        self.image_width = f32(image_width)
        self._delegate_set = False
        self.content_offset = 0.0
        self.set_content_offset((self.image_width * 3) * 0.5)
        self._delegate_set = True
        self.current_control_scheme = GameParameters.shared().control_scheme
        self.control_scheme_changed()
        # DIVERGENCE: the original sets this offset before it sets the delegate (0x10009c728, then
        # 0x10009c740), so the engine's head orientation stays 0 while the heading is really pi - half a
        # turn out.  On a phone the gyro fires within milliseconds of the game starting and corrects it
        # before anyone notices; here nothing moves until a turn key is pressed, so the first enemies are
        # heard half a turn from where they are.  The port sends the starting heading once.
        self.send_offset_to_delegate()

    def set_content_offset(self, x: float) -> None:       # UIScrollView: didScroll only on a change
        if x == self.content_offset:
            return
        self.content_offset = x
        if self._delegate_set:
            self.scroll_view_did_scroll()

    def scroll_view_did_scroll(self) -> None:             # 0x10009c814
        if GameParameters.shared().control_scheme == 1:
            return
        self.adjust_offset()
        self.send_offset_to_delegate()

    def adjust_offset(self) -> None:                      # 0x10009c928
        w = float(self.image_width)
        if self.content_offset < w * 0.5:
            self.set_content_offset(self.content_offset + w)
        if self.content_offset > w * 1.5:
            self.set_content_offset(self.content_offset - w)

    def send_offset_to_delegate(self) -> None:            # 0x10009ca34
        off = int(self.content_offset)                    # fcvtzs
        width = int(self.image_width)
        q = int(off / width)                              # sdiv truncates toward zero
        t1 = off - q * width
        frac = f32(1.0 - f32(float(t1) / self.image_width))
        sign = -1.0 if GameParameters.shared().control_scheme == 2 else 1.0
        S3DEngine.engine().set_head_orientation(f32(sign * (frac * 6.28318531)))

    def control_scheme_changed(self) -> None:             # 0x10009cb50
        scheme = GameParameters.shared().control_scheme
        if scheme == 1 or scheme == 3:
            self.enable_gyro()
            MotionManager.shared().start_motion_manager()
        if scheme == 2:
            self.disable_gyro()

    @staticmethod
    def disable_gyro() -> None:                           # 0x10009cd04
        MotionManager.shared().destroy_motion_manager()

    @staticmethod
    def enable_gyro() -> None:                            # 0x10009cd68
        MotionManager.shared().start_motion_manager()

    def update(self) -> None:                             # 0x10009cdcc
        params = GameParameters.shared()
        if self.current_control_scheme != params.control_scheme:
            self.current_control_scheme = params.control_scheme
            self.control_scheme_changed()
        if params.control_scheme == 1:
            self.gyro_did_move_from_angle(MotionManager.shared().last_gyro_angle)
        if params.control_scheme == 3:
            self.tilt_did_move_from_angle(MotionManager.shared().last_tilt_angle)

    def tilt_did_move_from_angle(self, angle: float) -> None:   # 0x10009cfe8
        if GameParameters.shared().control_scheme != 3:
            return
        delta = f32(f32(GameParameters.shared().sensivity * angle) * -15.0)
        self.set_content_offset(delta + self.content_offset)
        self.adjust_offset()
        self.send_offset_to_delegate()

    def gyro_did_move_from_angle(self, angle: float) -> None:   # 0x10009d148
        if GameParameters.shared().control_scheme != 1:
            return
        delta = f32((angle / -6.28318531) * self.image_width)
        self.set_content_offset(self.content_offset + delta)
        self.adjust_offset()
        self.send_offset_to_delegate()

    def turn_by(self, radians: float) -> None:
        """PORT ADDITION (user request, 2026-10-05): the view turned by `radians`, as the gyroscope turns it,
        whatever is turning it besides (The Magpie, GameplayController.turn_by_itself)."""
        self.set_content_offset(self.content_offset + f32((radians / 6.28318531) * self.image_width))
        self.adjust_offset()
        self.send_offset_to_delegate()

    def player_swiped(self, amount: float) -> None:       # 0x10009d278
        radians = f32((f32(f32(amount) / f32(5.68888903)) * 3.14159265) / 180.0)
        delta = f32((radians / 6.28318531) * self.image_width)
        self.set_content_offset(self.content_offset + delta)
        self.adjust_offset()
        self.send_offset_to_delegate()


# ================================================================================== touch surfaces
class AccessibleGameView:
    """ADAccessibleGameView - the full-screen surface used while VoiceOver (here: a screen reader) runs."""

    def __init__(self, gameplay):
        self.has_swiped = False
        self.has_started_to_move = False
        self.button_pressed_duration = 0.0
        self.initial_point = (0.0, 0.0)
        self._button_is_down = False
        self.weapon_manager = None                        # weak
        self.gameplay_view_controller = gameplay          # weak
        self.frame = (0.0, 0.0, VIEW_WIDTH, VIEW_HEIGHT)

    # quadrant centres, as the button-mode tests read them
    TOP_LEFT = (VIEW_WIDTH * 0.25, VIEW_HEIGHT * 0.25)
    TOP_RIGHT = (VIEW_WIDTH * 0.75, VIEW_HEIGHT * 0.25)
    BOTTOM_LEFT = (VIEW_WIDTH * 0.25, VIEW_HEIGHT * 0.75)
    BOTTOM_RIGHT = (VIEW_WIDTH * 0.75, VIEW_HEIGHT * 0.75)

    def handle_swipe_gesture(self) -> None:               # 0x10008a194
        self.has_swiped = True
        self.set_button_is_down(False)
        self.touch_canceled()

    def handle_swipe_up_gesture(self) -> None:            # 0x10008a1ec
        if GameParameters.shared().button_mode:
            return
        self.handle_swipe_gesture()
        if self.weapon_manager is not None:
            self.weapon_manager.select_next_weapon()

    def handle_swipe_down_gesture(self) -> None:          # 0x10008a2f8
        if GameParameters.shared().button_mode:
            return
        self.handle_swipe_gesture()
        if self.weapon_manager is not None:
            self.weapon_manager.reload_gesture_down()

    def touches_began(self, point) -> None:               # 0x10008a404
        self.initial_point = (float(point[0]), float(point[1]))
        self.set_button_is_down(True)
        self.has_swiped = False
        self.has_started_to_move = False

    def touches_ended(self) -> None:                      # 0x10008a50c
        self.set_button_is_down(False)
        self.has_swiped = False
        self.has_started_to_move = False
        if self.weapon_manager is not None:
            self.weapon_manager.continuous_stop()

    def touches_moved(self, point) -> None:               # 0x10008a5a4
        dx = float(point[0]) - self.initial_point[0]
        if GameParameters.shared().control_scheme == 2 and self.gameplay_view_controller is not None:
            self.gameplay_view_controller.touches_move_detected(dx, not self.has_started_to_move)
        self.has_started_to_move = True
        self.has_swiped = abs(dx) > 30

    def update(self, dt: float) -> None:                  # 0x10008a754
        if not self._button_is_down:
            self.button_pressed_duration = 0.0
            return
        self.button_pressed_duration = f32(self.button_pressed_duration + dt)
        d = self.button_pressed_duration
        if d <= 0.2:
            return
        if d > float(f32(dt)) + 0.2:
            return
        if self.has_swiped:
            return
        # FIX (Android, user request): the hold starts fire once per touch.  The duration is added up in
        # 32-bit floats, and on the phone the step is the real time since the last tick (_weapons_dt), so
        # four 0.05 s steps come to a hair over 0.2 and the fifth still passes the window below: the hold
        # began twice, which on a single-shot weapon (pistol, shotgun...) fired two shots.  With the fixed
        # 0.01 s step of the desktop the window passes exactly once, so there it is left as it was.
        if system.ANDROID and getattr(self, '_hold_fired', False):
            return
        if GameParameters.shared().button_mode:
            if self.initial_point[0] < self.frame[2] * 0.5:
                return
            if self.initial_point[1] >= self.frame[3] * 0.5:
                return
        if self.weapon_manager is not None:
            self._hold_fired = True
            self.weapon_manager.continuous_start()

    def solve_button_press(self) -> None:                 # 0x10008a914
        wm = self.weapon_manager
        x, y = self.initial_point
        w, h = self.frame[2], self.frame[3]
        if GameParameters.shared().button_mode:
            if x < w * 0.5 and y < h * 0.5:
                wm.shoot_with_melee()
                return
        else:
            wm.weapon_single_shot()
            return
        if x >= w * 0.5 and y < h * 0.5:
            # DIVERGENCE: the original starts continuous fire here, even for a press too short to hold -
            # it begins the weapon's looping "conti" sound and the release stops it again milliseconds
            # later, so tapping fire in Button mode spends bullets almost silently and never reaches the
            # empty click or the reload call-out.  The fire button this quadrant stands for does the
            # opposite (ADButtonWithSwipe: a press under 0.28 s is a single shot), and so does Gesture
            # mode, so a tap here is a single shot too.  Holding still starts continuous fire, from
            # update(), which is untouched.
            wm.weapon_single_shot()
            return
        if x < w * 0.5 and y >= h * 0.5:
            wm.select_next_weapon()
            return
        if x >= w * 0.5 and y >= h * 0.5:
            wm.reload_gesture_down()

    def touch_canceled(self) -> None:                     # 0x10008abcc
        self.set_button_is_down(False)
        if self.weapon_manager is not None:
            self.weapon_manager.continuous_stop()
        self.has_swiped = False

    def set_button_is_down(self, down: bool) -> None:     # 0x10008ac54
        self._button_is_down = bool(down)
        self._hold_fired = False                          # PORT ADDITION: see update
        if down:
            return
        if not self.has_swiped and self.button_pressed_duration < 0.2 and self.weapon_manager is not None:
            self.solve_button_press()
        self.button_pressed_duration = 0.0

    def handle_triple_tap(self) -> None:                  # 0x10008acf8
        if GameParameters.shared().button_mode:
            return
        if self.weapon_manager is not None:
            self.weapon_manager.shoot_with_melee()


class ButtonWithSwipe:
    """ADButtonWithSwipe (and ADWeaponTouchArea, which adds swipe up/down): hold 0.28 s for continuous fire,
    release earlier for a single shot, or, without a weapon manager, the button's own action."""

    def __init__(self, action=None, allow_swipe: bool = False):
        self.has_swiped = False
        self.button_pressed_duration = 0.0
        self._button_is_down = False
        self.weapon_manager = None                        # weak
        self.gameplay_view_controller = None              # weak
        self.action = action                              # the IBAction removed from the target list
        self.allow_swipe = allow_swipe
        self.pan_began = False

    def update(self, dt: float) -> None:                  # 0x10002493c (icon refresh omitted)
        if self._button_is_down:
            self.button_pressed_duration = f32(self.button_pressed_duration + dt)
            d = self.button_pressed_duration
            if d > 0.28 and not d > float(f32(dt)) + 0.28 and not self.has_swiped:
                if self.weapon_manager is not None:
                    self.weapon_manager.continuous_start()
        else:
            self.button_pressed_duration = 0.0

    def set_button_is_down(self, down: bool) -> None:     # 0x100024cf4
        self._button_is_down = bool(down)
        if down:
            self.has_swiped = False
            return
        if not self.has_swiped and self.button_pressed_duration < 0.28:
            if self.weapon_manager is not None:
                self.weapon_manager.weapon_single_shot()
            elif self.gameplay_view_controller is not None \
                    and not isinstance(self.gameplay_view_controller, OpenerGameplayController) \
                    and self.action is not None:
                self.action()
        self.button_pressed_duration = 0.0

    def touched_down(self) -> None:                       # 0x100024e8c
        self.set_button_is_down(True)

    def touched_up(self) -> None:                         # 0x100024ea0
        self.set_button_is_down(False)
        if self.weapon_manager is not None:
            self.weapon_manager.continuous_stop()

    def touch_canceled(self) -> None:                     # 0x100024f38
        if self.pan_began and self.button_pressed_duration < 0.28:
            return
        self.set_button_is_down(False)
        if self.weapon_manager is not None:
            self.weapon_manager.continuous_stop()

    def handle_swipe_gesture(self) -> None:               # 0x100025004
        self.has_swiped = True
        self.set_button_is_down(False)
        self.touch_canceled()

    def handle_triple_tap(self) -> None:                  # 0x100025174
        if GameParameters.shared().button_mode:
            return
        if self.weapon_manager is not None:
            self.weapon_manager.shoot_with_melee()


class WeaponTouchArea(ButtonWithSwipe):
    def handle_swipe_up_gesture(self) -> None:            # -[ADWeaponTouchArea handleSwipeUpGesture] 0x100040884
        self.handle_swipe_gesture()
        if self.weapon_manager is not None:
            self.weapon_manager.select_next_weapon()

    def handle_swipe_down_gesture(self) -> None:          # 0x100040934
        self.handle_swipe_gesture()
        if self.weapon_manager is not None:
            self.weapon_manager.reload_gesture_down()


# ========================================================================================= overlays
class ReviveController:
    """ADReviveViewController."""

    def __init__(self, cost: int, skip_cost=None):        # -initWithCost: 0x100021168
        self.cost = int(cost)
        self.skip_cost = None if skip_cost is None else int(skip_cost)   # PORT ADDITION: see
        self.skip_enabled = True                                         # skip_button_pressed
        self.gameplay_view_controller = None              # weak
        self.revive_stand_by_sound = None
        self.revive_playlist = S3DEngine.engine().play_list_with_name('revive')
        if self.revive_playlist is not None:
            self.revive_playlist.activate()
        self.revive_enabled = True
        self.tip = None
        self.revive_label = None

    def view_did_load(self) -> None:                      # 0x100021284
        if self.cost != 0:
            self.revive_label = f'Revive for {self.cost} diamond'     # accessibilityLabel
        else:
            self.revive_label = 'free revive'
        brick = BrickManager.shared().current_brick()
        self.tip = brick.random_tip() if brick is not None else None
        self.revive_stand_by_sound = self.revive_playlist.sound('revive_standby') if self.revive_playlist else None
        if self.revive_stand_by_sound is not None:
            self.revive_stand_by_sound.play(True)

    def view_will_appear(self) -> None:                   # 0x100021794
        from .inventory import Inventory
        if Inventory.shared().diamonds <= 0:
            self.revive_enabled = False                   # alpha 0.4, setEnabled:NO
            self.skip_enabled = False

    def revive_button_pressed(self, skip: bool = False) -> bool:   # 0x1000218a8; False: "no diamonds" alert
        from .inventory import Inventory
        inv = Inventory.shared()
        cost = self.skip_cost if skip else self.cost
        if not inv.diamonds >= cost:
            return False
        if skip:
            self.gameplay_view_controller.revive(skip=True)
        else:
            self.gameplay_view_controller.revive()
        inv.set_diamonds(inv.diamonds - cost)
        Tracker.shared().revive_used_with_cost(cost)
        notify_stats('RESET_BRICK_TIME', None)
        if self.revive_stand_by_sound is not None:
            self.revive_stand_by_sound.stop()
        yes = self.revive_playlist.sound('revive_yes') if self.revive_playlist else None
        if yes is not None:
            yes.play()
            pl = self.revive_playlist
            yes.add_3d_sound_end_callback(lambda _s: pl.deactivate())
        return True

    def skip_button_pressed(self) -> bool:
        """PORT ADDITION (user request, 2026-10-01): in an arena of the Extra mode the revive replays the wave
        died in, and this, for `ChallengeGameplayController.REVIVE_SKIP_FACTOR` times its price, goes on to
        the next wave instead - offered only while there is a next wave, so a win is never bought.  It is
        the revive in every other way: the same sounds, the same price doubling after it."""
        return self.revive_button_pressed(skip=True)

    def game_over_button_pressed(self) -> None:           # 0x100021b3c
        Tracker.shared().game_over_button_pressed()
        self.gameplay_view_controller.game_over()
        if self.revive_stand_by_sound is not None:
            self.revive_stand_by_sound.stop()
        no = self.revive_playlist.sound('revive_no') if self.revive_playlist else None
        if no is not None:
            no.set_gain(0.2)
            no.play()


class Narration:
    """PORT ADDITION (user request, 2026-10-03): a part of the Extra mode's story, read out as a line of the
    game's while the game goes on - as the original's challenges play Dr. Bastard's recorded lines
    (`ChallengeGameplayController.narrate`).

    It waits first (WAITING) for the lines that were already being said as it became due - `lines`, a list
    of the engine's sounds - and for the speech to finish reading what the game last announced; then it is
    due (DUE), and is handed to the speech (READING) at `read_at`, for `seconds`, the time the speech that
    reads it is taken to need.  A pause puts it back to DUE, to be read again from the start.  `after` is
    what comes once it has been read or skipped: None for a wave's story, whose wave then begins, and the
    completed screen for an epilogue."""

    WAITING, DUE, READING = 'waiting', 'due', 'reading'
    #: PORT ADDITION (user report, 2026-10-05): the time a part of the story is held for, over the time its
    #: reading is taken to need (ui/reading.reading_seconds): what is left after the pauses are counted -
    #: the slowest of the Extra mode's texts was still being read 8-9% past its time - so that a
    #: wave, or the completed screen after a closing story, does not come in over its last words
    MARGIN = 1.1

    def __init__(self, text: str, lines=(), after=None):
        self.text = text
        self.waiting_for = list(lines)
        self.after = after
        self.state = self.WAITING
        self.read_at = 0.0
        self.seconds = 0.0

    def skippable(self) -> bool:
        """Whether skipping the dialogue skips it: once it is being read, as a recorded line is skippable once
        it plays (`skipAllSkippableSounds` 0x1000a2e40 skips a sound in state 2) - and when a pause has put it
        back to be read again, so that the phone's Skip dialogue, which resumes and then skips, reaches it."""
        return self.state != self.WAITING


# ======================================================================================= controller
class GameplayController:
    """ADGameplayViewController (endless mode)."""
    uses_accessible_view_when_screen_reader = True

    def __init__(self, host=None):                        # -initWithNibName:bundle: 0x100056da0
        self.host = host                                  # the presenting screen
        self.weapon_update_timer = None
        self.update_timer = None
        self.stats_update_timer = None
        self.movement_on_last_frame = 0.0
        self.pan_array: list = []
        self.pause_view = None
        self.revive_view_controller = None
        self.turning_by_itself = 0                        # PORT ADDITION: The Magpie, 1 or -1 while it turns you
        self.nb_revives = 0
        self.announcer_value_on_entering_pause = False
        self.accessible_game_view = None
        self.paused = False
        self.held_sounds = None                           # PORT ADDITION: see hold_every_sound
        self.weapon_manager = None
        self.player = None
        self.death_overlay_visible = False
        self.score_label_text = '0'
        self.combo_label_text = ''
        self.skip_button_hidden = True
        self.timer_view_hidden = True
        self.timer_label_text = ''
        self.infinite_scroll_views = [InfiniteScrollView()]
        self.weapon_touch_area = WeaponTouchArea(allow_swipe=True)
        self.weapon_button = ButtonWithSwipe()
        self.shake_detector = None

    # --- setup -----------------------------------------------------------------------------------
    def init_ambiant_manager(self) -> None:               # 0x100057000
        AmbientManager.shared().start_with_random_ambient()
        engine = S3DEngine.engine()
        engine.set_reverb_room_size(1.5)
        engine.set_reverb_dampening(50.0)
        engine.set_reverb_volume(1.0)

    def ambiant_manager_did_activate_playlist(self) -> None:   # 0x100057128
        pass

    def init_brick_manager(self) -> None:                 # 0x10005712c
        self.nb_revives = 0
        bm = BrickManager.shared()
        bm.set_mode(1)
        MissionManager.shared().start_gameplay()
        bm.reset()
        bm.gameplay_view_controller = self
        bm.load_brick_chance_plist('brick_chance')
        bm.load_next_brick()

    def init_stats(self) -> None:                         # 0x1000572d4
        InGameStats.singleton().start_new_level('ENDLESS')
        self.score_label_text = '0'

    def init_ga_tracker_stats(self) -> None:              # 0x1000573e8 (analytics only)
        self.set_game_mode_dimension()

    def init_announcer(self) -> None:                     # 0x100057b0c (no caller in the binary)
        if GameParameters.shared().last_announcer_value():
            pl = S3DEngine.engine().play_list_with_name('announcer')
            if pl is not None:
                pl.activate()

    def view_did_load(self) -> None:                      # 0x100057c08
        self.init_weapon_manager()
        self.init_ambiant_manager()
        self.init_brick_manager()
        self.start_update_timers()
        self.init_button_mode()
        from .player import Player
        self.player = Player()
        self.skip_button_hidden = True
        self.timer_view_hidden = True
        if not isinstance(self, OpenerGameplayController):
            self.init_stats()
            self.init_ga_tracker_stats()
        self.update_score_view_with_animation(False)
        if self.host is not None and self.host.screen_reader_running():
            self.accessible_game_view = AccessibleGameView(self)
            self.accessible_game_view.weapon_manager = self.weapon_manager

    def set_game_mode_dimension(self) -> None:            # 0x100058ce4
        Tracker.shared().set_value_for_dimension('Endless mode', 'Game mode', 0, 0)

    def go_to_challenge_failed_screen(self) -> None:      # 0x100058d60
        pass

    def init_weapon_manager(self) -> None:                # 0x1000591cc
        from .weapon_manager import WeaponManager
        self.weapon_manager = WeaponManager.with_weapons_from_armory()
        self._attach_touch_objects()

    def _attach_touch_objects(self) -> None:
        self.weapon_touch_area.weapon_manager = self.weapon_manager
        self.weapon_touch_area.gameplay_view_controller = self
        self.weapon_button.weapon_manager = self.weapon_manager
        self.weapon_button.gameplay_view_controller = self

    def _weapons_dt(self) -> float:
        """FIX (Android, user request): the time the weapons have moved on by since their last update.

        The original ticks them with a fixed 0.01 s every hundredth of a second, and a timer that is late
        fires once, not once for each tick it missed.  A phone that takes longer than a hundredth over a pass
        of the game's loop therefore ran every gun slow - the minigun most of all, heard as lag and fewer
        bullets.  The real time since the last tick is used instead (at most 0.05 s, so a hitch is not
        a burst), which on a machine that keeps up is the same 0.01."""
        import time
        now = time.perf_counter()
        last, self._weapons_clock = getattr(self, '_weapons_clock', None), now
        if not system.ANDROID or last is None:
            return 0.01
        return min(max(now - last, 0.001), 0.05)

    def start_update_timers(self) -> None:                # 0x10005948c
        self._weapons_clock = None                        # PORT ADDITION: a pause is not time the guns moved on
        for t in (self.update_timer, self.weapon_update_timer, self.stats_update_timer):
            if t is not None:
                t.invalidate()
        loop = RunLoop.main()
        self.update_timer = loop.schedule_timer(0.05, self.update, True)
        self.weapon_update_timer = loop.schedule_timer(0.01, self.update_weapons, True)
        self.stats_update_timer = loop.schedule_timer(0.25, self.update_stats, True)

    def init_button_mode(self) -> None:                   # 0x10005a214
        pass                                              # ADButtonWithSwipe gameplayViewController links

    # --- timers ----------------------------------------------------------------------------------
    def update_stats(self) -> None:                       # 0x1000596d0
        if isinstance(self, OpenerGameplayController) or self.paused:
            return
        if BrickManager.shared().has_skippable_sounds_playing():
            return
        # PORT ADDITION: a wave held for a hand-over of weapons has not begun, and one waiting for its passers-by
        # is over (BrickManager.current_brick_is_cleared): neither is counted
        if self.holds_the_wave() or BrickManager.shared().waits_for_passers_by():
            return
        notify_stats('TIME_ELAPSED', 0.25)
        notify_stats('BRICK_TIME_ELAPSED', 0.25)
        cw = self.weapon_manager.current_weapon if self.weapon_manager is not None else None
        notify_stats('UPDATE_WEAPON_DATA', cw.name if cw is not None else None, False, False, False, False, 0.25)

    def update_weapons(self) -> None:                     # 0x100059a48
        dt = self._weapons_dt()
        self.weapon_touch_area.update(dt)
        if self.weapon_manager is not None:
            self.weapon_manager.update(dt)
        self.weapon_button.update(dt)
        self.update_score_view_with_animation(True)

    def update(self) -> None:                             # 0x100059b50
        if not isinstance(self, OpenerGameplayController):
            AmbientManager.shared().update(0.05)
        params = GameParameters.shared()
        mm = MotionManager.shared()
        if params.control_scheme == 1:
            mm.last_gyro_angle = mm.get_yaw_difference()
        elif params.control_scheme == 3:
            mm.last_tilt_angle = mm.get_tilt_angle()
        for v in list(self.infinite_scroll_views):
            v.update()
        self.turn_by_itself(0.05)                         # PORT ADDITION: The Magpie
        BrickManager.shared().update(0.05, hold_current=self.holds_the_wave())   # PORT ADDITION: see there
        if self.player is not None:
            self.player.update(0.05)
        if self.accessible_game_view is not None:
            self.accessible_game_view.update(0.05)
        self.update_score_view_with_animation(True)

    # --- The Magpie (PORT ADDITION, user request, 2026-10-05) -------------------------------------
    def start_turning_by_itself(self, direction: int) -> None:
        """The Magpie's catch: the player turns by themselves, `direction` 1 or -1, until they kill a Zombie
        (`stop_turning_by_itself`).  Already turning, they go on the way they were going."""
        if not self.turning_by_itself:
            self.turning_by_itself = direction
            log.info('The Magpie: turning by itself, %s', 'one way' if direction > 0 else 'the other')

    def stop_turning_by_itself(self) -> None:
        if self.turning_by_itself:
            log.info('The Magpie: a kill, and the turning stops')
        self.turning_by_itself = 0

    def turn_by_itself(self, dt: float) -> None:
        """One tick of it: the view - and the aim with it - turned by a sixth of a turn a second
        (modifiers.LOOSE_CONTROL_RADIANS_PER_SECOND), on top of whatever the player is turning by.  Not while
        paused or dead."""
        direction = self.turning_by_itself
        if (not direction or self.paused or getattr(self, 'death_overlay_visible', False)
                or self.player is None):
            return
        from .modifiers import LOOSE_CONTROL_RADIANS_PER_SECOND
        for v in list(self.infinite_scroll_views):
            v.turn_by(direction * LOOSE_CONTROL_RADIANS_PER_SECOND * dt)

    def holds_the_wave(self) -> bool:
        """PORT ADDITION (user request, 2026-10-03): whether the wave just loaded is kept from beginning while
        the game goes on round it.  The brick manager's `update:` 0x1000c37b0 is sent as always, told to hold
        that wave (`BrickManager.update`): its own update - its enemies' spawn times and their walk, its
        recordings, its power-up drop - and its own passers-by are held, and nothing else is.  So the turning,
        the ambience, the guns and a power-up in use go on, and so does what is left of the wave before: its
        last zombie dying and heard to the end, a power-up crate it dropped, and a car alarm, jukebox or
        machine, which stay from wave to wave.  (A cow of the wave before is gone by then: a challenge's wave
        waits for its cows, `BrickManager.current_brick_is_cleared`.  An enemy with no spawn time at all is
        spawned as its wave is made, `Brick.__init__`, and heard then, though it goes nowhere until the hold
        is over; every wave that hands over weapons gives each of its enemies and passers-by a time, and a wave
        that tells a part of the story spawns those only once it begins, `Brick.held_spawns`.)  Only an Extra
        wave asks for it - while it hands over a new set of weapons (`ChallengeGameplayController.arm`) and
        while its part of the story is read (`ChallengeGameplayController.narrate`) - and the challenge's
        clock does not run meanwhile either (`update_stats`).  Endless never holds a wave."""
        return False

    # --- input -----------------------------------------------------------------------------------
    def motion_ended(self, shake: bool) -> None:          # 0x10005a108
        if GameParameters.shared().button_mode:
            return
        if shake and self.weapon_manager is not None:
            self.weapon_manager.shoot_with_melee()

    def touches_move_detected(self, dx: float, just_started: bool) -> None:   # 0x10005a3e0
        if just_started:
            self.movement_on_last_frame = 0.0
        sens = GameParameters.shared().sensivity
        for v in list(self.infinite_scroll_views):
            v.player_swiped(f32(-(sens * dx)) - self.movement_on_last_frame)
        self.movement_on_last_frame = f32(-(sens * dx))

    def pan_detected(self, translation_x: float, began: bool) -> None:   # 0x10005a748
        if GameParameters.shared().control_scheme == 2:
            self.touches_move_detected(translation_x, began)

    def switch_weapon_button_pressed(self) -> None:       # 0x10005a86c
        self.weapon_manager.select_next_weapon()

    def reload_button_pressed(self) -> None:              # 0x10005a8d0
        self.weapon_manager.reload_gesture_down()

    def melee_button_pressed(self) -> None:               # 0x10005a934
        self.weapon_manager.shoot_with_melee()

    def power_up_button_pressed(self) -> None:            # 0x10005a998 (no button in the nib)
        self.weapon_manager.use_power_up()

    def player_killed_enemy(self, enemy, combo: int) -> None:   # 0x10005a9fc
        pass

    def player_did_a_critical_hit(self) -> None:          # 0x10005aa00
        pass

    def update_score_view_with_animation(self, animated: bool) -> None:   # 0x10005aa04 (labels only)
        stats = InGameStats.singleton()
        self.combo_label_text = f'x {stats.combo}'
        shown = _ns_int(self.score_label_text)
        score = stats.game_score
        if score == shown:
            return
        if not animated:
            self.score_label_text = self.formatted_score_from_int(score)
            return
        if not (score & 0xFFFFFFFF) > (shown & 0xFFFFFFFF):
            return
        diff = (score - shown) & 0xFFFFFFFF
        if not diff < 1001:
            self.score_label_text = self.formatted_score_from_int(shown + 1000)
            shown = _ns_int(self.score_label_text)
        diff = (score - shown) & 0xFFFFFFFF
        if not diff % 1000 < 101:
            self.score_label_text = self.formatted_score_from_int(shown + 100)
            shown = _ns_int(self.score_label_text)
        diff = (score - shown) & 0xFFFFFFFF
        if not diff % 100 < 11:
            self.score_label_text = self.formatted_score_from_int(shown + 10)
            shown = _ns_int(self.score_label_text)
        diff = (score - shown) & 0xFFFFFFFF
        if diff % 10 != 0:
            self.score_label_text = self.formatted_score_from_int(shown + 1)

    @staticmethod
    def formatted_score_from_int(value: int) -> str:      # 0x10005b448
        return str(int(value))

    def pause_button_touched(self) -> None:               # 0x10005b484
        self.pause_view = PauseController(self)
        self.pause_game()
        if self.host is not None:
            self.host.present_pause(self.pause_view)

    def skip_button_pressed(self) -> None:                # 0x10005b538
        pass

    def quit_gameplay_with_fail(self) -> None:            # 0x10005b53c
        self.go_to_score_screen()

    def go_to_score_screen(self) -> None:                 # 0x10005b54c
        from ..app import App
        self.kill_gameplay()
        App.delegate().go_to_game_over_endless()

    def pause_game(self) -> None:                         # 0x10005b5fc
        self.stop_timers()
        BrickManager.shared().pause_all_bricks()
        AmbientManager.shared().pause()
        if self.weapon_manager is not None:               # PORT ADDITION: see Weapon.pause
            self.weapon_manager.pause()
        if self.player is not None:                       # PORT ADDITION: see Player.pause
            self.player.pause()
        self.hold_every_sound()                           # PORT ADDITION: and everything else
        self.paused = True
        self.announcer_value_on_entering_pause = GameParameters.shared().last_announcer_value()

    def hold_every_sound(self) -> None:
        """PORT ADDITION (user request): whatever is still sounding when the game pauses is held with it.

        `pauseGame` 0x10005b5fc stops the timers and pauses the bricks and the ambience, and `resumeGame`
        0x10005b718 lets the same go; anything else that happens to be playing plays on.  The port pauses
        the weapons, the player's ringing ears and the power-up by name (`Weapon.pause`, `Player.pause`,
        `PowerUp.pause`); this is the net under them - a power-up's launch and explosions, a projectile, a
        shot's tail, any one-shot nobody thought of - so that a paused game is a paused game, and only the
        sounds held here are let go again (`S3DEngine.hold`).  The room keeps sounding, as it already did
        (`AmbientManager.room_sounds`).  A second pause keeps what the first is holding."""
        if self.held_sounds is None:
            self.held_sounds = S3DEngine.engine().hold(keep=AmbientManager.shared().room_sounds())

    def let_go_of_every_sound(self, stop: bool = False) -> None:
        """PORT ADDITION: the other half of `hold_every_sound` - play on, or, when the game is over rather
        than resumed (`kill_gameplay`), stop."""
        held, self.held_sounds = self.held_sounds, None
        if held is not None:
            held.drop() if stop else held.release()

    def resume_game(self) -> None:                        # 0x10005b718
        self.start_update_timers()
        BrickManager.shared().resume_all_bricks()
        AmbientManager.shared().resume()
        if self.weapon_manager is not None:               # PORT ADDITION: see Weapon.pause
            self.weapon_manager.resume()
        if self.player is not None:                       # PORT ADDITION: see Player.pause
            self.player.resume()
        self.let_go_of_every_sound()                      # PORT ADDITION: see hold_every_sound
        self.pause_view = None
        self.paused = False
        announcer = GameParameters.shared().last_announcer_value()
        if self.announcer_value_on_entering_pause == announcer:
            return
        pl = S3DEngine.engine().play_list_with_name('announcer')
        if pl is None:
            return
        if announcer:
            pl.activate()
        else:
            pl.deactivate()

    def show_death_overlay(self) -> None:                 # 0x10005b97c
        self.death_overlay_visible = True
        self.paused = True

    def show_revive_view(self) -> None:                   # 0x10005ba78
        AmbientManager.shared().stop_ambient()
        free = GameModifiers.shared().times('freeRevive')   # PORT DIVERGENCE: one a card, not one a hand
        cost = int(math.ldexp(1.0, self.nb_revives - free))
        self.revive_view_controller = ReviveController(cost, self.revive_skip_cost(cost))
        self.revive_view_controller.gameplay_view_controller = self
        self.revive_view_controller.view_did_load()
        self.revive_view_controller.view_will_appear()
        if self.host is not None:
            self.host.present_revive(self.revive_view_controller)
        self.nb_revives = self.nb_revives + 1

    def revive_skip_cost(self, cost: int):
        """PORT ADDITION: what skipping the wave costs instead of replaying it, or None where it is not
        offered - Endless, which goes on to the next wave whatever (see the challenge's)."""
        return None

    def revive(self, skip: bool = False) -> None:         # 0x10005bec0
        InGameStats.singleton().set_combo(10)
        self.update_score_view_with_animation(False)
        self.death_overlay_visible = False
        if self.host is not None:
            self.host.dismiss_revive()
        self.revive_view_controller = None
        self.paused = False
        if self.player is not None:                       # PORT ADDITION: the ringing ends (Player.reset_tinnitus)
            self.player.reset_tinnitus()
        BrickManager.shared().revive(skip)
        self.init_ambiant_manager()

    def game_over(self) -> None:                          # 0x10005c10c
        BrickManager.shared().game_over()

    def kill_gameplay(self) -> None:                      # 0x10005c170
        from .persistent_stats import PersistentStats
        self.stop_timers()
        self.let_go_of_every_sound(stop=True)             # PORT ADDITION: ended from a pause, held for nothing
        AmbientManager.shared().stop_ambient()

        def later():                                      # killGameplay_block_invoke 0x10005c770 (0.1 s)
            from .weapon_manager import WeaponManager
            AmbientManager.shared().stop_ambient()
            if self.weapon_manager is not None:
                self.weapon_manager.clean()
            BrickManager.shared().clean()
            # DIVERGENCE: -[ADWeaponManager clean] 0x1000aad50 cleans the power-up of the manager it is sent
            # to, and this block only sends it to the gameplay manager, whose own powerUp is always nil -
            # initPowerUp:/usePowerUp go through +sharedWeaponManager, which nothing ever cleans.  A power-up
            # still in hand at the end of a run was therefore waiting at the start of the next one.
            WeaponManager.shared().set_power_up(None)
        RunLoop.main().call_later(KILL_GAMEPLAY_CLEANUP, later)
        self.weapon_touch_area.gameplay_view_controller = None
        self.weapon_button.gameplay_view_controller = None
        if self.player is not None:
            self.player.dealloc()                         # setPlayer:nil releases the only reference
        self.player = None
        BrickManager.shared().gameplay_view_controller = None
        self.pan_array.clear()
        if GameParameters.shared().last_announcer_value():
            pl = S3DEngine.engine().play_list_with_name('announcer')
            if pl is not None:
                pl.deactivate()
        if not isinstance(self, OpenerGameplayController):
            stats = InGameStats.singleton()
            stats.end_level()
            stats.save_stats()
            PersistentStats.shared().save_score(stats.game_score)
            Tracker.shared().record_end_of_game_data()

    def stop_timers(self) -> None:                        # 0x10005c904
        for t in (self.update_timer, self.weapon_update_timer, self.stats_update_timer):
            if t is not None:
                t.invalidate()
        self.update_timer = None
        self.weapon_update_timer = None
        self.stats_update_timer = None


#: killGameplay_block_invoke 0x10005c770 runs this long after killGameplay returns, and only then are
#: the shared BrickManager and WeaponManager cleaned.  Anything that starts another game has to wait
#: for it, or the clean-up lands on the new game instead of the old one.
KILL_GAMEPLAY_CLEANUP = 0.1


def _ns_int(text) -> int:
    from ..platform.defaults import ns_int_value
    return ns_int_value(text)


def _arsenal(weapon_manager) -> list:
    """PORT ADDITION: the guns and the melee weapon a manager holds, by name and in order (see
    `ChallengeGameplayController.hand_over_weapons`)."""
    melee = weapon_manager.melee_weapon
    return [w.name for w in weapon_manager.weapons_array or []] + [melee.name if melee is not None else None]


# ============================================================================================ pause
class PauseController:
    """ADPauseViewController (the settings part lives in the settings screen port)."""

    def __init__(self, gameplay):
        self.gameplay_view_controller = gameplay          # weak

    def view_did_load(self) -> None:                      # 0x100055650
        pl = S3DEngine.engine().play_list_with_name('headphonesTest')
        if pl is not None:
            pl.activate()

    def quit_button_touched(self) -> None:                # 0x1000559c0 ("End Game")
        MissionManager.shared().end_gameplay()
        gvc = self.gameplay_view_controller

        def dismissed():                                  # quitButtonTouched:_block_invoke
            if gvc is not None:
                gvc.quit_gameplay_with_fail()
            self.gameplay_view_controller = None
        if gvc is not None and gvc.host is not None:
            gvc.host.dismiss_pause(dismissed)
        else:
            dismissed()
        pl = S3DEngine.engine().play_list_with_name('headphonesTest')
        if pl is not None:
            pl.deactivate()

    def challenge_dictionary(self):                       # PORT ADDITION
        """The challenge being played, or None in an endless game."""
        gvc = self.gameplay_view_controller
        return getattr(gvc, 'challenge_dictionary', None) if gvc is not None else None

    def restart_button_touched(self) -> None:             # PORT ADDITION
        """Start the same challenge again, without going out to the failed screen first.

        The original offers Resume and End Game and nothing else, so a challenge you had already lost -
        a missed time limit, an accuracy you could not recover - had to be played out to its end, or
        ended and then found again in the challenge list.  This tears the run down the way End Game does
        and starts the same dictionary again, which is what the failed screen's Try again does."""
        from ..app import App
        challenge = self.challenge_dictionary()
        if challenge is None:
            return
        MissionManager.shared().end_gameplay()
        gvc = self.gameplay_view_controller

        def dismissed():
            if gvc is not None:
                gvc.kill_gameplay()
            self.gameplay_view_controller = None
            # killGameplay 0x10005c170 does not finish when it returns: it defers the real clean-up by a
            # tenth of a second, and that block ends in BrickManager.clean() and WeaponManager.clean() -
            # both shared singletons, not the dying controller's own.  Starting the challenge straight
            # away meant the new arena was built first and emptied a tenth of a second later, leaving a
            # silent arena with nothing in it and a weapon that still fired.  The new game starts after
            # that block has run instead.
            RunLoop.main().call_later(KILL_GAMEPLAY_CLEANUP + 0.1,
                                      lambda: App.delegate().go_to_challenge_with_dict(challenge))
        if gvc is not None and gvc.host is not None:
            gvc.host.dismiss_pause(dismissed)
        else:
            dismissed()
        pl = S3DEngine.engine().play_list_with_name('headphonesTest')
        if pl is not None:
            pl.deactivate()

    def validate_button_pressed(self) -> None:            # 0x100055bbc ("Resume")
        gvc = self.gameplay_view_controller

        def dismissed():                                  # validateButtonPressed:_block_invoke
            if gvc is not None:
                gvc.resume_game()
        if gvc is not None and gvc.host is not None:
            gvc.host.dismiss_pause(dismissed)
        else:
            dismissed()
        pl = S3DEngine.engine().play_list_with_name('headphonesTest')
        if pl is not None:
            pl.deactivate()

    def back_button_pressed(self) -> None:                # 0x1000559ac
        self.validate_button_pressed()

    def can_skip_dialogue(self) -> bool:                  # PORT ADDITION (Android, user request)
        """Whether Dr. Bastard (or another skippable line) was talking when the game was paused."""
        gvc = self.gameplay_view_controller
        return gvc is not None and getattr(gvc, 'challenge_dictionary', None) is not None \
            and not getattr(gvc, 'skip_button_hidden', True)

    def skip_dialogue_touched(self) -> None:              # PORT ADDITION (Android, user request)
        """Resume, and skip the line that was playing.  On the phone the three-finger tap is only melee
        now, so skipping lives here, where no gesture of the fight can set it off by accident."""
        gvc = self.gameplay_view_controller
        self.validate_button_pressed()
        if gvc is not None:
            gvc.skip_button_pressed()


# ======================================================================================== challenge
class ChallengeGameplayController(GameplayController):
    def __init__(self, challenge_dictionary: dict, host=None):   # 0x1000da350
        super().__init__(host)
        self.challenge_dictionary = challenge_dictionary
        self.check_skip_button_counter = 0
        self.stories_told = set()                         # PORT ADDITION: see tell_story_if_due
        self.narration = None                             # PORT ADDITION: see narrate
        self.epilogue_told = False                        # PORT ADDITION: see go_to_score_screen
        self.arming = False                               # PORT ADDITION: see hand_over_weapons
        self.draw_left = 0.0
        self.weapons_after_story = False

    def view_did_load(self) -> None:                      # 0x1000da420
        self.init_challenge_modifiers()                   # PORT ADDITION: see below
        super().view_did_load()
        self.timer_view_hidden = False
        self.timer_label_text = '00:00'

    def init_challenge_modifiers(self) -> None:
        """PORT ADDITION (user request): the modifiers a challenge asks to be played with.

        The original has no such key, and none of its challenges wants one: a challenge is the same arena
        for everybody, which is the point of its stars.  Some of the port's own arenas are built on one -
        Stampede's speed, Iron Sights' narrow cone, Rust's short cylinder - so a challenge may name flags in
        a `Modifiers` list and get exactly those.

        Before anything is built: `Weapon.__init__` reads `lessBullets`, `goldenBullet` and the spread and
        head-shot modifiers when the weapon is made, and `Enemy.__init__` the speed and life ones when the
        enemy is made, and `super().view_did_load()` makes the weapons and the first wave.  Applied after
        it, as it first was, a start from the overview played Iron Sights with a revolver of the ordinary
        spread, Rust with a full cylinder and the first wave of Stampede at ordinary speed - while Restart
        from the pause menu, which does not reset the modifiers, played them as designed (2026-09-30).

        Exactly those, and nothing else: the modifiers are reset first.  Nothing resets them between the
        tarot screen (`ui/tarot.py`) and the next game-over screen, so a player who left an endless game
        without finishing it would otherwise carry their hand into the challenge - and a hand holding Black
        Cat (`noCritical`) would make this arena unwinnable through no fault of the player's.  A challenge
        with no `Modifiers` key is left alone, so the original's challenges behave as they always did.
        """
        wanted = (self.challenge_dictionary or {}).get('Modifiers')
        if not wanted:
            return
        from .modifiers import GameModifiers
        mods = GameModifiers.shared()
        mods.reset_modifiers()
        for flag in wanted:
            if not mods.apply_setter(str(flag), True):
                log.warning('challenge asks for a modifier that does not exist: %s', flag)

    def set_game_mode_dimension(self) -> None:            # 0x1000da6ac
        Tracker.shared().set_value_for_dimension('Challenge mode', 'Game mode', 0, 0)

    def skip_button_pressed(self) -> None:                # 0x1000da728
        if self.narration is not None and self.narration.skippable():   # PORT ADDITION: see narrate
            self.skip_narration()
            return
        BrickManager.shared().skip_skippable_sounds()

    def update(self) -> None:                             # 0x1000da794
        if self.arming:                                   # PORT ADDITION: see hand_over_weapons
            self.arming = self.arm()
        if not self.arming and self.narration is None:    # PORT ADDITION: see tell_story_if_due
            self.tell_story_if_due()
            if self.narration is None and self.weapons_after_story and not self.paused:
                self.weapons_after_story = False          # PORT ADDITION: see hand_over_weapons
                self.announce_weapons()
        if self.narration is not None:                    # PORT ADDITION: see narrate
            self.narrate()
            if self.player is None:                       # the epilogue has been read: the game is over
                return
        self.check_skip_button_counter = self.check_skip_button_counter + 1
        if self.check_skip_button_counter == 20:
            self.check_skip_button_counter = 0
            # PORT ADDITION: the story being read is a line that can be skipped (`narrate`)
            if (BrickManager.shared().has_skippable_sounds_playing()
                    or (self.narration is not None and self.narration.skippable())):
                self.skip_button_hidden = False
                if self.host is not None:
                    self.host.layout_changed()            # UIAccessibilityLayoutChangedNotification
            else:
                self.skip_button_hidden = True
        if not self.paused and not BrickManager.shared().has_skippable_sounds_playing():
            self.timer_label_text = self.time_string_from_seconds(int(InGameStats.singleton().challenge_time_elapsed))
        super().update()

    def update_stats(self) -> None:                       # 0x1000daa68
        super().update_stats()
        if self.paused or BrickManager.shared().has_skippable_sounds_playing():
            return
        # PORT ADDITION: see GameplayController.update_stats
        if self.holds_the_wave() or BrickManager.shared().waits_for_passers_by():
            return
        notify_stats('UPDATE_CHALLENGE_TIME_ELAPSED', 0.25)

    @staticmethod
    def time_string_from_seconds(seconds: int) -> str:    # 0x1000dab80
        minutes = int(seconds / 60)                       # C division
        rest = seconds - minutes * 60
        return f'{minutes}:{"0" if rest < 10 else ""}{rest}'

    def init_weapon_manager(self) -> None:                # 0x1000dac60
        from .weapon_manager import WeaponManager
        self.weapon_manager = WeaponManager.with_challenge_weapon_array(self.challenge_dictionary.get('weapons'))
        self._attach_touch_objects()

    #: PORT ADDITION: how many times a revive's price skipping the wave costs instead (user request, "5X or
    #: 10X" - ten, so that a skip stays the exception it is meant to be)
    REVIVE_SKIP_FACTOR = 10

    def tell_story_if_due(self) -> None:
        """PORT ADDITION (user request, 2026-10-01): a wave that carries `Story` - a part of the Extra mode's
        story, in text - has it read out as the wave begins, and the wave waits until it has been
        (`narrate`).  Each part is told as its wave begins - and again when a revive begins the wave over
        (user request, 2026-10-04: `BrickManager.retry_current_brick` forgets it was told).  With no screen
        to read it on (a run with none, as the referee plays) it is passed over.

        A wave that hands over a new set of weapons tells it first, and the set is read out and drawn once
        it has been (`hand_over_weapons`, `arm`; user request, 2026-10-05, the first wave and then every
        wave), so the order there is the story, the line, the pause, the draw and the gun's name, and the
        wave.  Until 2026-10-05 the set came first and the story after it (user request, 2026-10-03).

        It is read once what was already being said as the wave began has been heard out (user request,
        2026-10-02): the challenge's start clip, the announcer, a gun naming itself, the revive's answer and
        the weapons a wave hands over (`opening_lines`, `GameplayScreen.still_announcing`).  The start clip
        is `start_level_button`, which the overview's Play (`playButtonSound` 0x1000d8d50), the failed
        screen's Try again (0x1000720c4) and the pause menu's Restart play as they start the game: three
        seconds, two of them heard.  Nothing in the original waits for it - `goToChallengeWithDict:` loads
        the game at once and its timers run from `viewDidLoad` - but its challenges are written round it: not
        one of the thirty first waves has a zombie on a clock, each waiting on a line or on another zombie, and
        twenty-nine of them open with a second or two of nothing before the line.  The wave is held while
        the story waits, as while it is read (`holds_the_wave`)."""
        b = BrickManager.shared().current_brick()
        text = (b.brick_dictionary or {}).get('Story') if b is not None else None
        if not text or b.name in self.stories_told:
            return
        self.stories_told.add(b.name)
        if self.host is None:
            return
        self.narration = Narration(text, self.opening_lines())

    #: PORT ADDITION: the sounds, by name, that a story waits for when they are playing as its wave begins:
    #: the challenge's start clip, and the revive's answer when the revive skipped to the story's wave
    STORY_WAITS_FOR = ('start_level_button', 'revive_yes')

    def opening_lines(self) -> list:
        """PORT ADDITION: the sounds playing now that a part of the story waits for (`tell_story_if_due`):
        those in STORY_WAITS_FOR, anything of the announcer's, and a gun being drawn and naming itself
        (`Weapon.deploy`, when a wave hands over weapons).  Only what is playing as it becomes due: a gun
        switched to or an announcement made after that does not keep it waiting.  The wave's own recordings
        are never among them: the wave is held until the story has been read, and the last wave's were
        stopped as it loaded (`BrickManager.load_brick_with_name`)."""
        engine = S3DEngine.engine()
        announcer = engine.play_list_with_name('announcer')
        voices = set(announcer.agent_cache.values()) if announcer is not None else set()
        lines = []
        for sound in engine.playing_now():
            key = sound.key or ''
            if (sound in voices or key in self.STORY_WAITS_FOR
                    or (key.startswith('weapon_') and ('_deploy' in key or '_voice' in key))):
                lines.append(sound)
        return lines

    def narrate(self) -> None:
        """PORT ADDITION (user request, 2026-10-03): one tick of a part of the story being told
        (`Narration`), as the original's challenges tell theirs through Dr. Bastard's recordings.

        Those are a wave's own `Sounds`, mostly `blocker` and `skippable`, and the game does not stop for
        them: a recording plays for its length (`-[ADSound update:]` 0x1000b3914) while the player turns,
        switches, reloads and fires.  Its enemies wait on it through `spawn_after` - when it ends or is
        skipped (`finishSoundWithSkip:` 0x1000b4060), `soundOrEnemyWithNameWasDeactivated:withSkip:`
        0x1000c6bb0 starts what waits on it (`checkSpawnAfterKill:withSkip:` 0x1000a20ac) - and a wave is not
        cleared while a blocking one has not finished (`brickIsCleared` 0x1000a1658).  While a skippable one
        plays the Skip button shows (`update` 0x1000da794, `hasSkippableSoundsPlaying` 0x1000a2c98) and the
        challenge's clock stands still (`updateStats` 0x1000daa68).

        The story is that, in text.  Once what it waits for is over it is handed to the speech that reads
        what is said during a game (`Speech.speak_in_game`: the second speech while Use second speech is on),
        and the wave is held (`holds_the_wave`) - nothing of it spawns, moves or counts, and the challenge's
        clock stands still - until the time that speech is taken to need for it has passed: its words at the
        speech's own calibration (ui/reading.py).  The game itself runs all the while: turning, switching,
        reloading, firing, the ambience.  Skipping the dialogue stops the speech and begins the wave at once
        (`skip_narration`).  Until 2026-10-03 the story was a screen of its own, with a Continue button, and
        the game was paused under it; the user asked for it to be the original's lines in text instead ("just
        follow how the original challenge behave, just replace the audio thing with text")."""
        from ..platform.speech import Speech
        from ..ui.reading import in_game_speech, reading_seconds
        from .. import localization
        n = self.narration
        if self.paused or getattr(self, 'death_overlay_visible', False):
            return
        if n.state == n.WAITING:
            announcing = getattr(self.host, 'still_announcing', None)
            if any(s.playing for s in n.waiting_for) or (announcing is not None and announcing()):
                return
            n.state = n.DUE
        now = RunLoop.main().now()
        if n.state == n.DUE:
            Speech.shared().speak_in_game(n.text)
            n.read_at = now
            n.seconds = reading_seconds(localization.translate(n.text), in_game_speech()) * n.MARGIN
            n.state = n.READING
            return
        if now - n.read_at >= n.seconds:
            log.info('the story has been read')
            self.end_narration()

    def skip_narration(self) -> None:
        """PORT ADDITION: the dialogue skipped while a part of the story is read, by whatever skips the
        original's lines (`skip_button_pressed` 0x1000da728): the speech reading it stops, and the wave begins
        - or the completed screen comes - at once."""
        from ..platform.speech import Speech
        if self.narration.state == Narration.READING:
            Speech.shared().stop_in_game()
        log.info('the story was skipped')
        self.end_narration()

    def end_narration(self) -> None:
        n, self.narration = self.narration, None
        if n is not None and n.after is not None:
            n.after()

    def pause_game(self) -> None:
        """PORT ADDITION to `pauseGame` 0x10005b5fc: a part of the story being read stops with the game, and
        is read again from its start once the game runs again (`narrate`).  Speech cannot be paused where it
        is, and left to go on it read over the pause menu, or was cut by it; a pause held for any time loses
        the thread of a sentence anyway.  The wave stays held meanwhile."""
        super().pause_game()
        n = self.narration
        if n is not None and n.state == n.READING:
            from ..platform.speech import Speech
            Speech.shared().stop_in_game()
            n.state = n.DUE

    def allows_revive(self) -> bool:
        """PORT ADDITION (user request, 2026-10-01): an arena of the Extra mode offers the revive that Endless
        offers when the player dies - for diamonds, twice the price each time (`show_revive_view`) - or the
        failed screen, which is starting over.  The original's challenges end at the first death, as they
        always did.  The revive replays the wave died in (`BrickManager.retry_current_brick`); skipping it
        instead costs more (`revive_skip_cost`).  Every arena in `additions.CHAPTERS` is the Extra mode's, so
        a chapter added later has it too."""
        from .additions import chapter_of
        return chapter_of(self.get_challenge_id()) is not None

    def revive_skip_cost(self, cost: int):
        """PORT ADDITION: skipping the wave died in costs REVIVE_SKIP_FACTOR revives, and is offered only
        while a wave follows it - from the last, a skip would be the win itself, bought."""
        bm = BrickManager.shared()
        if not self.allows_revive() or bm.current_wave >= len(bm.brick_scenario or []):
            return None
        return cost * self.REVIVE_SKIP_FACTOR

    def hand_over_weapons(self, entries: list, announce: bool = True, first: bool = False) -> None:
        """PORT ADDITION (user request): a wave of a challenge that carries its own `Weapons` - a list in the
        form of the challenge's `weapons` - takes the player's weapons away and hands over those instead,
        so that one long arena can go from the guns of one chapter to the guns of the next.

        The original's challenges are armed once, for every wave.  Such a challenge lists in its own
        `weapons` every gun any of its waves hands over, because that list is what the overview checks
        (`hasWeaponForChallengeWithName:` 0x10001f868) and names when one is not bought; its first wave
        then carries the first set, in hand before anything is heard and read out after the wave's story,
        as every set is (below).

        The new guns are made before the old ones are let go: a gun of the same name shares its playlist
        (`Weapon.__init__` activates it, `dealloc` deactivates it), and activating one again is not
        immediate, so the old gun releases only the playlists nothing new is using.  A reload in progress
        and a held trigger are stopped first, as a switch of weapon stops them.  Every new gun arrives as
        `Weapon.__init__` makes it: a full clip of its capacity (after the modifiers that change it), the
        rounds the entry gives (`ammo`, or the original's unlimited 0x7fffffff), and at rest.

        The new set is read out first, and the first new gun drawn after it (user request, 2026-10-03):
        "New weapons: ..." is said, the game waits for the time the speech that reads it is taken to need
        (`GameplayScreen.announce`, ui/reading.py) and DRAW_PAUSE on top, and only then is the gun drawn
        as a switch draws it - its deploy sound, and its name if the announcer is on (`Weapon.deploy`).
        Drawn together, as they were, the draw and the name were heard over the list.  Until the draw the
        guns are holstered (`WeaponManager.holstered`): fire, tapped or held, melee, the switch and the
        reload do nothing, by key, gesture, Button mode, controller or shake.  And the wave waits until
        the drawn gun is ready, its switch's second over (`arm`, `holds_the_wave`): none of its enemies or
        passers-by is spawned or moves, none of its spawn times runs, and the challenge's clock stands still,
        while what is left of the wave before - a zombie still dying, a power-up crate - goes on, as does a
        power-up in use.  The wait is counted in the game's own ticks, so a pause holds it and it goes on
        after.  With no screen to read the line on (the referee) the gun is drawn at once, as before - the
        first wave's is in hand at once and not drawn (`first`), as it always was.

        A hand-over of the set already in hand says nothing and leaves the gun that was in hand there, fresh
        (user request, 2026-10-02): that is a revive or its skip giving the wave its weapons back
        (`BrickManager.hand_back_weapons`), which used to read out "New weapons" for the same wave while
        the announcer named the first gun.  The original's revive (`revive` 0x10005bec0, and the brick
        manager's 0x1000c7558) sends nothing to the weapons, and `deploy` 0x1000166e4 is sent by
        `selectNextWeapon` 0x1000a9e04 alone, so nothing is drawn or named as play resumes, and nothing
        waits.  A set that differs from the one in hand - a wave that changes the weapons, a skip to it
        included - is read out and drawn as above.

        The set is held back until the wave's story has been read (`weapons_after_story`; user request,
        2026-10-05): the story comes first, then the new weapons, then the zombies.  The first wave's was
        in hand at once with nothing said, so a player starting Reprise was never told what they had; and
        every later act read out its set and drew the gun, and then told its story over the gun in hand,
        which the user asked to go the other way round as well.  The set is in hand and holstered from the
        hand-over, the wave held (`holds_the_wave`), and once the story has been read or skipped it is
        read out and drawn as above (`announce_weapons`), the wave beginning when the gun is ready.  A
        wave with no story reads it out at once.  A revive into a wave that hands over a set gives back the
        set in hand and says nothing, as above."""
        from .weapon_manager import WeaponManager
        old = self.weapon_manager
        new = WeaponManager.with_challenge_weapon_array(entries)
        same = old is not None and _arsenal(old) == _arsenal(new)
        if same and old.current_weapon is not None:       # the gun in hand stays in hand
            for index, w in enumerate(new.weapons_array):
                if w.name == old.current_weapon.name:
                    new.current_weapon_index = index
                    new.set_current_weapon(w)
                    break
        if old is not None:
            kept = {id(w.playlist) for w in list(new.weapons_array) + [new.melee_weapon]
                    if w is not None and w.playlist is not None}
            for w in list(old.weapons_array or []) + [old.melee_weapon]:
                if w is None:
                    continue
                # a reload still sounding counts too: a death puts the gun back at rest (`stop_firing_now`)
                # and leaves its reload playing, which a revive into the same set then played on
                if w.state == 6 or w.state == 8 or w.reload_sound is not None:
                    w.interrupt_reload()
                w.stop_firing_now()
                if w.playlist is not None and id(w.playlist) in kept:
                    w.playlist = None                     # the new gun of that name plays through it
            old.clean()
        self.weapon_manager = new
        self._attach_touch_objects()
        if getattr(self, 'accessible_game_view', None) is not None:
            self.accessible_game_view.weapon_manager = new
        if not announce or same:
            return
        if self.host is None:                             # nowhere to read it out: drawn at once
            if not first:
                new.current_weapon.deploy()
            return
        new.holstered = True
        self.weapons_after_story = True                   # read out once the wave's story has been (`update`)

    def announce_weapons(self) -> None:
        """PORT ADDITION: the set in hand, holstered, read out - "New weapons: ..." - and its first gun drawn
        after it (`arm`), the wave held until it is ready (`hand_over_weapons`)."""
        from .weapon_manager import WeaponManager
        weapons = self.weapon_manager
        names = [WeaponManager.shared().display_name_for_item_with_name(w.name)
                 for w in list(weapons.weapons_array) + [weapons.melee_weapon] if w is not None]
        reading = self.host.announce('New weapons: %s' % ', '.join(names))
        self.draw_left = (reading or 0.0) + self.DRAW_PAUSE
        self.arming = True

    def weapons_now(self):
        """PORT ADDITION (user request, 2026-10-05): what a revive puts back - every gun's clip and spare rounds
        and which gun is in hand - as the wave beginning finds them (`BrickManager.load_next_brick`), a set it
        hands over included.  The game's own guns: `weapon_manager`, never the power-up's shared one."""
        weapons = self.weapon_manager
        if weapons is None:
            return None
        guns = [(w.name, w.bullets_in_clip, w.bullets_total) for w in weapons.weapons_array or []]
        return guns, (weapons.current_weapon.name if weapons.current_weapon is not None else None)

    def put_weapons_back(self, kept) -> None:
        """PORT ADDITION (user request, 2026-10-05): a revive's weapons as `weapons_now` kept them at the start of
        the wave died in: each gun's clip and spare rounds, and the gun that was in hand back in hand - without
        a word or a sound, no "New weapons", no draw and no name, as if the wave were simply begun again.  The
        guns are the fresh set the revive has just handed back (`BrickManager.hand_back_weapons`), at rest, so
        nothing of the death - a reload, a held trigger - carries over; only their rounds are put back."""
        weapons = self.weapon_manager
        if weapons is None or kept is None:
            return
        guns, in_hand = kept
        rounds = {}
        for name, clip, spare in guns:
            rounds.setdefault(name, (clip, spare))
        for index, w in enumerate(weapons.weapons_array or []):
            if w.name in rounds:
                w.bullets_in_clip, w.bullets_total = rounds[w.name]
            if w.name == in_hand:
                weapons.current_weapon_index = index
                weapons.set_current_weapon(w)

    #: PORT ADDITION (user request, 2026-10-03): the brief pause, in seconds, between the predicted end of
    #: "New weapons: ..." and the new gun being drawn (`hand_over_weapons`) - long enough to hear the list
    #: finish before the draw, short enough not to feel like waiting
    DRAW_PAUSE = 0.5

    def arm(self) -> bool:
        """PORT ADDITION: one tick of a hand-over in progress (`hand_over_weapons`), and whether it is still in
        progress - which holds the wave (`holds_the_wave`).  It counts down to the draw by the update timer's
        own 0.05 s, the time the wave is moved on by, so it stops while the game is paused; then the gun in
        hand is drawn, and the hand-over is over once it is ready - out of `Switching`, its draw's second,
        or whatever the player has done with it since."""
        weapons = self.weapon_manager
        if weapons is None or weapons.current_weapon is None:
            return False
        if weapons.holstered:
            self.draw_left -= 0.05
            if self.draw_left > 0.0:
                return True
            weapons.holstered = False
            weapons.current_weapon.deploy()
        return weapons.current_weapon.state == 1

    def holds_the_wave(self) -> bool:
        """PORT ADDITION: while a new set of weapons is being handed over (`arm`) or waits to be read out
        after the story (`hand_over_weapons`), and while a part of the story waits to be read or is read
        (`narrate`)."""
        return self.arming or self.weapons_after_story or self.narration is not None

    def init_brick_manager(self) -> None:                 # 0x1000daf74
        bm = BrickManager.shared()
        bm.reset()
        bm.set_mode(2)
        bm.gameplay_view_controller = self
        bm.load_brick_challenge_array(self.challenge_dictionary.get('bricks'))
        bm.load_next_brick()
        MissionManager.shared().start_gameplay()

    def init_ambiant_manager(self) -> None:               # 0x1000db158
        from ..platform.defaults import ns_float_value
        ambient = self.challenge_dictionary.get('ambient') or {}
        AmbientManager.shared().start_with_ambient(ambient.get('ambientPlaylist'),
                                                   ns_float_value(ambient.get('gain')))
        engine = S3DEngine.engine()
        engine.set_reverb_room_size(1.5)
        engine.set_reverb_dampening(50.0)
        engine.set_reverb_volume(1.0)
        AmbientManager.shared().gameplay_view_controller = self

    def ambiant_manager_did_activate_playlist(self) -> None:   # 0x1000db3e8
        AmbientManager.shared().start_base_sound()

    def init_stats(self) -> None:                         # 0x1000db44c
        InGameStats.singleton().start_new_level('CHALLENGE')

    def quit_gameplay_with_fail(self) -> None:            # 0x1000db4b8
        self.go_to_challenge_failed_screen()

    def go_to_challenge_failed_screen(self) -> None:      # 0x1000db4c8
        from ..app import App
        self.kill_gameplay()
        App.delegate().go_to_challenge_failed_with_dictionary(self.challenge_dictionary)

    def go_to_score_screen(self) -> None:                 # 0x1000db588
        # PORT ADDITION (user request, 2026-10-01): an arena of the Extra mode whose story ends with it
        # (`Epilogue`) tells that end once the last wave is won, before the completed screen - read out as a
        # part of the story is (`narrate`), where the original's challenges play a closing line as a last wave
        # of nothing but a blocking recording.  The completed screen comes once it has been read, or at once
        # when it is skipped.
        text = (self.challenge_dictionary or {}).get('Epilogue')
        if text and self.host is not None and not self.epilogue_told:
            self.epilogue_told = True
            self.narration = Narration(text, self.opening_lines(), after=self.go_to_score_screen)
            return
        InGameStats.singleton().force_complete_accuracy()
        self.go_to_challenge_completed_screen()

    def get_challenge_id(self):                           # 0x1000db604
        return self.challenge_dictionary.get('challenge_id')

    def go_to_challenge_completed_screen(self) -> None:   # 0x1000db628
        from ..app import App
        self.kill_gameplay()
        RunLoop.main().call_later(
            0.1, lambda: App.delegate().go_to_challenge_completed_with_dictionary(self.challenge_dictionary))

    def show_death_overlay(self) -> None:                 # 0x1000db788 (does not set paused)
        # DIVERGENCE (observed, not read): the original has [[UIApplication sharedApplication] delegate]
        # startMenuMusic:@"game_over_theme"] here, at 0x0db7f0, with nothing guarding it - and in a
        # recording of the real game no theme is heard when you die in a challenge, nor on the retry screen
        # that follows.  What is heard there is the retry screen's own sting, a random gameover_1..3
        # playlist started by -[ADChallengeFailedViewController viewDidLoad] 0x100071718 at 0x071c90, and
        # the menu theme only returns at the challenge selector.  Checked and ruled out as the cause:
        # startMenuMusic: 0x100082ca0 (its two early exits do not apply), killGameplay 0x10005c170 and its
        # 0.1 s block, playListWithName: 0x1000fc050 (cached, still returns the playlist once deactivated),
        # activate: 0x1000fe9c0 (only skips while already activating), the retry screen's own viewDidLoad,
        # and all three callers of stopMenuMusic.  The mechanism is unidentified - most likely something in
        # S3D's asynchronous activation on the device - so this follows the ear rather than the line.
        # Pressing End Challenge never reaches here at all, which is why that path was already silent.
        self.death_overlay_visible = True


# =========================================================================================== opener
class OpenerGameplayController(GameplayController):
    def __init__(self, host=None):                        # 0x100025334
        super().__init__(host)
        self.control_mode_label = None

    def view_did_load(self) -> None:                      # 0x1000253c0 (does not call super)
        self.init_ambiant_manager()
        self.init_brick_manager()
        self.start_update_timers()
        self.weapon_touch_area.gameplay_view_controller = self
        self.timer_view_hidden = True
        scheme = GameParameters.shared().control_scheme
        if scheme == 1:
            self.control_mode_label = 'Move the device'
        elif scheme == 2:
            self.control_mode_label = 'Swipe the screen'
        elif scheme == 3:
            self.control_mode_label = 'Tilt the device'
        else:
            self.control_mode_label = 'Swipe the screen or move the device'
        if self.host is not None and self.host.screen_reader_running():
            # the original announces "Triple tap to skip intro" after 2 s; the port names its key.  Skipping
            # before then leaves the opener behind, so the announcement checks it is still the screen: it
            # used to arrive over the main menu, where pressing Enter presses whatever is focused.
            # PORT ADDITION (user request, 2026-10-03): by the first speech, not the in-game one - the opener is
            # not a game being played, and the second speech reads only what is said in one.
            def announce_skip() -> None:
                from ..app import App
                from ..platform.speech import Speech
                if App.delegate().view_controller is self:
                    Speech.shared().speak(self.host.skip_intro_announcement())
            RunLoop.main().call_later(2.0, announce_skip)

    def handle_skip_for_accessible_users(self) -> None:   # 0x100025994
        self.skip_button_pressed()

    def init_ambiant_manager(self) -> None:               # 0x100025c38
        engine = S3DEngine.engine()
        engine.set_reverb_room_size(1.5)
        engine.set_reverb_dampening(50.0)
        engine.set_reverb_volume(1.0)

    def init_brick_manager(self) -> None:                 # 0x100025d20
        bm = BrickManager.shared()
        bm.set_mode(4)
        bm.reset()
        bm.gameplay_view_controller = self
        bm.load_brick_with_name('opener')

    def go_to_score_screen(self) -> None:                 # 0x100025e48
        from ..app import App
        self.kill_gameplay()
        App.delegate().go_to_main_menu()

    def skip_button_pressed(self) -> None:                # 0x100025ef8
        from ..app import App
        self.kill_gameplay()
        App.delegate().go_to_main_menu()
