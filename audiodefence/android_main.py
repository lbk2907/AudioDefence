"""Audio Defence on Android: the game's main loop and its touch controls.

The Java side (MainActivity, Bridge) owns the screen, the sound output and the text-to-speech.  It calls
``run(home)`` on a thread of its own; this is the desktop port's main loop (audiodefence/__main__.py) with
pygame's events replaced by the touch events Bridge collects.

CONTROLS (Android has no keyboard; the game is played with one to three fingers on the screen)

  In the menus                                  (the accessible screens of the original, as on the desktop)
    swipe right / left / up / down              the arrow keys: move through the screen, change tab
                                                (Settings > Miscellaneous > Menu layout picks which pair moves)
    double tap                                  Enter: press the button
    touch and hold                              Shift + Enter: a row's second action
    two-finger tap                              Escape: back
    two-finger swipe up / down                  first / last item
  In a game (Gesture mode, as the original's VoiceOver mode)
    touch                                       tap = one shot, hold = continuous fire
    swipe up / swipe down                       next weapon / reload
    swipe left / right                          turn (Swipe aiming); Gyro and Tilt aiming use the phone's sensors
    two-finger tap                              pause
    three-finger tap                            melee (in the intro: skip)
    Skip dialogue, on the pause screen          skip a line of Dr. Bastard's
    double tap (in the intro)                   skip the intro
  In a game (Button mode)
    the screen is four corners: top right fires, top left is melee, bottom left changes weapon, bottom
    right reloads; the other gestures work as above.
"""
from __future__ import annotations

import logging
import os
import sys
import time

log = logging.getLogger('android')

# event types from Bridge.pollEvents
DOWN, MOVE, UP, CANCEL = 0, 1, 2, 3
PAUSED, RESUMED, BACK, MENU_KEY = 10, 11, 20, 21

SWIPE_MIN = 56.0            # dp a finger has to travel to be a swipe in a menu
GAME_SWIPE = 48.0           # dp for a swipe up or down in a game
GAME_SWIPE_INTENT = 18.0    # dp of mostly-vertical travel after which a touch is no longer a shot
TAP_MAX_MOVE = 24.0
DOUBLE_TAP_WINDOW = 0.40
LONG_PRESS = 0.65
MULTI_TAP_WINDOW = 0.45
#: FIX (user request): how long a first finger in a game waits before it counts as a shot.  Fingers of a
#: two- or three-finger tap land a few hundredths of a second apart; the first one used to fire at once, so
#: pausing and melee fired a shot too.  If a second finger lands inside this window, no shot is fired.
MULTI_FINGER_GRACE = 0.06


class _Finger:
    __slots__ = ('x0', 'y0', 't0', 'x', 'y', 'moved', 'swiped')

    def __init__(self, x, y, t):
        self.x0 = self.x = x
        self.y0 = self.y = y
        self.t0 = t
        self.moved = 0.0
        self.swiped = False


class PhoneMotion:
    """MotionManager's source on a phone: the gyroscope (Gyro aiming) and the tilt (Tilt aiming)."""

    def __init__(self, bridge):
        self.b = bridge
        self.direction = 0

    def set_direction(self, direction: int) -> None:      # the screen's stick/keys do not turn a phone
        self.direction = direction

    def take_yaw_difference(self) -> float:
        return float(self.b.takeYaw())

    def tilt_angle(self) -> float:
        return float(self.b.tiltAngle())


