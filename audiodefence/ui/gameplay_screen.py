"""The gameplay screen: keyboard input for GameplayController and its pause / revive overlays.

PORT INPUT MAPPING (the original is touch and motion driven).  The keys live in platform/keymap.py and can
be rebound in Settings -> Keyboard; these are the defaults:

    Space (tap / hold)   touch the game area: tap = single shot, hold = continuous fire
    Left / Right Ctrl    melee   (gesture mode: the triple tap; button mode: the melee corner)
    Up arrow             next weapon (gesture mode: swipe up; button mode: the switch corner)
    Down arrow           reload      (gesture mode: swipe down; button mode: the reload corner)
    Left / Right arrows  turn (gyro scheme: device yaw; tilt scheme: device tilt; swipe scheme: a swipe)
    Escape               the Pause button
    Enter                the Skip button (challenge narration, opener)
    T                    read the challenge timer label (VoiceOver can read it: hint "Challenge timer")

With a screen reader running the original replaces the touch views with ADAccessibleGameView; the port
does the same and sends key presses as touches at the centre of the matching screen quadrant.

A game controller (platform/pad.py) presses the same actions through pad_down / pad_up, and its sticks turn
at the speed they are pushed (_update_turn).
"""
from __future__ import annotations

import logging

from ..game.gameplay import (AccessibleGameView, ButtonWithSwipe, ChallengeGameplayController, KeyboardMotion,
                             MotionManager, OpenerGameplayController)
from ..game.parameters import GameParameters
from ..platform.keymap import KeyMap
from ..platform.runloop import RunLoop
from .accessibility import AccessibleScreen, Button, View
from .screens import Screen

log = logging.getLogger('ui.gameplay')

SWIPE_POINTS_PER_SECOND = 600.0     # PORT INPUT: arrow keys in the swipe scheme drag at this speed

#: PORT ADDITION (user report, 2026-10-05): how long fire settles after it is let go.  A press that comes
#: sooner waits until then and counts only if it is still held: a trigger that springs back past half way
#: as it is let go - a worn spring, or a trigger lock that makes a short pull a whole one - was read as a
#: second, very short press, and a short press is a tap, which fires a shot (heard as an extra shot after a
#: burst of the Machine Gun).  Keys go through the same wait, and so do the phone's touches of fire, for a
#: finger rolling back onto the glass (`android_main.TouchInput._begin_view`).  No gun fires faster than
#: every 0.2 s (Weapons.plist `fireRate`), so a tap that ends inside this would not have fired anyway.
FIRE_SETTLE = 0.1


