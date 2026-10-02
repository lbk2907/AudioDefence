"""Audio Defence on Android: the game's main loop and its touch controls.

The Java side (MainActivity, Bridge) owns the screen, the sound output and the text-to-speech.  It calls
``run(home)`` on a thread of its own; this is the desktop port's main loop (audiodefence/__main__.py) with
pygame's events replaced by the touch events Bridge collects.

CONTROLS - the original's own, as it was played with VoiceOver running (the phone is held sideways and the
whole screen is the touch area; TalkBack is off and the game speaks for itself)

  In the menus, VoiceOver's gestures (the port's menus are its VoiceOver stand-in, as on the desktop)
    swipe right / left                          next / previous element
    swipe up / down                             VoiceOver's rotor: a slider up or down, or the next or
                                                previous tab or category where the screen has them
    double tap                                  activate (Enter)
    double tap and hold                         a row's second action (Shift + Enter)
    two-finger scrub, or the phone's Back       accessibilityPerformEscape: back (Escape)
    two-finger tap                              stop speaking
    two-finger swipe up / down                  read everything from the top / from the element on
    four-finger tap, top / bottom half          first / last element
  In a game, ADAccessibleGameView, which with VoiceOver running covers the screen: the touches go to its
  own handlers (touchesBegan / Moved / Ended), and its gesture recognizers are copied here
    touch                                       Gesture: tap = one shot, hold = continuous fire;
                                                Button: the four quarters of the screen (solveButtonPress)
    one-finger swipe up / down                  Gesture: next weapon / reload; Button: nothing
    three-finger tap                            Gesture: melee; Button: nothing
    a finger moved sideways                     turns, when aiming is Swipe (touchesMoved); Gyro and Tilt
                                                read the phone's sensors
    a shake                                     Gesture: melee (motionEnded:withEvent:)
    the Pause button, top middle of the screen  touch it and it is read; a double tap on it pauses
    the phone's Back                            pause (the desktop's Escape)
  In the intro (ADOpenerGameplayViewController, no ADAccessibleGameView)
    one-finger triple tap                       skip it (handleSkipForAccessibleUsers)
    a finger moved sideways                     turns, when aiming is Swipe (the weapon area's pan)
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
GAME_SWIPE = 48.0           # dp for the game area's swipe up or down (UISwipeGestureRecognizer)
TAP_MAX_MOVE = 24.0
DOUBLE_TAP_WINDOW = 0.40
LONG_PRESS = 0.65           # a double tap held this long is VoiceOver's double tap and hold
MULTI_TAP_WINDOW = 0.45
SCRUB_LEG = 30.0            # dp each stroke of a two-finger scrub has to cover
#: FIX (user request): how long a first finger in a game waits before it counts as a shot.  Fingers of a
#: three-finger tap land a few hundredths of a second apart; the first one used to fire at once, so melee
#: fired a shot too.  If a second finger lands inside this window, the touch waits to see what the
#: fingers are doing.
MULTI_FINGER_GRACE = 0.06

#: -[ADGameplayViewController pauseButton], nib object #143: x, y, width, height on the 568 x 320 screen.
#: With VoiceOver running it is the one thing brought in front of the game view (0x100058350).
PAUSE_BUTTON = (240.0, 1.0, 86.0, 31.0)
NIB_SIZE = (568.0, 320.0)


class _Finger:
    __slots__ = ('x0', 'y0', 't0', 'x', 'y', 'moved')

    def __init__(self, x, y, t):
        self.x0 = self.x = x
        self.y0 = self.y = y
        self.t0 = t
        self.moved = 0.0


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
    """The phone's touches, given to whatever the original gave them to.

    One gesture - from the first finger down to the last one up - belongs to one place, decided as it
    starts: a menu ('menu'), the game view ('game'), the Pause button in front of it ('pause') or the
    intro ('opener').  A game touch that began goes on to its end in the game view it began in, even if
    the pause screen has come up meanwhile, as a UITouch stays with its view."""

    def __init__(self, host, bridge):
        self.host = host
        self.b = bridge
        self.fingers: dict = {}
        self.kind = None
        self.gesture_max = 0                               # most fingers down in this gesture
        self.gesture_moved = 0.0
        self.gesture_t0 = 0.0
        self.gesture_ys: list = []                         # where each finger of the gesture came down
        self.multi_done = False                            # a two-finger gesture has already acted
        self.scrub = None                                  # [x, extreme, direction, strokes]
        self.pending_tap = None                            # (time, x, y, kind) waiting for a second tap
        self.second_tap = False                            # this touch is a double tap's second
        self.long_done = False
        self.taps: list = []                               # the intro: the times of the taps in a row
        self.pan_began = False                             # the intro: its pan has begun
        # the game view's touch: ADAccessibleGameView is not multipleTouchEnabled, so it is the first finger
        self.agv = None
        self.view_pid = None
        self.view_state = None                             # 'held' (not yet begun), 'began', None
        self.view_end_due = False                          # its finger lifted while others were down
        self.view_down = (0.0, 0.0)                        # where it came down
        self.target = None                                 # the GameplayScreen ('pause'), the opener's controller

    # ------------------------------------------------------------------------------------ helpers
    def _key(self, code, mod=0) -> None:
        import pygame
        for kind in (pygame.KEYDOWN, pygame.KEYUP):
            self.host.handle_event(pygame.event.Event(kind, key=code, mod=mod, unicode='', scancode=0))

    def _game(self):
        from .ui.gameplay_screen import GameplayScreen
        top = self.host.top()
        return top if isinstance(top, GameplayScreen) else None

    def _screen(self):
        return float(self.b.screenWidthDp()) or NIB_SIZE[0], float(self.b.screenHeightDp()) or NIB_SIZE[1]

    def _on_pause_button(self, x, y) -> bool:
        sw, sh = self._screen()
        px, py = x / sw * NIB_SIZE[0], y / sh * NIB_SIZE[1]
        bx, by, bw, bh = PAUSE_BUTTON
        return bx <= px < bx + bw and by <= py < by + bh

    # ------------------------------------------------------------------------------------ events
    def handle(self, kind, pid, x, y, now) -> None:
        if kind == DOWN:
            if not self.fingers:
                self._start(pid, x, y, now)
            self.fingers[pid] = _Finger(x, y, now)
            self.gesture_max = max(self.gesture_max, len(self.fingers))
            self.gesture_ys.append(y)
        elif kind == MOVE:
            f = self.fingers.get(pid)
            if f is None:
                return
            f.moved = max(f.moved, ((x - f.x0) ** 2 + (y - f.y0) ** 2) ** 0.5)
            f.x, f.y = x, y
            self.gesture_moved = max(self.gesture_moved, f.moved)
            if self.kind == 'game':
                self._move_game(pid, f)
            elif self.kind == 'opener':
                self._move_opener(f)
            elif self.kind == 'menu' and len(self.fingers) == 2:
                self._move_two()
        elif kind in (UP, CANCEL):
            f = self.fingers.pop(pid, None)
            if f is None:
                return
            f.x, f.y = x, y
            if self.kind == 'game' and pid == self.view_pid:
                if kind == CANCEL:
                    self._withdraw()
                elif self.gesture_max == 1:
                    self._end_view()
                else:
                    self.view_end_due = True               # UITapGestureRecognizer delaysTouchesEnded
            if not self.fingers:
                if kind == UP:
                    self._gesture_over(f, now)
                elif self.kind == 'game':
                    self._withdraw()
                self._reset()

    def _start(self, pid, x, y, now) -> None:
        self.gesture_max = 0
        self.gesture_moved = 0.0
        self.gesture_t0 = now
        self.gesture_ys = []
        self.multi_done = False
        self.scrub = None
        self.long_done = False
        p = self.pending_tap
        self.second_tap = (p is not None and now - p[0] <= DOUBLE_TAP_WINDOW
                           and abs(x - p[1]) < 60 and abs(y - p[2]) < 60)
        game = self._game()
        if game is None:
            self.kind = 'menu'
            return
        c = game.controller
        from .game.gameplay import OpenerGameplayController
        if isinstance(c, OpenerGameplayController):
            self.kind = 'opener'
            self.target = c
            return
        agv = game._agv()
        if agv is None or getattr(c, 'paused', False) or getattr(c, 'death_overlay_visible', False):
            self.kind = None
            return
        if self._on_pause_button(x, y):
            self.kind = 'pause'
            self.target = game
            if not (self.second_tap and p[3] == 'pause'):
                from .ui.accessibility import BUTTON, View
                game.speak(View('Pause', traits=BUTTON).spoken())     # VoiceOver reads what it touches
            return
        self.kind = 'game'
        self.agv = agv
        sw, sh = self._screen()
        agv.frame = (0.0, 0.0, sw, sh)                     # initWithFrame:[self view].frame - the screen
        self.view_pid = pid
        self.view_down = (x, y)
        self.view_state = 'held'                           # begun in frame(), unless more fingers come

    def _reset(self) -> None:
        self.kind = None
        self.gesture_max = 0
        self.agv = None
        self.target = None
        self.view_pid = None
        self.view_state = None
        self.view_end_due = False
        self.pan_began = False
        self.scrub = None

    # ------------------------------------------------------------------------------------ the game view
    def _view_alive(self) -> bool:
        """The game the touch began in is still there (under the pause screen, perhaps)."""
        from .ui.gameplay_screen import GameplayScreen
        screen = self.host.screen
        return isinstance(screen, GameplayScreen) and screen._agv() is self.agv

    def _begin_view(self) -> None:
        """touchesBegan:withEvent: 0x10008a404, where the finger came down."""
        if self.view_state == 'held' and self._view_alive():
            self.view_state = 'began'
            self.agv.touches_began(self.view_down)

    def _end_view(self) -> None:
        """touchesEnded:withEvent: 0x10008a50c (a quick tap that was still held begins first)."""
        self._begin_view()
        if self.view_state == 'began' and self._view_alive():
            self.agv.touches_ended()
        self.view_state = None

    def _withdraw(self) -> None:
        """A recognizer that cancelsTouchesInView took the touch: it never ends in the view.

        DIVERGENCE: ADAccessibleGameView does not implement touchesCancelled:withEvent:, so in the original
        a touch taken by the three-finger tap, or by a swipe under Button mode, left the view thinking the
        finger was still down - its trigger stuck until the next touch ended.  The touch is withdrawn the way
        the swipe's own handler withdraws it (handleSwipeGesture 0x10008a194): no shot, the gun stopped."""
        if self.view_state == 'began' and self._view_alive():
            self.agv.handle_swipe_gesture()
        self.view_state = None

    def _move_game(self, pid, f) -> None:
        if pid != self.view_pid:
            return                                         # the view only ever has its first finger
        if self.view_state == 'held' and len(self.fingers) == 1 and f.moved > TAP_MAX_MOVE / 2:
            self._begin_view()                             # a finger on the move is a swipe or a turn
        if self.view_state != 'began':
            return
        self.agv.touches_moved((f.x, f.y))                 # touchesMoved:withEvent: 0x10008a5a4
        dy, dx = f.y - f.y0, f.x - f.x0
        if self.gesture_max == 1 and abs(dy) > GAME_SWIPE and abs(dy) > 1.6 * abs(dx):
            # the swipe recognizers (initGestureRecognizers 0x100089f64: one touch, up or down); their
            # handlers do nothing under Button mode, but the recognizer has still taken the touch
            if dy < 0:
                self.agv.handle_swipe_up_gesture()
            else:
                self.agv.handle_swipe_down_gesture()
            self._withdraw()

    # ------------------------------------------------------------------------------------ the intro
    def _move_opener(self, f) -> None:
        """The weapon area's pan (ADButtonWithSwipe handlePan 0x100025054): it turns under Swipe aiming."""
        if len(self.fingers) != 1 or self.gesture_max != 1:
            return
        if not self.pan_began and f.moved <= TAP_MAX_MOVE / 2:
            return
        self.target.pan_detected(f.x - f.x0, not self.pan_began)
        self.pan_began = True

    # ------------------------------------------------------------------------------------ menus
    def _move_two(self) -> None:
        if self.multi_done:
            return
        fs = list(self.fingers.values())
        dys = [f.y - f.y0 for f in fs]
        dxs = [f.x - f.x0 for f in fs]
        if all(abs(dy) > SWIPE_MIN and abs(dy) > 1.5 * abs(dx) for dy, dx in zip(dys, dxs)) \
                and dys[0] * dys[1] > 0:
            self.multi_done = True
            self._read_all(from_top=dys[0] < 0)            # two-finger swipe up: from the top
            return
        # the two-finger scrub: back and forth, a Z - three strokes, each one turning the other way
        x = sum(f.x for f in fs) / 2
        s = self.scrub
        if s is None:
            self.scrub = [x, x, 0, 0]
            return
        s[0] = x
        if s[2] == 0:
            if abs(x - s[1]) >= SCRUB_LEG:
                s[2], s[1], s[3] = (1 if x > s[1] else -1), x, 1
            return
        if (x - s[1]) * s[2] > 0:
            s[1] = x                                       # still going the same way
        elif abs(x - s[1]) >= SCRUB_LEG:
            s[2], s[1], s[3] = -s[2], x, s[3] + 1
            if s[3] >= 3:
                self.multi_done = True
                import pygame
                self._key(pygame.K_ESCAPE)

    @staticmethod
    def _took_over(top) -> None:
        """PORT ADDITION: stopping the speech or reading the screen again is the player reading it for
        themselves, and a screen that would go on by itself waits for them instead once it is told
        (ui/gameplay_screen.StoryScreen).  Swipes and taps tell it as the keys they stand for; these two
        gestures are not keys, so they tell it here."""
        took_over = getattr(top, 'player_took_over', None)
        if took_over is not None:
            took_over()

    def _read_all(self, from_top: bool) -> None:
        """VoiceOver's two-finger swipe: read the screen from the top, or on from the element in focus."""
        from .ui.accessibility import AccessibleScreen
        from .ui.screens import joined
        top = self.host.top()
        if not isinstance(top, AccessibleScreen):
            return
        self._took_over(top)
        elements = top.elements()
        if not from_top and top.focus in elements:
            elements = elements[elements.index(top.focus):]
        if elements:
            top.speak(joined(e.spoken() for e in elements))

    def _menu_one_up(self, f, now) -> None:
        if self.long_done:
            return
        dx, dy = f.x - f.x0, f.y - f.y0
        import pygame
        if (dx * dx + dy * dy) ** 0.5 >= SWIPE_MIN:
            if abs(dx) >= abs(dy):
                self._key(pygame.K_RIGHT if dx > 0 else pygame.K_LEFT)
            else:
                self._key(pygame.K_DOWN if dy > 0 else pygame.K_UP)
            self.pending_tap = None
            return
        if f.moved > TAP_MAX_MOVE:
            return
        if self.second_tap and self.pending_tap is not None and self.pending_tap[3] == 'menu':
            self.pending_tap = None
            self._key(pygame.K_RETURN)                      # double tap: Enter
        else:
            self.pending_tap = (now, f.x, f.y, 'menu')

    # ------------------------------------------------------------------------------------ the end
    def _gesture_over(self, f, now) -> None:
        quick = now - self.gesture_t0 <= MULTI_TAP_WINDOW and self.gesture_moved <= TAP_MAX_MOVE * 2
        if self.kind == 'game':
            if self.gesture_max == 3 and quick:
                # the three-finger tap (tripleTap: three touches, cancelsTouchesInView) -> handleTripleTap
                # 0x10008acf8, which does nothing under Button mode
                self._withdraw()
                self.agv.handle_triple_tap()
            elif self.view_end_due:
                self._end_view()                           # not a three-finger tap: the touch ends as one
        elif self.kind == 'pause':
            if self.gesture_max == 1 and f.moved <= TAP_MAX_MOVE:
                p = self.pending_tap
                if self.second_tap and p is not None and p[3] == 'pause':
                    self.pending_tap = None
                    self.target.press('pause', None)       # pauseButtonTouched: 0x10005b484
                else:
                    self.pending_tap = (now, f.x, f.y, 'pause')
        elif self.kind == 'opener':
            if self.gesture_max == 1 and f.moved <= TAP_MAX_MOVE:
                if not (self.taps and now - self.taps[-1] <= DOUBLE_TAP_WINDOW):
                    self.taps = []
                self.taps.append(now)
                if len(self.taps) == 3:                    # numberOfTapsRequired 3 (viewDidLoad 0x1000253c0)
                    self.taps = []
                    self.target.handle_skip_for_accessible_users()
        elif self.kind == 'menu':
            if self.gesture_max == 1:
                self._menu_one_up(f, now)
            elif quick and not self.multi_done:
                if self.gesture_max == 2:                  # VoiceOver's two-finger tap: stop speaking
                    from .platform.speech import Speech
                    Speech.shared().stop()
                    self._took_over(self.host.top())
                elif self.gesture_max == 4:                # four-finger tap: first or last element
                    import pygame
                    y = sum(self.gesture_ys) / len(self.gesture_ys)
                    self._key(pygame.K_HOME if y < self._screen()[1] / 2 else pygame.K_END)

    # ------------------------------------------------------------------------------------ per pass
    def frame(self, now) -> None:
        if self.kind == 'game' and self.view_state == 'held' and self.view_pid in self.fingers:
            f = self.fingers[self.view_pid]
            if self.gesture_max == 1:
                if now - f.t0 >= MULTI_FINGER_GRACE:
                    self._begin_view()
            elif self.gesture_max > 3 or now - self.gesture_t0 > MULTI_TAP_WINDOW \
                    or self.gesture_moved > TAP_MAX_MOVE * 2:
                self._begin_view()                         # no three-finger tap: the touch is the view's
        if self.kind == 'menu' and self.second_tap and not self.long_done and len(self.fingers) == 1 \
                and self.gesture_max == 1:
            f = next(iter(self.fingers.values()))
            if now - f.t0 >= LONG_PRESS and f.moved <= TAP_MAX_MOVE:
                self.long_done = True                      # VoiceOver's double tap and hold
                self.pending_tap = None
                import pygame
                self._key(pygame.K_RETURN, pygame.KMOD_SHIFT)        # a row's second action
        if self.pending_tap is not None and now - self.pending_tap[0] > DOUBLE_TAP_WINDOW \
                and not self.fingers:
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
    params = GameParameters.shared()
    GameParameters.screen_reader_running = Speech.shared().screen_reader_running()
    Speech.shared().choice = params.speech_output()
    params.forget_saved_voice()                          # PORT ADDITION (user request): each engine's own voice
    Speech.shared().configure_sapi(**params.sapi_config())
    Speech.shared().set_engine(params.speech_engine())   # PORT ADDITION (user request): Settings > Speech

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
            if params.settle_speech_engine():             # PORT ADDITION: the speech engine has started
                Speech.shared().speak("The speech engine chosen in Settings could not be started, so the phone's "
                                      'default engine speaks instead.', False)
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