class TouchInput:
    def __init__(self, host, bridge):
        self.host = host
        self.b = bridge
        self.fingers: dict = {}
        self.gesture_max = 0                               # most fingers down in this gesture
        self.gesture_moved = 0.0
        self.gesture_t0 = 0.0
        self.pending_tap = None                            # (time, x, y) waiting for a second tap
        self.long_done = False
        self.in_game_finger = None
        self.game_swiped = False
        self.multi_swipe_done = False
        self.held_down = None                              # (pid, x, y, t): a game touch not yet begun

    # ------------------------------------------------------------------------------------ helpers
    def _key(self, code, mod=0) -> None:
        import pygame
        for kind in (pygame.KEYDOWN, pygame.KEYUP):
            self.host.handle_event(pygame.event.Event(kind, key=code, mod=mod, unicode='', scancode=0))

    def _game(self):
        from .ui.gameplay_screen import GameplayScreen
        top = self.host.top()
        return top if isinstance(top, GameplayScreen) else None

    # ------------------------------------------------------------------------------------ events
    def handle(self, kind, pid, x, y, now) -> None:
        if kind == DOWN:
            self.fingers[pid] = _Finger(x, y, now)
            if len(self.fingers) == 1:
                self.gesture_max = 1
                self.gesture_moved = 0.0
                self.gesture_t0 = now
                self.long_done = False
                self.multi_swipe_done = False
                self._down_first(pid, x, y, now)
            else:
                self.gesture_max = max(self.gesture_max, len(self.fingers))
                self._abort_first_finger(pid)
        elif kind == MOVE:
            f = self.fingers.get(pid)
            if f is None:
                return
            f.moved = max(f.moved, ((x - f.x0) ** 2 + (y - f.y0) ** 2) ** 0.5)
            f.x, f.y = x, y
            self.gesture_moved = max(self.gesture_moved, f.moved)
            if len(self.fingers) == 1:
                self._move_first(pid, f, now)
            elif len(self.fingers) == 2:
                self._move_two(now)
        elif kind in (UP, CANCEL):
            f = self.fingers.pop(pid, None)
            if f is None:
                return
            f.x, f.y = x, y
            if kind == CANCEL:
                self._cancel(pid, f)
            elif not self.fingers and self.gesture_max == 1:
                self._up_first(pid, f, now)
            if not self.fingers:
                if kind == UP and self.gesture_max >= 2 and not self.multi_swipe_done:
                    self._multi_tap(now)
                self.gesture_max = 0
                self.in_game_finger = None

    # ------------------------------------------------------------------------------------ one finger
    def _down_first(self, pid, x, y, now) -> None:
        game = self._game()
        if game is None:
            return
        agv = game._agv()
        c = game.controller
        if agv is None or getattr(c, 'paused', False) or getattr(c, 'death_overlay_visible', False):
            return
        from .game.gameplay import OpenerGameplayController
        if isinstance(c, OpenerGameplayController):
            return
        self.game_swiped = False
        self.held_down = (pid, x, y, now)                  # begun in frame(), unless more fingers come

    def _begin_held(self) -> None:
        """The held first finger is a one-finger touch after all: it begins now, where it came down."""
        h, self.held_down = self.held_down, None
        if h is None:
            return
        game = self._game()
        agv = game._agv() if game is not None else None
        if agv is None:
            return
        self.in_game_finger = h[0]
        agv.touches_began(self._scaled(agv, h[1], h[2]))

    def _scaled(self, agv, x, y):
        w, h = agv.frame[2], agv.frame[3]
        sw, sh = self.b.screenWidthDp(), self.b.screenHeightDp()
        return (x / sw * w if sw else x, y / sh * h if sh else y)

    def _abort_first_finger(self, pid) -> None:
        """A second finger came down: whatever the first began in a game is over."""
        self.held_down = None                              # it never began: no shot
        game = self._game()
        if game is not None and self.in_game_finger is not None:
            agv = game._agv()
            if agv is not None:
                agv.touch_canceled()
            self.in_game_finger = None

    def _move_first(self, pid, f, now) -> None:
        game = self._game()
        if game is None:
            return
        if self.held_down is not None and self.held_down[0] == pid and f.moved > TAP_MAX_MOVE / 2:
            self._begin_held()                             # a finger on the move is a swipe or a turn
        if self.in_game_finger != pid:
            return
        agv = game._agv()
        if agv is None:
            return
        agv.touches_moved(self._scaled(agv, f.x, f.y))
        dy = f.y - f.y0
        dx = f.x - f.x0
        vertical = abs(dy) > 1.6 * abs(dx)
        if vertical and abs(dy) > GAME_SWIPE_INTENT:
            # a finger on its way up or down is a swipe being made, not a shot: without this, a swipe slower
            # than the 0.2 s after which holding starts continuous fire fired the gun before it changed weapon
            agv.has_swiped = True
        if not self.game_swiped and abs(dy) > GAME_SWIPE and vertical:
            self.game_swiped = True
            if dy < 0:
                agv.handle_swipe_up_gesture()
            else:
                agv.handle_swipe_down_gesture()
            # the swipe has taken this finger, as the swipe gesture takes the touch on iOS: nothing it does
            # from here to when it is lifted reaches the game - lifting it used to fire a single shot
            self.in_game_finger = None

    def _up_first(self, pid, f, now) -> None:
        game = self._game()
        if game is not None:
            self._up_in_game(game, pid, f, now)
            return
        dx, dy = f.x - f.x0, f.y - f.y0
        dist = (dx * dx + dy * dy) ** 0.5
        if self.long_done:
            return
        if dist >= SWIPE_MIN:
            import pygame
            if abs(dx) >= abs(dy):
                self._key(pygame.K_RIGHT if dx > 0 else pygame.K_LEFT)
            else:
                self._key(pygame.K_DOWN if dy > 0 else pygame.K_UP)
            self.pending_tap = None
            return
        if f.moved > TAP_MAX_MOVE:
            return
        p = self.pending_tap
        if p is not None and now - p[0] <= DOUBLE_TAP_WINDOW and abs(f.x - p[1]) < 60 and abs(f.y - p[2]) < 60:
            self.pending_tap = None
            import pygame
            self._key(pygame.K_RETURN)                      # double tap: Enter
        else:
            self.pending_tap = (now, f.x, f.y)

    def _up_in_game(self, game, pid, f, now) -> None:
        if self.held_down is not None and self.held_down[0] == pid:
            self._begin_held()                             # a quick tap: the shot, then its release
        agv = game._agv()
        was = self.in_game_finger == pid
        self.in_game_finger = None
        if agv is not None and was:
            agv.touches_ended()
            return
        # the intro takes no shots, so a double tap there skips it (a three-finger tap does too)
        from .game.gameplay import OpenerGameplayController
        if isinstance(game.controller, OpenerGameplayController) and f.moved <= TAP_MAX_MOVE:
            p = self.pending_tap
            if p is not None and now - p[0] <= DOUBLE_TAP_WINDOW:
                self.pending_tap = None
                import pygame
                self._key(pygame.K_RETURN)                  # the Skip key
            else:
                self.pending_tap = (now, f.x, f.y)

    def _cancel(self, pid, f) -> None:
        if self.held_down is not None and self.held_down[0] == pid:
            self.held_down = None
        game = self._game()
        if game is not None and self.in_game_finger == pid:
            agv = game._agv()
            if agv is not None:
                agv.touch_canceled()
            self.in_game_finger = None

    # ------------------------------------------------------------------------------------ more fingers
    def _move_two(self, now) -> None:
        if self.multi_swipe_done or len(self.fingers) != 2:
            return
        fs = list(self.fingers.values())
        dys = [f.y - f.y0 for f in fs]
        dxs = [f.x - f.x0 for f in fs]
        if all(abs(dy) > SWIPE_MIN and abs(dy) > 1.5 * abs(dx) for dy, dx in zip(dys, dxs)) \
                and dys[0] * dys[1] > 0:
            self.multi_swipe_done = True
            if self._game() is None:
                import pygame
                self._key(pygame.K_HOME if dys[0] < 0 else pygame.K_END)

    def _triple(self, game) -> None:
        """The three-finger tap: melee.  (It skips the intro, where there is no melee.)

        CHANGED (user request): it used to skip Dr. Bastard's lines in a challenge instead of swinging, so
        melee did nothing while he talked.  Skipping a line is now Skip dialogue, first on the pause screen
        (two-finger tap)."""
        from .game.gameplay import OpenerGameplayController
        c = game.controller
        if isinstance(c, OpenerGameplayController):
            import pygame
            self._key(pygame.K_RETURN)                       # the Skip key
            return
        agv = game._agv()
        if agv is not None:
            agv.handle_triple_tap()

    def _multi_tap(self, now) -> None:
        if self.gesture_moved > TAP_MAX_MOVE * 2 or now - self.gesture_t0 > MULTI_TAP_WINDOW:
            return
        import pygame
        if self.gesture_max == 2:
            self._key(pygame.K_ESCAPE)                       # back / pause
        elif self.gesture_max >= 3:
            game = self._game()
            if game is not None:
                self._triple(game)                           # three fingers: melee
            else:
                self._key(pygame.K_ESCAPE)

    # ------------------------------------------------------------------------------------ per pass
    def frame(self, now) -> None:
        if self.held_down is not None and now - self.held_down[3] >= MULTI_FINGER_GRACE \
                and len(self.fingers) == 1:
            self._begin_held()
        if len(self.fingers) == 1 and self._game() is None and not self.long_done and self.gesture_max == 1:
            f = next(iter(self.fingers.values()))
            if now - f.t0 >= LONG_PRESS and f.moved <= TAP_MAX_MOVE:
                self.long_done = True
                import pygame
                self._key(pygame.K_RETURN, pygame.KMOD_SHIFT)        # a row's second action
        if self.pending_tap is not None and now - self.pending_tap[0] > DOUBLE_TAP_WINDOW:
            self.pending_tap = None