class GameplayScreen(Screen):
    def __init__(self, host, controller):
        super().__init__(host)
        self.controller = controller
        controller.host = self
        self.motion = KeyboardMotion()
        self._turn_keys: dict = {}                        # what is turning now: key or button -> action
        self._space_down = False
        self._fire_let_go = float('-inf')                 # PORT ADDITION: see FIRE_SETTLE
        self._fire_waiting = None                         # the key or button whose press waits for it
        self._corner_down: dict[int, tuple] = {}
        self._pan_translation = 0.0
        self._pan_active = False
        self._last_frame = RunLoop.main().now()
        self._skip_was_hidden = True
        # the button-mode buttons of the non-accessible layout (weaponButton is the controller's)
        self.melee_button = ButtonWithSwipe(action=controller.melee_button_pressed)
        self.switch_button = ButtonWithSwipe(action=controller.switch_weapon_button_pressed)
        self.reload_button = ButtonWithSwipe(action=controller.reload_button_pressed)
        for b in (self.melee_button, self.switch_button, self.reload_button):
            b.gameplay_view_controller = controller

    # --- host services the controller uses -------------------------------------------------------
    def screen_reader_running(self) -> bool:
        return self.host.screen_reader_running()

    def announce(self, text) -> float:
        """Say a line of the game's; PORT ADDITION: returns the seconds the speech that reads it is taken to
        need (ui/reading.py), which a wave handing over weapons waits for before it draws the first
        (`ChallengeGameplayController.hand_over_weapons`)."""
        from ..platform.speech import Speech
        from .reading import in_game_speech, reading_seconds
        # PORT ADDITION (user request, 2026-10-03): said by the second speech while Settings -> Speech -> Use
        # second speech is on (Speech.speak_in_game), and by the first, as it always was, otherwise
        Speech.shared().speak_in_game(text)
        # PORT ADDITION: remembered, so that the Extra mode's story waits for it (still_announcing), with the
        # speech that read it
        self._announced = (str(text), Speech.shared().lines, RunLoop.main().now(), in_game_speech())
        return reading_seconds(text, self._announced[3])

    def still_announcing(self) -> bool:
        """PORT ADDITION: whether the speech is still reading what the game last announced - the weapons a
        wave hands over - so that a story told as the wave begins does not cut it off
        (`ChallengeGameplayController.tell_story_if_due`).  Anything said since has cut it already.  The
        reading is timed, as a hint is, whatever speaks (ui/reading.py)."""
        from ..platform.speech import Speech
        from .reading import reading_seconds
        said = getattr(self, '_announced', None)
        if said is None or Speech.shared().lines != said[1]:
            return False
        return RunLoop.main().now() < said[2] + reading_seconds(said[0], said[3])

    @staticmethod
    def skip_intro_announcement() -> str:
        from ..game.parameters import GameParameters
        model = GameParameters.shared().names_controller()
        if model is not None:                             # PORT ADDITION: in the controller's words
            from ..platform.pad import PadMap
            padmap = PadMap.for_model(model)
            if padmap.names('skip'):
                return 'Press %s to skip intro' % padmap.text('skip')
        from ..platform import host
        if host.ANDROID:                                  # the original's own words, and its touch
            return 'Triple tap to skip intro'
        return 'Press Enter to skip intro'

    def layout_changed(self) -> None:
        # The original posts UIAccessibilityLayoutChangedNotification with a nil argument (0x1000da8c4),
        # which tells VoiceOver the screen changed without moving the cursor or speaking anything.  The port
        # used to say "Skip" here, which meant every dialog in a challenge interrupted itself to announce a
        # button - and the key that skips is in Settings anyway.  Nothing is spoken now.
        self._skip_was_hidden = self.controller.skip_button_hidden

    def present_pause(self, pause_controller) -> None:
        pause_controller.view_did_load()
        from .settings import PauseScreen
        self.host.present_over(self, PauseScreen(self.host, pause_controller))

    def dismiss_pause(self, completion) -> None:
        self.host.pop_overlay()
        completion()

    def present_revive(self, revive_controller) -> None:
        self.host.push_overlay(ReviveScreen(self.host, revive_controller))

    def dismiss_revive(self) -> None:
        top = self.host.top_overlay()
        if isinstance(top, ReviveScreen):
            self.host.pop_overlay()

    # --- lifecycle -------------------------------------------------------------------------------
    def on_present(self) -> None:
        MotionManager.shared().source = self.motion
        self.controller.view_did_load()
        if self.controller.weapon_manager is not None:
            for b in (self.melee_button, self.switch_button, self.reload_button):
                b.weapon_manager = None                   # only weaponButton gets the manager in the nib

    def on_dismiss(self) -> None:
        if MotionManager.shared().source is self.motion:
            MotionManager.shared().source = None
        from ..platform.pad import Pads
        Pads.shared().set_triggers('off')                 # PORT ADDITION: the game is over; so is the gun

    # --- keys ------------------------------------------------------------------------------------
    def _agv(self) -> AccessibleGameView | None:
        return self.controller.accessible_game_view

    def key_down(self, event) -> None:
        self.press(KeyMap.shared().action_for(event.key), event.key)

    def key_up(self, event) -> None:
        self.release(KeyMap.shared().action_for(event.key), event.key)

    # PORT ADDITION: a game controller presses the same actions as the keys, from its own bindings - each
    # kind of controller has its own; `source` tells one held button or key from another, as the key code
    # does for the keyboard, and starts with the pad it came from.
    def pad_down(self, source, name: str) -> None:
        from ..platform.pad import Pads
        self.press(Pads.shared().padmap_for(source[0]).action_for(name), source)

    def pad_up(self, source, name: str) -> None:
        from ..platform.pad import Pads
        self.release(Pads.shared().padmap_for(source[0]).action_for(name), source)

    def press(self, action, k) -> None:
        """An action's key or button went down; `k` is which one."""
        c = self.controller
        if action == 'pause':
            if not isinstance(c, OpenerGameplayController) and not c.paused:
                c.pause_button_touched()
            return
        if action == 'skip':
            if isinstance(c, OpenerGameplayController):
                c.handle_skip_for_accessible_users()
            else:
                c.skip_button_pressed()
            return
        if action == 'timer' and isinstance(c, ChallengeGameplayController):
            from ..platform.speech import Speech          # PORT ADDITION: in-game text (Speech.speak_in_game)
            Speech.shared().speak_in_game(c.timer_label_text)
            return
        if c.paused or getattr(c, 'death_overlay_visible', False):
            # DIVERGENCE: showDeathOverlay brings the death overlay to the front of the gameplay view and
            # gives it userInteractionEnabled (0x10005b9e4 / 0x10005ba20, and 0x1000db814 in the challenge
            # controller), so on a phone it swallows every touch and the weapon views below it stop
            # responding.  Endless also sets paused, which the gate above already catches; the challenge
            # controller does not, so a dead player could still fire, melee, reload and switch weapons
            # until the failed screen loaded.  Keys are not routed through the view hierarchy here, so the
            # overlay has to be honoured explicitly.  Pause, skip and the timer are handled above this and
            # keep working; key_up is deliberately left ungated so a key held at the moment of death still
            # releases cleanly.
            return
        if action in ('turn_left', 'turn_right'):
            if k not in self._turn_keys:                  # a key repeat does not take the turn over again
                self._turn_keys[k] = action
            self._update_turn()
            return
        if isinstance(c, OpenerGameplayController):
            return
        button_mode = GameParameters.shared().button_mode
        agv = self._agv()
        if action == 'fire' and not self._space_down:
            wait = self._fire_let_go + FIRE_SETTLE - RunLoop.main().now()
            if wait > 0.0:
                self._wait_for_fire_to_settle(k, wait)
                return
            self._space_down = True
            if agv is not None:
                agv.touches_began(AccessibleGameView.TOP_RIGHT)
            elif button_mode:
                c.weapon_button.touched_down()
            else:
                c.weapon_touch_area.touched_down()
        elif action in ('melee', 'next_weapon', 'reload') and k not in self._corner_down:
            corner = {'melee': AccessibleGameView.TOP_LEFT, 'next_weapon': AccessibleGameView.BOTTOM_LEFT,
                      'reload': AccessibleGameView.BOTTOM_RIGHT}[action]
            if agv is not None:
                if button_mode:
                    self._corner_down[k] = corner
                    agv.touches_began(corner)
                elif action == 'melee':
                    agv.handle_triple_tap()
                elif action == 'next_weapon':
                    agv.handle_swipe_up_gesture()
                else:
                    agv.handle_swipe_down_gesture()
            elif button_mode:
                button = {'melee': self.melee_button, 'next_weapon': self.switch_button,
                          'reload': self.reload_button}[action]
                self._corner_down[k] = button
                button.touched_down()
            else:
                area = c.weapon_touch_area
                if action == 'melee':
                    area.handle_triple_tap()
                elif action == 'next_weapon':
                    area.handle_swipe_up_gesture()
                else:
                    area.handle_swipe_down_gesture()

    def release(self, action, k) -> None:
        c = self.controller
        if action in ('turn_left', 'turn_right'):
            self._turn_keys.pop(k, None)
            self._update_turn()
            return
        agv = self._agv()
        if action == 'fire' and k == self._fire_waiting:  # let go again before fire settled: a bounce
            self._fire_waiting = None
            return
        if action == 'fire' and self._space_down:
            self._space_down = False
            self._fire_let_go = RunLoop.main().now()
            if agv is not None:
                agv.touches_ended()
            elif GameParameters.shared().button_mode:
                c.weapon_button.touched_up()
            else:
                c.weapon_touch_area.touched_up()
        elif k in self._corner_down:
            target = self._corner_down.pop(k)
            if isinstance(target, ButtonWithSwipe):
                target.touched_up()
            elif agv is not None:
                agv.touches_ended()

    def _wait_for_fire_to_settle(self, k, wait: float) -> None:
        """PORT ADDITION: a fire press too soon after fire was let go (FIRE_SETTLE) is pressed when the wait
        is over, if it is still held then and the game is still in front."""
        if self._fire_waiting is not None:                # a key repeat, or another key: one waits already
            return
        self._fire_waiting = k

        def settled():
            if self._fire_waiting != k:
                return                                    # let go meanwhile
            self._fire_waiting = None
            if self.host.top() is self:
                self._fire_let_go = float('-inf')
                self.press('fire', k)
        RunLoop.main().call_later(wait, settled)

    def _update_turn(self) -> None:
        """A turn key or a turn button decides while one is held; otherwise a controller's stick does, at
        the speed it is pushed to (PORT ADDITION: a key or a button only ever turns at full speed)."""
        if self._turn_keys:                               # the last one pressed decides, key or button
            direction = 1 if next(reversed(self._turn_keys.values())) == 'turn_right' else -1
        else:
            direction = self._stick_turn()
        if direction != self.motion.direction:
            self.motion.set_direction(direction)

    def _stick_turn(self) -> float:
        from ..platform.pad import Pads
        c = self.controller
        # the gate the turn keys pass through in press(): no turning while paused or dead
        if getattr(c, 'paused', False) or getattr(c, 'death_overlay_visible', False):
            return 0
        return Pads.shared().turn()

    def _update_controller(self) -> None:
        """PORT ADDITION: shaking a controller is shaking the phone - motionEnded:withEvent: 0x10005a108,
        which swings the melee weapon under Gesture and does nothing under Button.  And a DualSense's
        triggers are given their feel while the game is in front: R2 a gun's trigger that breaks where it
        fires, L2 a light spring where it reloads.  In a pause, a death or the menus they are plain again."""
        from ..platform.pad import Pads
        pads = Pads.shared()
        if not pads.pads:
            return
        c = self.controller
        playing = (self.host.top() is self and not getattr(c, 'paused', False)
                   and not getattr(c, 'death_overlay_visible', False)
                   and not isinstance(c, OpenerGameplayController))
        if pads.shaken() and playing:
            c.motion_ended(True)
        level = GameParameters.shared().trigger_level()
        playing = playing and level != 'off'
        for iid in list(pads.dualsenses):                 # each by its own bindings
            padmap = pads.padmap_for(iid)
            gun = playing and 'righttrigger' in padmap.names('fire')
            reload = playing and 'lefttrigger' in padmap.names('reload')
            pads.set_triggers('gun and reload' if gun and reload else 'gun' if gun else 'off', level, iid)

    # --- per pass --------------------------------------------------------------------------------
    def frame(self) -> None:
        self._update_turn()                               # PORT ADDITION: a stick moves without events
        self._update_controller()
        now = RunLoop.main().now()
        dt = now - self._last_frame
        self._last_frame = now
        c = self.controller
        # the button-mode buttons of the plain layout tick with the weapon timer in the original
        # (updateWeapons only ticks weaponTouchArea and weaponButton); their taps need no tick.
        if GameParameters.shared().control_scheme == 2 and not c.paused:
            direction = self.motion.direction
            if direction != 0:
                began = not self._pan_active
                if began:
                    self._pan_translation = 0.0
                self._pan_active = True
                # The sensitivity is applied once, by touchesMoveDetected 0x10005a3e0, which multiplies
                # the drag by it exactly as the original does.  Scaling the drag here as well applied it
                # twice, so Swipe turned with the square of the setting - 26 degrees a second at 0.5 and
                # 634 at 3.0, against Gyro's honest 38 and 224.
                speed = SWIPE_POINTS_PER_SECOND
                self._pan_translation += direction * speed * dt
                c.pan_detected(self._pan_translation, began)
            else:
                self._pan_active = False


class ReviveScreen(AccessibleScreen):
    """ADReviveViewController (an ADNoBarViewController, nib ADReviveViewController view #113).

    It has no firstAccessibleElement, so VoiceOver starts at the top of the screen: the tip text above the two
    buttons.  No accessibilityPerformEscape."""

    def __init__(self, host, revive):
        super().__init__(host)
        self.revive = revive

    def load_view(self) -> None:
        v = View('', (0, 0, 568, 320), accessible=False, name='#113')
        box = View('', (0, 0, 568, 320), accessible=False, parent=v, name='#15/#44')
        tip = self.revive.tip or ''                       # tipTextView (ADChallengeDescription #25)
        frame = (105, 87, 359, 104) if self.revive.skip_cost is not None else (105, 137, 359, 104)   # Skip
        self.tip_view = View(tip, frame, parent=box, name='#25')
        self.tip_view.hidden = not tip
        self.revive_button = Button(self.revive.revive_label, (99, 251, 164, 50), parent=box,
                                    actions=[self._revive], name='#8')
        self.revive_button.enabled = self.revive.revive_enabled       # viewWillAppear: setEnabled:NO
        if self.revive.skip_cost is not None:
            # PORT ADDITION: the Extra mode's dearer choice (ReviveController.skip_button_pressed), between
            # the two the original has, which keep their places.
            self.skip_button = Button('Skip this wave for %i diamonds, giving up the time star'
                                      % self.revive.skip_cost,
                                      (99, 195, 372, 50), parent=box, actions=[self._skip], name='skip')
            self.skip_button.enabled = self.revive.skip_enabled
        Button('Game over', (306, 251, 165, 50), parent=box, actions=[self.revive.game_over_button_pressed],
               name='#80')
        self.roots = [v]

    def _revive(self) -> None:
        if not self.revive.revive_button_pressed():
            self.host.show_no_diamonds_alert()            # -[ADNoBarViewController showNoDiamondsAlert] 0x100019990

    def _skip(self) -> None:
        if not self.revive.skip_button_pressed():
            self.host.show_no_diamonds_alert()

    # REMOVED (user request): the magic tap 0x100021cb4 pressed Game over, ending the run.