def _setup_logging(home: str, level: str = 'info') -> None:
    from .paths import user_dir
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(logging.FileHandler(os.path.join(user_dir(), 'audiodefence.log'), 'w', encoding='utf-8'))
    except OSError:
        pass
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format='%(asctime)s %(name)s %(levelname)s %(message)s', handlers=handlers, force=True)


def run(home: str, fake: bool = False) -> int:
    """Called by MainActivity on a thread of its own, once the game's data is in place."""
    os.environ['AUDIODEFENCE_ANDROID'] = '1'
    os.environ['AUDIODEFENCE_HOME'] = home
    _setup_logging(home)
    log.info('Audio Defence for Android starting; data in %s', home)
    from . import paths
    log.info('game data: %s', paths.BUNDLE)

    from .app import App
    from .game.parameters import GameParameters
    from .platform.jbridge import bridge
    from .platform.runloop import RunLoop
    from .platform.speech import Speech
    from .s3d.engine import S3DEngine
    from .ui.host import ScreenManager

    b = bridge()
    try:                                                   # PORT ADDITION: Settings > Controls
        b.setShakeSensitivity(int(GameParameters.shared().shake_sensitivity()))
    except Exception:
        log.exception('could not set the shake sensitivity')
    GameParameters.screen_reader_running = Speech.shared().screen_reader_running()
    Speech.shared().choice = GameParameters.shared().speech_output()
    Speech.shared().configure_sapi(**GameParameters.shared().sapi_config())

    host = ScreenManager()
    running = [True]
    host.request_quit = lambda: running.__setitem__(0, False)
    app = App.delegate()
    app.host = host
    app.application_did_finish_launching()

    touch = TouchInput(host, b)
    loop = RunLoop.main()
    engine = S3DEngine.engine()
    motion_screen = [None]
    try:
        while running[0] and not b.shouldQuit():
            events = b.pollEvents()
            n = len(events)
            now = time.perf_counter()
            for i in range(0, n - 4, 5):
                kind = int(events[i])
                if kind in (DOWN, MOVE, UP, CANCEL):
                    touch.handle(kind, int(events[i + 1]), float(events[i + 2]), float(events[i + 3]), now)
                elif kind == PAUSED:
                    app.application_will_resign_active()
                elif kind == BACK:
                    import pygame
                    touch._key(pygame.K_ESCAPE)
            loop.run_once()
            engine.pump()
            host.frame()
            top = host.top()
            from .ui.gameplay_screen import GameplayScreen
            if isinstance(top, GameplayScreen) and top is not motion_screen[0]:
                top.motion = PhoneMotion(b)              # Gyro and Tilt aiming read the phone
                from .game.gameplay import MotionManager
                MotionManager.shared().source = top.motion
                motion_screen[0] = top
            touch.frame(now)
            shook = b.takeShake()
            if shook and not isinstance(top, GameplayScreen):
                # PORT ADDITION: on the Settings screen a shake is said, to try the sensitivity out
                from .ui.settings import SettingsScreen, PauseScreen
                if isinstance(top, SettingsScreen) and not isinstance(top, PauseScreen):
                    top.speak('Shake')
            if shook and isinstance(top, GameplayScreen):
                c = top.controller
                from .game.gameplay import OpenerGameplayController
                if not (getattr(c, 'paused', False) or getattr(c, 'death_overlay_visible', False)
                        or isinstance(c, OpenerGameplayController)):
                    c.motion_ended(True)                     # a shake swings the melee weapon (not in Button mode)
            wait = min(loop.next_deadline() - loop.now(), 0.004)
            if wait > 0:
                time.sleep(wait)
    except Exception:
        log.exception('the game stopped')
        raise
    finally:
        log.info('shutting down')
        try:
            engine.stop_all()
        except Exception:
            log.exception('could not stop the sounds')
        try:
            Speech.shared().shutdown()
        except Exception:
            pass
        b.gameEnded()
    return 0
