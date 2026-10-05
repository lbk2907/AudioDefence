"""Settings and pause, with their shared options panel.

    ADSettingsViewController : ADViewController          (presented from the main menu)
    ADPauseViewController    : ADSettingsViewController   (presented over the gameplay)
    Accessible_ADControlSchemeViewController : ADControlSchemeViewController  (the table both of them show)

-[ADSettingsViewController addControlSchemePanel] 0x1000af5b8 builds the accessible control scheme while
VoiceOver runs, posts UIAccessibilityScreenChangedNotification with its table and centres its view on the
settings nib's controlSchemeView.

PORT UI: the original's accessible table is one long list under "Aiming", "Controls" and "Sound" headings
(its sighted twin, ADControlSchemeViewController, has those three as tabs).  The port shows one heading at a
time - the screen opens inside Aiming, and the arrows the menu navigation is not using change category, as
the armory's tabs do - and adds two categories' worth of things the accessible table never had: the turn
sensitivity (a sighted-only slider in the original) and the key bindings (the port's own, since the original
is touch driven).  Every change is spoken.
"""
from __future__ import annotations

import logging
import time

import pygame

from ..app import App
from .. import localization
from .. import localization
from .. import localization
from ..game import data
from ..game.parameters import GameParameters
from ..platform import host as system
from ..platform.keymap import ACTIONS, BY_MODE, KeyMap, key_text, mode_text
from ..platform.speech import VOICE_NAME
from ..s3d.engine import S3DEngine
from .accessibility import (CELL, Button, View, cross_axis_key, cross_axis_text, menu_tick,
                            play_button_click, JUMP_MODS)
from .challenges import _TableLoader, _play_buttons_sound
from .host import register
from .screens import MenuItem, MenuScreen, joined
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.settings')

#: where the voice starts, before one is chosen: what Settings -> Speech's voice row says it defaults to
VOICE_DEFAULT_HINT = ('the one set in Spoken Content, in System Settings' if system.MAC else
                      'the one set in Control Panel')


def _headphones_playlist():
    return S3DEngine.engine().play_list_with_name('headphonesTest')


# PORT INPUT: the original's descriptions (GYRO_DESCRIPTION, SWIPE_DESCRIPTION, TILT_DESCRIPTION) tell the
# player to turn the device, swipe or tilt it.  All three are the turn keys here, so what actually separates
# them is how fast they turn - the three code paths run at different rates - and the rows say only which is
# which.  The degrees a second are in the README, where they can be read rather than sat through on every
# pass of the list; Turn sensitivity scales all three in proportion.
AIMING_ROWS = (('Gyro', 'Turns slowest', 1),
               ('Swipe', 'Turns in between', 2),
               ('Tilt', 'Turns fastest', 3))

# BUTTON_MODE / GESTURE_MODE describe where to tap and how to swipe; the port's keys do both, so the rows
# say what the mode changes for a keyboard player instead - with the keys bound in that mode, or the
# buttons, when a controller's names are chosen (Settings -> Miscellaneous).
CONTROL_ROWS = (('Button', True), ('Gesture', False))


def control_description(button: bool) -> str:
    if system.ANDROID:                                    # PORT ADDITION (user request): the phone's touches
        if button:
            return ('The screen is four corners: top right fires, top left swings the melee weapon, bottom '
                    'left switches weapon and bottom right reloads')
        return ('Tap anywhere to fire, or touch and hold for continuous fire. Swipe up to switch weapon, '
                'swipe down to reload, and tap with three fingers or shake the phone for melee')
    mode = 'button' if button else 'gesture'
    switch, reload = _mode_words('next_weapon', mode), _mode_words('reload', mode)
    if GameParameters.shared().controller_names():
        if button:
            return ('Your controller presses the four corner buttons of the phone layout, so %s switches '
                    'weapon and %s reloads' % (switch, reload))
        return ('Your controller taps and swipes anywhere on the screen, so %s switches weapon and %s '
                'reloads' % (switch, reload))
    if button:
        return ('Your keys press the four corner buttons of the phone layout, so %s switches weapon and %s '
                'reloads' % (switch, reload))
    return 'Your keys tap and swipe anywhere on the screen, so %s switches weapon and %s reloads' % (switch,
                                                                                                     reload)


def _mode_words(action: str, mode: str) -> str:
    """An action's keys in a control scheme - or its buttons, when a controller's names are chosen."""
    if GameParameters.shared().controller_names():
        from ..platform.pad import button_words
        return button_words(action, mode) or 'no button'
    return KeyMap.shared().keys_text(action, mode)

# PORT UI: Speech holds who speaks the game and how - each speech's output, its voice and its calibration, on a
# page of its own (SPEECH_PAGES) - and the hints.  Keyboard holds the key bindings alone, and Joystick a game
# controller's buttons.  Miscellaneous is last and holds the rest: how the cursor moves through a screen, when the tutorial's lines are shown as
# text and what they name, how a controller vibrates and how a DualSense's triggers feel, whether the game
# looks for updates, and the one button that puts every setting back.
CATEGORIES = (('aiming', 'Aiming'), ('controls', 'Controls'), ('sound', 'Sound'), ('speech', 'Speech'),
              ('keyboard', 'Keyboard'), ('joystick', 'Joystick'), ('misc', 'Miscellaneous'))
PAD_BINDING_HINT = ('Press Enter to add a button, Shift Enter to replace them all, '
                    'Delete to remove the last one.')
SELECT_HINT = 'Press Enter to select.'
#: PORT ADDITION (user request, 2026-10-03): the Speech tab's two pages, one for each speech's own settings -
#: the first speech, which reads everything, and the second, which reads in-game text while Use second speech is
#: on.  A page is a list of its own, opened from its row, as a row's choices are (`open_page`).
SPEECH_PAGES = (('first', 'First speech settings'), ('second', 'Second speech settings'))


def _remove_quietly(path: str) -> None:
    """PORT ADDITION: a backup's working copy taken away, if there is one (Export backup, Import backup)."""
    import os
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


class ControlSchemePanel:
    """Accessible_ADControlSchemeViewController (nib view #21, table #13 at 440x244), as categories."""

    def __init__(self, screen, parent: View, center):
        self.screen = screen
        self.category = CATEGORIES[0][0]                  # settings open inside a category, not on a list
        self.capturing = None                             # the action waiting for its new key
        self.capturing_replaces = False                   # Shift+Enter: the new key replaces the others
        self.pad_capturing = None                         # the action waiting for a controller button
        self.pad_capturing_replaces = False
        self.pad_capturing_model = None                   # and the controller whose profile it goes to
        self.sapi_shown = False                           # Speech: whether SAPI 5's rows are listed
        self.page = None                                  # Speech: the speech whose page is open (SPEECH_PAGES)
        self._engine_settled = 0                          # Android: the engine start the rows were made after
        self.choosing = None                              # a row's choices, shown as a list of their own
        self.calibration = SpeechCalibration(self.announce)   # Speech: the Speech calibration row
        self._trigger_sample = None                       # the Trigger feel being tried on the pad
        self._speech_due = 0.0
        frame = (center[0] - 220.0, center[1] - 122.0, 440.0, 244.0)
        self.view = View('', frame, accessible=False, parent=parent, name='#21')
        self.table_view = View('', frame, accessible=False, parent=self.view, ordered=True, name='#13')
        self.reload_data()

    # --- rows ------------------------------------------------------------------------------------
    def reload_data(self) -> None:
        if self.choosing is not None:                     # a row's own choices are the list just now
            self._load_choices()
            return
        params = GameParameters.shared()
        t = _TableLoader(self.table_view)
        # The original's accessible table is one list under "Aiming", "Controls" and "Sound" headings; the
        # port shows one category at a time and changes it with the arrows the navigation is not using.
        # The category is said as it opens (and as the screen opens), like the armory's tabs, so it is not
        # kept as a row of its own.
        if self.category == 'aiming':                     # cellForAimingAtIndex: 0x1000b5734
            for title, description, scheme in AIMING_ROWS:
                cell = t.cell(title, description, hint=SELECT_HINT,
                              action=lambda s=scheme: self.select_control_scheme(s))
                cell.selected = params.control_scheme == scheme     # selectRowAtIndexPath:
            # the value is a bare multiplier - sensivity * angle in the gyro path 0x10005a108, sensivity *
            # dx in the drag path 0x10005a3e0 - with no unit of its own.  The row reads it alone; the range
            # and what it works out to in degrees a second are in the README.
            t.cell('Turn sensitivity', self.sensitivity_text(),
                   hint='Press Enter for the next value, Shift plus Enter for the previous.',
                   action=self.step_sensitivity, shift_action=self.step_sensitivity_back)
        elif self.category == 'controls':                 # cellForControlAtIndex: 0x1000b5d64
            for title, button in CONTROL_ROWS:
                cell = t.cell(title, control_description(button), hint=SELECT_HINT,
                              action=lambda b=button: self.select_button_mode(b))
                cell.selected = bool(params.button_mode) == button
            if system.ANDROID:                            # PORT ADDITION (user request)
                row = t.cell('Shake sensitivity', self.shake_text(),
                             hint='How easily shaking the phone swings your melee weapon in Gesture mode, '
                                  'from 1, a hard shake, to 10, a light one; all the way down is Off. %s. '
                                  'Shake the phone on '
                                  'this screen to try it: the game says Shake when it feels one.'
                                  % self.slider_words())
                row.adjust = self.adjust_shake            # a slider: the swipes across adjust it
        elif self.category == 'sound':                    # cellForSound: 0x1000b619c
            t.cell('Announcer', 'ON' if params.last_announcer_value() else 'OFF',
                   hint='Press Enter to toggle in-game announcements.', action=self.toggle_announcer)
            t.cell('Test headphones', hint='Press Enter to test your headphones.', action=self.test_headphones)
            # PORT ADDITION (user request, 2026-10-05): which head the game hears with (s3d/sound3d.py).  The test
            # and the phone's files are not offered in a pause: the game's own sounds are held there.
            from ..s3d import sound3d
            in_game = isinstance(self.screen, PauseScreen)
            t.cell('3D sound', sound3d.label(params.sound_3d()),
                   hint=("Which head the game's 3D sound is heard with. Every head hears a little differently: "
                         "choose the one that makes ahead, behind and the sides clearest to you. The game's own is "
                         "the original's. Your own .mhr files are listed too, added with Add 3D sound file. The "
                         'README says how to make one. Press Enter for the list.'
                         if system.ANDROID else
                         "Which head the game's 3D sound is heard with. Every head hears a little differently: "
                         "choose the one that makes ahead, behind and the sides clearest to you. The game's own is "
                         "the original's, and OpenAL Soft's built-in comes with the sound library. Your own .mhr "
                         'files are listed too, from the hrtf folder in the game data folder. The README says how '
                         'to make one. Press Enter for the list.'),
                   action=self.choose_3d_sound, shift_action=self.choose_3d_sound)
            if not in_game:
                t.cell('Test 3D sound',
                       hint='Press Enter to hear a sound go once around you with the 3D sound chosen: it starts '
                            'ahead of you and turns to your right.',
                       action=self.test_3d_sound)
            if system.ANDROID and not in_game:
                t.cell('Add 3D sound file',
                       hint="Press Enter to add a 3D sound of your own, an .mhr file, from the phone's storage, "
                            'and use it. Copy the file to the phone first, to the Download folder for example. It '
                            "is chosen in Android's own file picker, which TalkBack reads, not the game.",
                       action=self.add_3d_sound_file)
                if params.sound_3d().startswith(sound3d.FILE):
                    t.cell('Remove 3D sound file',
                           hint="Press Enter to take the 3D sound file in use out of the game; the game's own is "
                                'used again. You are asked first.',
                           action=self.remove_3d_sound_file)
        elif self.category == 'misc':                     # PORT ADDITION: everything else
            # Language leads the tab: it decides what every other row on every screen is read in,
            # so a player who wants it should not have to walk past the rest to reach it (user request).
            t.cell('Language', dict(params.languages())[params.language()],
                   hint="The language the port's own text is shown and spoken in. English is what "
                        'the port was written in; another language translates it as it is read, which '
                        'takes effect as each screen is opened again. Press Enter for the list.',
                   action=self.choose_language, shift_action=self.choose_language)
            if params.controller_names():                 # the Control and Tab keys have no button
                axis_hint = 'Press Enter to move through menus with the other pair of D-pad directions.'
            else:
                axis_hint = ('Press Enter to move through menus with the other pair; Control with an arrow, '
                             'or with Tab, jumps to the first or last.')
            if not system.ANDROID:                        # the phone moves with VoiceOver's swipes
                t.cell('Menu layout', self.menu_axis_text(), hint=axis_hint, action=self.toggle_menu_axis)
            t.cell('Remember cursor position', 'ON' if params.remember_focus() else 'OFF',
                   hint='Press Enter to toggle: when on, going back to a screen returns the cursor to the '
                        'row you left it on instead of the first one.',
                   action=self.toggle_remember_focus)
            t.cell('Tutorial text', self.tutorial_text_text(),
                   hint='Press Enter for the next setting and Shift plus Enter for the previous.',
                   action=self.step_tutorial_text, shift_action=self.step_tutorial_text_back)
            from ..platform.pad import Pads
            models = Pads.shared().connected_models()
            row = t.cell('Names in hints and tutorial', dict(params.KEY_NAMES)[params.key_names()],
                         hint="Whether the hints and the tutorial text name the keyboard's keys or the "
                              "connected controller's buttons. Press Enter or Shift plus Enter to switch. It "
                              'goes back to Keyboard keys whenever no controller is connected.',
                         action=self.toggle_key_names, shift_action=self.toggle_key_names)
            row.enabled = bool(models)                    # dimmed with no controller (pad._keys_when_none)
            if len(models) > 1:                           # several kinds connected: which one to name
                row = t.cell('Controller for names', params.names_controller() or models[-1],
                             hint='Which connected controller the hints and the tutorial text name the '
                                  'buttons of. Press Enter for the next controller and Shift plus Enter for '
                                  'the previous.',
                             action=self.step_names_controller, shift_action=self.step_names_controller_back)
                row.enabled = params.key_names() == 'buttons'
            levels = dict(params.FEEL_LEVELS)
            t.cell('Joystick vibration', levels[params.vibration_level()],
                   hint='How strongly a game controller vibrates, for hits, kills, explosions, the heartbeat '
                        'and your death. Press Enter for the next setting and Shift plus Enter for the '
                        'previous.',
                   action=self.step_vibration, shift_action=self.step_vibration_back)
            t.cell('Fine haptics', 'ON' if params.fine_haptics() else 'OFF',
                   hint='Press Enter to toggle: when on, a controller that can play what you feel in its '
                        'grips does so - a DualSense plugged in by USB - instead of shaking its motors. '
                        'With no such controller the motors are used either way.',
                   action=self.toggle_fine_haptics)
            t.cell('Trigger feel', levels[params.trigger_level()],
                   hint="Only for a DualSense controller; other controllers have no trigger feel. How stiff "
                        "its triggers are while you play: R2 like a gun's trigger, L2 a pull where it "
                        'reloads. Press Enter for the next setting and Shift plus Enter for the previous.',
                   action=self.step_trigger_level, shift_action=self.step_trigger_level_back)
            t.cell('Check for updates when the game starts', 'ON' if params.check_updates() else 'OFF',
                   hint='Press Enter to toggle: when on, the main menu looks for a new build and tells '
                        'you only if there is one.',
                   action=self.toggle_check_updates)
            # PORT ADDITION (user request, 2026-10-05): the player's files as a whole (game/saves.py).  Clearing
            # and importing are not offered in a pause: the game being played is made of what they replace.
            in_game = isinstance(self.screen, PauseScreen)
            if system.ANDROID:
                t.cell('Export backup',
                       hint='Press Enter to save your progress, settings and buttons in one file, AudioDefence '
                            'backup.zip, in the AudioDefence folder in Documents. Each export replaces the last. '
                            'Import backup brings them back, after the game is installed again or on another '
                            'phone. Nothing is sent anywhere.',
                       action=self.export_backup)
                if not in_game:
                    t.cell('Import backup',
                           hint='Press Enter to bring back the backup in the AudioDefence folder in Documents, in '
                                'place of your progress, settings and buttons. Afterwards the game closes, to start '
                                'again with the backup. Once the game has been uninstalled, Android no longer lets '
                                "it see that file, and it is chosen in Android's own file picker, which TalkBack "
                                'reads, not the game.',
                           action=self.import_backup)
            else:
                t.cell('Open game data folder',
                       hint='Press Enter to open the folder the game keeps your files in: save.json is your '
                            'progress, settings.json your settings and keys.json your keys and controller '
                            'buttons. Close the game before you put files into it, or it writes its own over '
                            'them as it closes.',
                       action=self.open_data_folder)
            if not in_game:
                t.cell('Clear all saves',
                       hint='Press Enter to start the game again from nothing: your coins, diamonds, weapons, '
                            'power-ups, missions, challenges, stars and high score are deleted. Your settings '
                            'and buttons stay. You are asked first.',
                       action=self.clear_all_saves)
            # last, in the game and out of it (user request, 2026-10-05)
            t.cell('Reset all settings',
                   hint='Press Enter to put every setting back to its default. Your key and controller '
                        'bindings stay as they are.',
                   action=self.reset_all_settings)
        elif self.category == 'speech' and self.page is not None:   # PORT ADDITION: a speech's own page
            self.speech_page_rows(t, params, self.page == 'second')
        elif self.category == 'speech':                   # PORT ADDITION: who speaks, and how
            self.sapi_shown = False                       # the voices' rows are on the pages
            # PORT ADDITION (user request, 2026-10-03): the second speech, used or not, and a page of settings
            # for each speech, which can be changed whether the second is used or not
            t.cell('Use second speech', 'ON' if params.second_speech() else 'OFF',
                   hint='Press Enter to toggle: when on, the second speech reads the story in Extra, the tutorial '
                        'and what is said during a game, and the first speech reads everything else. The second '
                        "speech's voice is set in Second speech settings.",
                   action=self.toggle_second_speech, shift_action=self.toggle_second_speech)
            t.cell('First speech settings',
                   hint='The speech that reads the menus, the hints and Settings, and everything else while Use '
                        'second speech is off: its output, voice, rate, pitch, volume and calibration. Press Enter '
                        'to open them, and Escape to come back.',
                   action=lambda: self.open_page('first'))
            t.cell('Second speech settings',
                   hint='The speech that reads the story in Extra, the tutorial and what is said during a game '
                        'while Use second speech is on: its output, voice, rate, pitch, volume and calibration, '
                        'which can be set while it is off. Press Enter to open them, and Escape to come back.',
                   action=lambda: self.open_page('second'))
            # PORT ADDITION (user request, 2026-10-02): a row's hint, read on its own after a pause, as
            # VoiceOver reads one (ui/reading.py).
            t.cell('Hints', 'ON' if params.speak_hints() else 'OFF',
                   hint='Press Enter to toggle: when on, each row is read first and its hint, like this one, '
                        'follows after a pause.',
                   action=self.toggle_hints, shift_action=self.toggle_hints)
            pause = params.hint_pause()
            t.cell('Pause before hints', ('%s second' if pause == 1 else '%s seconds') % self.seconds_text(pause),
                   hint="How long the game waits after reading a row before it reads the row's hint, from 0 to "
                        '3 seconds. ' + self.SAPI_STEP_HINT,
                   action=self.step_hint_pause, shift_action=self.step_hint_pause_back)
        elif self.category == 'keyboard':                 # PORT ADDITION: the key bindings
            keymap = KeyMap.shared()
            scheme = mode_text(keymap.mode())
            for action, _label, _default in ACTIONS:
                detail = keymap.keys_text(action)
                if action in BY_MODE:                     # this one is bound per control scheme
                    detail = '%s, in %s mode' % (detail, scheme)
                row = t.cell(keymap.label(action), detail,
                             hint='Press Enter to add a key, Shift Enter to replace them all, '
                                  'Delete to remove the last one.',
                             action=lambda a=action: self.capture_key(a),
                             shift_action=lambda a=action: self.capture_key(a, replace=True))
                row.binding_action = action               # what Delete acts on, for this row
            t.cell('Restore default keys',
                   hint='Press Enter to put every key back to its default, in both control schemes.',
                   action=self.restore_keys)
        elif self.category == 'joystick':                 # PORT ADDITION: a game controller
            from ..platform.pad import PAD_DEFAULTS, PAD_LABELS, PadMap, Pads
            pads = Pads.shared()
            models = pads.connected_models()
            editing = pads.editing_model()
            if len(models) > 1:                           # several kinds: whose buttons the rows below set
                t.cell('Controller', '%s, %d of %d' % (editing, models.index(editing) + 1, len(models)),
                       hint="The buttons below are this controller's. Press Enter for the next controller "
                            'and Shift plus Enter for the previous.',
                       action=self.step_editing, shift_action=self.step_editing_back)
            else:
                t.cell('Controller', editing or 'none connected',
                       hint=None if editing else 'Connect a controller to set its buttons.')
            t.cell('Turn', 'either stick, sideways',
                   hint='The further a stick is pushed, the faster you turn. The sticks always turn and '
                        'cannot be changed; to turn with buttons instead, set Alternate turn left and '
                        'Alternate turn right below.')
            if editing is None:                           # the buttons are set for a connected controller
                self.click_on_every_row()
                return
            padmap = PadMap.for_model(editing)
            scheme = mode_text(padmap.mode())
            for action in PAD_DEFAULTS:
                detail = padmap.text(action)
                if isinstance(PAD_DEFAULTS[action], dict):   # bound per control scheme, as on the keyboard
                    detail = '%s, in %s mode' % (detail, scheme)
                hint = PAD_BINDING_HINT
                if action in ('turn_left', 'turn_right'):
                    hint = ('This turns at the same speed as the keyboard does, however hard you press; '
                            'the sticks turn as far as they are pushed. ') + hint
                row = t.cell(PAD_LABELS.get(action, KeyMap.label(action)), detail, hint=hint,
                             action=lambda a=action: self.capture_pad(a),
                             shift_action=lambda a=action: self.capture_pad(a, replace=True))
                row.pad_binding_action = action           # what Delete acts on, for this row
            t.cell('Restore default buttons',
                   hint="Press Enter to put every one of this controller's buttons back to its default, in "
                        'both control schemes.',
                   action=self.restore_pad)
        self.click_on_every_row()

    def click_on_every_row(self) -> None:
        """PORT ADDITION: these rows are buttons in the sighted original (ADControlSchemeViewController's
        tabs and option buttons are ADButtonWithFonts), and those click when pressed.  As in Button(), the
        click is added after the row's own action."""
        for row in self.table_view.children:
            for actions in (row.actions, row.shift_actions):
                if actions and play_button_click not in actions:
                    actions.append(play_button_click)

    def focus_first_row(self, prefix: str | None = None) -> None:
        """Land on the category's first option, past its heading, and say where that is - the way the
        armory lands inside a tab it has just changed to."""
        rows = [row for row in self.table_view.children if row.traits == CELL]
        self.screen.post_screen_changed(rows[0] if rows else None, prefix)

    def announce(self, text: str) -> None:
        self.screen.speak(text)

    # --- a speech's own page (PORT ADDITION, user request, 2026-10-03) ----------------------------------
    def speech_page_rows(self, t, params, second: bool) -> None:
        """One speech's settings: its Speech output, its voice's rows while SAPI 5 (the Mac's system voice, the
        phone's text-to-speech) is what it speaks with, then - for the second - whether it follows the first's
        calibration, its Speech calibration (the second's only while it does not follow), and Test speech last."""
        from ..platform.speech import OUTPUTS
        output = params.second_speech_output() if second else params.speech_output()
        # the hints are written out where the rows are made, so the translators' list finds them
        t.cell('Speech output', dict(OUTPUTS)[output],
               hint=(("Which voice the second speech uses. On the phone, Automatic and Android speech are the "
                      "same: the phone's own text-to-speech, set in the rows below. Press Enter for the list."
                      if second else
                      "Which voice speaks the game. On the phone, Automatic and Android speech are the same: the "
                      "phone's own text-to-speech, set in the rows below. Press Enter for the list.")
                     if system.ANDROID else
                     ('Which screen reader or voice the second speech uses. Automatic uses %s. Choose one and only '
                      'that one speaks: the second speech is silent while it is not running. Press Enter for the '
                      'list.' if second else
                      'Which screen reader or voice speaks the game. Automatic uses %s. Choose one and only that '
                      'one speaks: the game is silent while it is not running. Press Enter for the list.')
                     % ('VoiceOver, or the system voice when VoiceOver is off' if system.MAC else
                        'NVDA, or another screen reader that is running, or SAPI 5 when none is')),
               action=self.choose_speech_output, shift_action=self.choose_speech_output)
        self.sapi_shown = self.sapi_speaking(second)
        if self.sapi_shown:                               # only while SAPI 5 is what this speech speaks with
            self.sapi_rows(t, params, second)
        if second:                                        # straight after the voice it follows for
            t.cell("Follow the first speech's calibration", 'ON' if params.second_follows() else 'OFF',
                   hint="Press Enter to toggle: when on, the second speech uses the first speech's calibration, and "
                        'calibrating the first speech calibrates both. Turned off, the second speech keeps that '
                        'calibration until you calibrate it, in the Speech calibration row that then appears.',
                   action=self.toggle_follow, shift_action=self.toggle_follow)
        # PORT ADDITION (user request, 2026-10-02): how fast the speech reads, measured, by which the game
        # predicts when a line has been read, whatever speaks it (ui/reading.py).  For every output: the
        # measurement is the speech's, and stays when the output or the voice changes.  Each speech has its own
        # (user request, 2026-10-03) - the second's row only while it does not follow the first's, since
        # following, there is nothing of its own to measure (user request, the same day).
        if not (second and params.second_follows()):
            word_time = params.speech_word_time(params.SECOND_SPEECH if second else params.FIRST_SPEECH)
            t.cell('Speech calibration',
                   '%i words a minute' % round(60.0 / word_time) if word_time else 'not done yet',
                   hint=('How fast the second speech reads. While Use second speech is on, the game works out from '
                         'it when the story in Extra has been read. Press Enter and the second speech reads a '
                         'sentence; press Enter again the moment it ends, or Escape to cancel.' if second else
                         'How fast the first speech reads. The game works out from it when each row has been read, '
                         'so that its hint comes at the right moment, and the story in Extra too while Use second '
                         "speech is off. Calibrate again after changing the voice or its speed, a screen reader's or "
                         "the game's own. Press Enter and a sentence is read; press Enter again the moment it ends, "
                         'or Escape to cancel.'),
                   action=self.start_calibration)
        # PORT ADDITION (user request, 2026-10-03): this speech heard as it is set now (`test_speech`), last on
        # the page (user request, the same day)
        t.cell('Test speech', hint='Press Enter to hear this speech.', action=self.test_speech)

    def open_page(self, page: str) -> None:
        """A speech's page, as a list of its own: its first row named after the page.  Escape or Back goes back
        to the row it was opened from (`close_page`)."""
        self.page = page
        self._show_ok(False)                              # see _show_ok: a page is on top of the settings too
        self.table_view.children.clear()
        self.reload_data()
        self.focus_first_row(dict(SPEECH_PAGES)[page])

    def close_page(self) -> bool:
        """Escape or Back: a row's list of choices closes first, and then a speech's page, back to its row in the
        Speech tab.  True when one of them was open, so the screen knows the key was used here."""
        if self.close_choices():
            return True
        if self.page is None:
            return False
        title = dict(SPEECH_PAGES)[self.page]
        self.page = None
        self._show_ok(True)
        self.table_view.children.clear()
        self.reload_data()
        self._focus_row(title)
        return True

    def on_a_page(self) -> bool:
        """Whether a row's list or a speech's page is open: the arrows that change category are theirs then."""
        return self.choosing is not None or self.page is not None

    def test_speech(self) -> None:
        """PORT ADDITION (user request, 2026-10-03): the Test speech row - a sentence read by the speech whose
        page is open, the way that speech reads everything: through its Speech output, and with its voice, rate,
        pitch and volume while SAPI 5 (the Mac's system voice, the phone's engine) is what it speaks with.  The
        second speech's is read whether Use second speech is on or not, as its other rows are.  An output that
        cannot speak just now is said to be silent, through a speech that can, as choosing it says
        (`say_silent`)."""
        from ..platform.speech import Speech
        params = GameParameters.shared()
        speech = Speech.shared()
        second = self.second_page()
        choice = params.second_speech_output() if second else params.speech_output()
        if not speech.can_speak(choice):
            self.say_silent(choice, second)
        elif second:                                      # one sentence for both (user request): which
            speech.speak_second('This is how this voice sounds while you play. Change its speed, pitch or '
                                'volume until every word is clear.')   # page it is, the player knows
        else:
            self.announce('This is how this voice sounds while you play. Change its speed, pitch or '
                          'volume until every word is clear.')

    def toggle_second_speech(self) -> None:
        params = GameParameters.shared()
        params.set_second_speech(not params.second_speech())
        self.reload_data()
        self.announce('Use second speech %s' % ('ON' if params.second_speech() else 'OFF'))

    def toggle_follow(self) -> None:
        params = GameParameters.shared()
        params.set_second_follows(not params.second_follows())
        self.reload_data()
        self.announce("Follow the first speech's calibration %s" % ('ON' if params.second_follows() else 'OFF'))

    # --- choosing from a list (PORT ADDITION) -----------------------------------------------------
    def open_choices(self, title: str, options, current, apply) -> None:
        """Show a row's choices as a list of their own, the way the aiming and the control rows are listed.

        Stepping through a setting with Enter suits the three or four choices most of them have.  Speech
        output has twelve, and the SAPI 5 voice list has as many voices as are installed - two hundred and
        fifty on the machine this was written for - which is not a list to walk through one press at a
        time, hearing each one as you pass it.  Enter opens it, the one in use is where the cursor lands,
        Enter takes one and Escape leaves it as it was (user request).
        """
        self.choosing = (title, list(options), current, apply)
        self._show_ok(False)                              # see _show_ok
        self.table_view.children.clear()                  # a list of its own: no row keeps its place
        self.reload_data()
        rows = [row for row in self.table_view.children if row.traits == CELL]
        on = next((row for row in rows if row.selected), rows[0] if rows else None)
        # no full stop at the end: the prefix is joined to the row with one (`_apply_pending_focus`)
        self.screen.post_screen_changed(on, '%s. %d to choose from' % (title, len(rows)))

    def _load_choices(self) -> None:
        _title, options, current, _apply = self.choosing
        t = _TableLoader(self.table_view)
        for value, label in options:
            row = t.cell(label, hint='Press Enter to use this one. Escape leaves it as it was.',
                         action=lambda v=value: self.take_choice(v))
            row.selected = value == current               # where the cursor lands, and read as selected

    def _show_ok(self, visible: bool) -> None:
        """PORT ADDITION: the screen's OK button is hidden while a row's choices are listed (user
        request).  OK finishes the settings screen, and a list is a page on top of it: Enter takes a
        choice and Back leaves the list, so OK there would either do nothing a player wants or throw them
        out of the settings altogether, which is what it did."""
        button = getattr(self.screen, 'ok_button', None)
        if button is not None:
            button.hidden = not visible

    def take_choice(self, value) -> None:
        title, _options, _current, apply = self.choosing
        self.choosing = None
        self._show_ok(self.page is None)
        self.table_view.children.clear()
        apply(value)                                      # which says what was chosen, in the new voice
        self.reload_data()
        self._focus_row(title)

    def close_choices(self) -> bool:
        """Escape or Back with a list open: back to the row it was opened from, the setting untouched.
        True when there was one open, so the screen knows the key was used here."""
        if self.choosing is None:
            return False
        title = self.choosing[0]
        self.choosing = None
        self._show_ok(self.page is None)
        self.table_view.children.clear()
        self.reload_data()
        self._focus_row(title)
        return True

    def _focus_row(self, title: str) -> None:
        rows = [row for row in self.table_view.children if row.traits == CELL]
        # by the row's English, which `title` is, so it is found in a translated game too
        row = next((r for r in rows if (r._label or '').startswith(title)), rows[0] if rows else None)
        self.screen.post_screen_changed(row)

    # --- categories ------------------------------------------------------------------------------
    def open_category(self, key: str) -> None:
        self.category = key
        self.page = None
        self.capturing = None
        self.capturing_replaces = False
        self.table_view.children.clear()                  # a new list: no row keeps its place
        self.reload_data()
        self.focus_first_row(dict(CATEGORIES)[key])       # named, then the option it lands on

    @staticmethod
    def category_keys_text() -> str:
        """Both pairs of arrows, whichever way round the player has them: "Up and Down change category,
        Left and Right move through it"."""
        return localization.translate(cross_axis_text().replace('tab', 'category'))

    def move_category(self, where: str) -> None:
        """PORT ADDITION: the arrows the menu navigation is not using move between categories - 'next',
        'previous', 'first' or 'last', as the element keys do one axis over."""
        keys = [key for key, _title in CATEGORIES]
        step = {'next': 1, 'previous': -1}.get(where)
        if step is None:
            i = 0 if where == 'first' else len(keys) - 1
        else:
            i = max(0, min(len(keys) - 1, keys.index(self.category) + step))   # the ends hold, as elsewhere
        menu_tick()                                       # PORT ADDITION: felt as well as heard
        self.open_category(keys[i])                       # at an end: says where we still are

    # --- aiming ----------------------------------------------------------------------------------
    @staticmethod
    def sensitivity_text(value=None) -> str:
        value = GameParameters.shared().sensivity if value is None else value
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def select_control_scheme(self, scheme: int) -> None:   # willSelectRowAtIndexPath: 0x1000b51b0
        GameParameters.shared().set_control_scheme(scheme)
        self.reload_data()                                # the selected row moves within the section
        title = next(t for t, _d, s in AIMING_ROWS if s == scheme)
        self.announce('%s selected' % title)

    def step_sensitivity(self, step: int = 1) -> None:
        params = GameParameters.shared()
        steps = params.SENSIVITY_STEPS
        current = min(steps, key=lambda s: abs(s - params.sensivity))
        params.set_sensivity(steps[(steps.index(current) + step) % len(steps)])
        self.reload_data()
        self.announce('Turn sensitivity %s' % self.sensitivity_text())

    def step_sensitivity_back(self) -> None:
        self.step_sensitivity(-1)

    # --- controls --------------------------------------------------------------------------------
    @staticmethod
    def shake_text(value=None) -> str:                    # PORT ADDITION (Android)
        value = GameParameters.shared().shake_sensitivity() if value is None else value
        return 'Off' if value == 0 else '%d' % value

    @staticmethod
    def slider_words() -> str:
        if GameParameters.shared().menu_axis() == 'vertical':
            return 'Swipe right to raise it, left to lower it'
        return 'Swipe up to raise it, down to lower it'

    def adjust_shake(self, step: int) -> None:
        """The Shake sensitivity slider moved one step (it stops at its ends, as a slider does)."""
        params = GameParameters.shared()
        value = max(0, min(10, params.shake_sensitivity() + step))
        if value == params.shake_sensitivity():
            self.announce(self.shake_text())              # at an end: says where it still is
            return
        params.set_shake_sensitivity(value)
        self.reload_data()
        self.announce(self.shake_text())

    def select_button_mode(self, button: bool) -> None:
        GameParameters.shared().set_button_mode(button)
        self.reload_data()
        mode = 'button' if button else 'gesture'          # Next weapon and Reload are bound per scheme
        self.announce('%s selected, %s switches weapon, %s reloads'
                      % ('Button' if button else 'Gesture',
                         _mode_words('next_weapon', mode), _mode_words('reload', mode)))

    # --- sound -----------------------------------------------------------------------------------
    def toggle_announcer(self) -> None:
        params = GameParameters.shared()
        params.set_announcer(not params.last_announcer_value())
        self.reload_data()
        self.announce('Announcer %s' % ('ON' if params.last_announcer_value() else 'OFF'))

    @staticmethod
    def tutorial_text_text(mode=None) -> str:
        params = GameParameters.shared()
        return dict(params.TUTORIAL_TEXT_MODES)[params.tutorial_text_mode() if mode is None else mode]

    def step_tutorial_text(self, step: int = 1) -> None:
        params = GameParameters.shared()
        modes = [m for m, _text in params.TUTORIAL_TEXT_MODES]
        mode = modes[(modes.index(params.tutorial_text_mode()) + step) % len(modes)]
        params.set_tutorial_text_mode(mode)
        self.reload_data()
        self.announce('Tutorial text %s' % self.tutorial_text_text(mode))

    def step_tutorial_text_back(self) -> None:
        self.step_tutorial_text(-1)

    @staticmethod
    def test_headphones() -> None:
        pl = _headphones_playlist()
        sound = pl.sound('HeadphonesTest') if pl is not None else None
        if sound is not None:
            sound.play()

    # --- 3D sound (PORT ADDITION, user request, 2026-10-05: s3d/sound3d.py) -----------------------------
    #: Test 3D sound: the Machine's loop - steady, and wide enough in pitch to be placed by ear - once around the
    #: listener at two units, in this many seconds
    TEST_3D_SECONDS = 6.0
    TEST_3D_DISTANCE = 2.0

    def choose_3d_sound(self) -> None:
        from ..s3d import sound3d
        self.open_choices('3D sound', sound3d.choices(), GameParameters.shared().sound_3d(), self.take_3d_sound)

    def take_3d_sound(self, choice: str) -> None:
        """The device hears with it at once, and it is kept; one that does not load is said, and the one
        before is kept."""
        from ..s3d import sound3d
        params = GameParameters.shared()
        if S3DEngine.engine().device.use_3d_sound(choice):
            params.set_sound_3d(choice)
            self.reload_data()
            self.announce('3D sound: %s' % sound3d.label(choice))
        else:
            self.reload_data()
            self.announce('%s could not be used as a 3D sound. The one before is kept.' % sound3d.label(choice))

    def test_3d_sound(self) -> None:
        """The Machine's loop goes once around the listener, from ahead towards the right, wherever the head was
        last turned (S3DEngine.normalize_to_head_position: ahead is +x and the right +y of where it faces).  Its
        playlist is put away again afterwards unless something else had it out."""
        import math
        from ..platform.runloop import RunLoop
        self.stop_3d_test()
        engine = S3DEngine.engine()
        pl = engine.play_list_with_name('Machine')
        if pl is None:
            return
        was_active = pl.active
        loop = RunLoop.main()

        def start(_playlist=None) -> None:
            sound = pl.sound('Machine_machine_loop_SPA')
            if sound is None or self._test_3d is not None:
                return
            began = loop.now()

            def place() -> None:
                turned = (loop.now() - began) / self.TEST_3D_SECONDS
                if turned >= 1.0:
                    self.stop_3d_test()
                    return
                angle = 2.0 * math.pi * turned
                ahead = self.TEST_3D_DISTANCE * math.cos(angle)
                right = self.TEST_3D_DISTANCE * math.sin(angle)
                h = engine.head_orientation
                hx, hy, _hz = engine.head_position
                dy = -right                                   # the planar frame's y is the head's left
                sound.set_planar((hx + ahead * math.cos(h) - dy * math.sin(h),
                                  hy + ahead * math.sin(h) + dy * math.cos(h), 0.0))
            place()
            sound.set_spatialized(True)
            sound.play(True)
            self._test_3d = (sound, loop.schedule_timer(0.02, place), pl, was_active)
        self._test_3d = None
        if was_active:
            start()
        else:
            pl.activate(start)

    def stop_3d_test(self) -> None:
        test, self._test_3d = getattr(self, '_test_3d', None), None
        if test is None:
            return
        sound, timer, pl, was_active = test
        timer.invalidate()
        sound.stop()
        if not was_active:
            pl.deactivate()

    def add_3d_sound_file(self) -> None:
        """Android: an .mhr file chosen in Android's file picker, copied into the game data folder's hrtf folder
        under its own name once the mixer has read it, and used."""
        import os
        from ..s3d import sound3d
        made = os.path.join(sound3d.folder(), 'adding.tmp')
        if self._pick_document('open', made, picked=lambda state, why: self._added_3d_sound(made, state, why)):
            self.announce("Android's file picker is open. Turn TalkBack on and choose the .mhr file.")

    def _added_3d_sound(self, made: str, state: str, why: str) -> None:
        import os
        from ..platform.jbridge import bridge
        from ..s3d import sound3d
        if state != 'done':
            _remove_quietly(made)
            self.announce('No file chosen. Nothing was added.' if state == 'cancelled' else
                          'The file could not be read: %s.' % why)
            return
        phone = bridge()
        problem = str(phone.checkHrtf(made) or '')
        if problem:
            _remove_quietly(made)
            self.announce('That file is not a 3D sound the game can use: %s.' % problem)
            return
        name = os.path.basename(str(phone.documentName() or '').replace('\\', '/')).strip() or '3D sound'
        if name.lower().endswith('.mhr'):
            name = name[:-4]
        if name in (sound3d.GAME_NAME, sound3d.BUILTIN_NAME):
            name += ' (yours)'
        try:
            os.replace(made, os.path.join(sound3d.folder(), name + '.mhr'))
        except OSError as exc:
            _remove_quietly(made)
            self.announce('The file could not be added: %s.' % exc)
            return
        self.take_3d_sound(sound3d.FILE + name)

    def remove_3d_sound_file(self) -> None:
        from .host import AlertScreen
        host = self.screen.host
        host.push_overlay(AlertScreen(
            host, 'Remove 3D sound file?',
            "The 3D sound file in use is taken out of the game, and the game's own is used again.",
            [('No', None), ('Yes, remove it', self._remove_3d_sound_now)]))

    def _remove_3d_sound_now(self) -> None:
        from ..s3d import sound3d
        params = GameParameters.shared()
        choice = params.sound_3d()
        if not choice.startswith(sound3d.FILE):
            return
        S3DEngine.engine().device.use_3d_sound(sound3d.GAME)
        params.set_sound_3d(sound3d.GAME)
        _remove_quietly(sound3d.path_of(choice))
        self.reload_data()
        self.announce("3D sound file removed. The game's own is used again.")

    # --- keyboard --------------------------------------------------------------------------------
    @staticmethod
    def menu_axis_text(axis=None) -> str:
        params = GameParameters.shared()
        return dict(params.MENU_AXES)[params.menu_axis() if axis is None else axis]

    def toggle_remember_focus(self) -> None:
        params = GameParameters.shared()
        params.set_remember_focus(not params.remember_focus())
        self.reload_data()
        self.announce('Remember cursor position %s' % ('ON' if params.remember_focus() else 'OFF'))

    # --- miscellaneous (PORT ADDITION) -----------------------------------------------------------
    def toggle_check_updates(self) -> None:
        params = GameParameters.shared()
        params.set_check_updates(not params.check_updates())
        self.reload_data()
        self.announce('Check for updates when the game starts %s'
                      % ('ON' if params.check_updates() else 'OFF'))

    RESET_DONE = 'All settings reset to default. Your key and controller bindings are unchanged.'
    #: what Import backup says before the game closes, timed by it (said in _import_from, where the
    #: translators' list finds it)
    IMPORTED = 'Backup imported. The game closes now: open it again to play with the backup.'

    def reset_all_settings(self) -> None:
        """Every setting on these pages back to where a new profile starts, except the key bindings and the
        controller's - they have their own Restore default keys and Restore default buttons.

        Each value is what the setting's own getter answers when nothing is stored, so a reset profile
        and a new one cannot disagree.  The setters are all the Settings rows ever call, so going
        through them here misses nothing the rows would have done."""
        params = GameParameters.shared()
        params.set_control_scheme(1)                              # last_control_scheme with nothing stored
        params.set_sensivity(params.DEFAULT_SENSIVITY)
        params.set_button_mode(params.DEFAULT_BUTTON_MODE)        # last_button_mode, likewise
        params.set_announcer(True)                                # last_announcer_value, likewise
        params.set_tutorial_text_mode(params.DEFAULT_TUTORIAL_TEXT)
        params.set_menu_axis(params.DEFAULT_MENU_AXIS)
        params.set_remember_focus(params.DEFAULT_REMEMBER_FOCUS)
        if system.ANDROID:                                # PORT ADDITION: the phone's own settings
            params.set_shake_sensitivity(params.DEFAULT_SHAKE_SENSITIVITY)
            params.set_speech_engine(None)
        params.set_check_updates(params.DEFAULT_CHECK_UPDATES)
        params.set_menu_music_volume(params.DEFAULT_MENU_MUSIC_VOLUME)
        params.set_vibration_level(params.DEFAULT_VIBRATION)
        params.set_trigger_level(params.DEFAULT_TRIGGER_FEEL)
        params.set_fine_haptics(params.DEFAULT_FINE_HAPTICS)
        params.set_key_names(params.DEFAULT_KEY_NAMES)
        params.set_modern_audio(params.DEFAULT_MODERN_AUDIO)
        params.set_names_controller(None)
        params.set_speech_output(params.DEFAULT_SPEECH_OUTPUT)
        params.set_language(params.DEFAULT_LANGUAGE)
        params.set_sapi(voice=None, rate=None, boost=False, pitch=0, volume=None)
        params.set_speak_hints(params.DEFAULT_SPEAK_HINTS)
        params.set_hint_pause(params.DEFAULT_HINT_PAUSE)
        # PORT ADDITION (user request, 2026-10-03): the second speech: not used, and its own settings back
        params.set_second_speech(params.DEFAULT_SECOND_SPEECH)
        params.set_second_speech_output(params.DEFAULT_SPEECH_OUTPUT)
        params.set_second_sapi(voice=None, rate=None, boost=False, pitch=0, volume=None)
        if system.ANDROID:
            params.set_second_speech_engine(None)
        params.forget_speech_word_times()                 # the pace measured is forgotten, both speeches'
        params.set_sound_3d(params.DEFAULT_SOUND_3D)      # PORT ADDITION (2026-10-05): the game's own 3D sound
        S3DEngine.engine().device.use_3d_sound(params.DEFAULT_SOUND_3D)
        params.set_second_follows(params.DEFAULT_SECOND_FOLLOWS)
        App.apply_menu_music_volume()
        self.reload_data()
        if calibration_wanted():                          # PORT ADDITION (user request, 2026-10-02): the pace
            # was forgotten with the rest: asked for again at once, as at start-up, rather than left
            # guessed until the next start (the line is the one below, which is where the translators' list
            # finds it)
            self.ask_for_calibration(localization.translate(self.RESET_DONE), row='Reset all settings')
        else:
            self.announce('All settings reset to default. Your key and controller bindings are unchanged.')

    # --- the player's files (PORT ADDITION, user request, 2026-10-05: game/saves.py) ----------------
    def open_data_folder(self) -> None:
        from ..game import saves
        if saves.open_folder():
            self.announce('Game data folder opened.')
        else:
            self.announce('The game data folder could not be opened.')

    def clear_all_saves(self) -> None:
        """Asked first, No first: what goes cannot be brought back."""
        from .host import AlertScreen
        host = self.screen.host
        host.push_overlay(AlertScreen(
            host, 'Clear all saves?',
            'Your coins, diamonds, weapons, power-ups, missions, challenges, stars and high score are deleted and '
            'cannot be brought back. Your settings and buttons stay. Export backup keeps a copy first.'
            if system.ANDROID else
            'Your coins, diamonds, weapons, power-ups, missions, challenges, stars and high score are deleted and '
            'cannot be brought back. Your settings and buttons stay.',
            [('No', None), ('Yes, clear all saves', self._clear_all_saves_now)]))

    def _clear_all_saves_now(self) -> None:
        """The progress goes, and the main menu opens on the new one, saying so as it is named."""
        from ..game import saves
        saves.clear_progress()
        host = self.screen.host
        self.screen.back_button_pressed()                 # to the main menu, as its Back does
        menu = host.top()
        cleared = localization.translate('All saves cleared')
        pending = getattr(menu, '_pending_focus', None)
        if pending is not None:
            menu.post_screen_changed(pending[0], cleared)
        else:
            self.screen.speak('All saves cleared')

    def export_backup(self) -> None:
        """Android: the three files in one zip, over the last one, in the AudioDefence folder in Documents -
        chosen in Android's file picker on Android 8 and 9, which have no such folder for an app."""
        import os
        from .. import paths
        from ..game import saves
        from ..platform.jbridge import bridge
        made = os.path.join(paths.user_dir(), 'export.tmp.zip')
        try:
            saves.write_backup(made)
        except OSError:
            self.announce('The backup could not be made.')
            return
        answer = str(bridge().exportBackup(made) or '')
        if answer == 'picker':
            if self._pick_document('create', made, saves.BACKUP_NAME):
                self.announce("Android's file picker is open, to choose where the backup goes. Turn TalkBack on "
                              'to use it.')
            return
        _remove_quietly(made)
        state, _newline, rest = answer.partition('\n')
        if state == 'ok':
            self.announce('Backup saved in the AudioDefence folder in Documents, as %s.'
                          % (rest or saves.BACKUP_NAME))
        else:
            self.announce('The backup could not be saved: %s.' % rest)

    def import_backup(self) -> None:
        """Android: asked first, then the backup read from its folder - or chosen in Android's file picker,
        where the game cannot see one of its own there."""
        from .host import AlertScreen
        host = self.screen.host
        host.push_overlay(AlertScreen(
            host, 'Import backup?',
            'The backup takes the place of your progress, settings and buttons, which cannot be brought back. '
            'Afterwards the game closes, to start again with the backup.',
            [('No', None), ('Yes, import the backup', self._import_backup_now)]))

    def _import_backup_now(self) -> None:
        import os
        from .. import paths
        from ..platform.jbridge import bridge
        path = os.path.join(paths.user_dir(), 'import.tmp.zip')
        state, _newline, why = str(bridge().findBackup(path) or '').partition('\n')
        if state == 'ok':
            self._import_from(path)
        elif state == 'failed':
            _remove_quietly(path)
            self.announce('The backup could not be read: %s.' % why)
        elif not self._pick_document('open', path):
            pass
        elif state == 'none':                             # none it can see: installed again since, or none made
            self.announce('The game cannot see a backup of its own in the AudioDefence folder in Documents: '
                          "Android shows a game only the files it made, and none once it has been uninstalled. "
                          "Android's file picker is open instead. Turn TalkBack on and choose AudioDefence "
                          'backup.zip, in the AudioDefence folder in Documents.')
        else:                                             # Android 8 and 9: the picker is the only way there
            self.announce("Android's file picker is open. Turn TalkBack on and choose AudioDefence backup.zip.")

    def _pick_document(self, kind: str, path: str, name: str = '', picked=None) -> bool:
        """Android's file picker, for a backup to read into `path` ('open') or to write `path` to ('create',
        as `name`), and what came of it said when it closes - or, given `picked`, handed to it as the state
        and why; False if it could not be opened, which has been said.  The game goes on running underneath:
        the picker's answer is looked for four times a second (Bridge.documentState)."""
        from ..platform.jbridge import bridge
        from ..platform.runloop import RunLoop
        phone = bridge()
        started = phone.pickFileToOpen(path) if kind == 'open' else phone.pickFileToCreate(name, path)
        if not started:
            _remove_quietly(path if kind == 'create' else '')
            self.announce("Android's file picker could not be opened.")
            return False

        def look() -> None:
            state, _newline, why = str(phone.documentState() or '').partition('\n')
            if state == 'waiting':
                RunLoop.main().call_later(0.25, look)
            elif picked is not None:
                picked(state, why)
            elif kind == 'create':
                _remove_quietly(path)
                self.announce('Backup saved.' if state == 'done' else
                              'No place chosen. The backup was not saved.' if state == 'cancelled' else
                              'The backup could not be saved: %s.' % why)
            elif state == 'done':
                self._import_from(path)
            else:
                _remove_quietly(path)
                self.announce('No backup chosen. Nothing was changed.' if state == 'cancelled' else
                              'The backup could not be read: %s.' % why)
        RunLoop.main().call_later(0.25, look)
        return True

    def _import_from(self, path: str) -> None:
        """The chosen file put in place, if it is a backup, and the game closed once that has been said."""
        from ..game import saves
        from ..platform.runloop import RunLoop
        from .reading import reading_seconds
        found = saves.read_backup(path)
        _remove_quietly(path)
        if found is None:
            self.announce('That file is not an Audio Defence backup. Nothing was changed.')
            return
        saves.restore(found)
        self.announce('Backup imported. The game closes now: open it again to play with the backup.')
        RunLoop.main().call_later(reading_seconds(localization.translate(self.IMPORTED)) + 0.5,
                                  self.screen.host.quit_game)

    # --- joystick (PORT ADDITION) ----------------------------------------------------------------
    @staticmethod
    def _next_level(level: str, step: int) -> str:
        levels = [key for key, _text in GameParameters.FEEL_LEVELS]
        return levels[(levels.index(level) + step) % len(levels)]

    def step_vibration(self, step: int = 1) -> None:
        params = GameParameters.shared()
        params.set_vibration_level(self._next_level(params.vibration_level(), step))
        self.reload_data()
        self.announce('Joystick vibration %s' % dict(params.FEEL_LEVELS)[params.vibration_level()])
        from ..platform.haptics import Haptics            # so the new strength can be felt
        Haptics.shared().sample()

    def step_vibration_back(self) -> None:
        self.step_vibration(-1)

    #: PORT ADDITION: seconds a stepped Trigger feel is left on the pad, to squeeze R2 and feel it.  The
    #: triggers are a game's feel, and the game is not running while you are choosing it.
    TRIGGER_SAMPLE = 8.0

    def toggle_fine_haptics(self) -> None:
        params = GameParameters.shared()
        params.set_fine_haptics(not params.fine_haptics())
        self.reload_data()
        self.announce('Fine haptics %s' % ('ON' if params.fine_haptics() else 'OFF'))
        from ..platform.haptics import Haptics            # so the difference can be felt at once
        Haptics.shared().sample()

    def step_trigger_level(self, step: int = 1) -> None:
        params = GameParameters.shared()
        params.set_trigger_level(self._next_level(params.trigger_level(), step))
        self.reload_data()
        self.announce('Trigger feel %s' % dict(params.FEEL_LEVELS)[params.trigger_level()])
        self.sample_triggers(params.trigger_level())

    def sample_triggers(self, level: str) -> None:
        """Give a connected DualSense this feel for a few seconds, so it can be tried here; then plain
        again, as the menus always leave it."""
        from ..platform.pad import Pads
        from ..platform.runloop import RunLoop
        pads = Pads.shared()
        if not pads.dualsenses:
            return
        if level == 'off':
            pads.set_triggers('off')
            return
        pads.set_triggers('gun and reload', level)
        token = self._trigger_sample = object()

        def plain() -> None:
            if self._trigger_sample is token:             # a later step has its own few seconds
                self._trigger_sample = None
                pads.set_triggers('off')
        RunLoop.main().call_later(self.TRIGGER_SAMPLE, plain)

    def step_trigger_level_back(self) -> None:
        self.step_trigger_level(-1)

    def choose_language(self) -> None:
        """PORT ADDITION: the languages as a list of their own (user request), as Speech output and the
        SAPI 5 voice are.  Each language names itself in its own script, so stepping through them reads
        one out in a language the player may not have chosen yet; the list says them once."""
        params = GameParameters.shared()
        self.open_choices('Language', list(params.languages()), params.language(), self.take_language)

    def take_language(self, choice: str) -> None:
        """The chosen language, read in at once, so the rows rebuilt after this and every screen opened
        afterwards are in it.  A row already on screen keeps the text it was built with."""
        params = GameParameters.shared()
        params.set_language(choice)                       # which loads it (GameParameters.set_language)
        self.reload_data()
        self.announce('Language: %s' % dict(params.languages())[choice])

    def toggle_key_names(self) -> None:
        params = GameParameters.shared()
        params.set_key_names('keys' if params.key_names() == 'buttons' else 'buttons')
        self.reload_data()
        self.announce('Names in hints and tutorial: %s' % dict(params.KEY_NAMES)[params.key_names()])

    def choose_speech_output(self) -> None:
        """PORT ADDITION: the outputs as a list (user request).  Twelve of them, and each one said as you
        passed it while stepping - the list says them once and takes the one you land on.  The second speech's
        page lists them for the second (user request, 2026-10-03)."""
        from ..platform.speech import OUTPUTS
        params = GameParameters.shared()
        if self.second_page():
            self.open_choices('Speech output', list(OUTPUTS), params.second_speech_output(),
                              self.take_second_output)
            return
        self.open_choices('Speech output', list(OUTPUTS), params.speech_output(), self.take_speech_output)

    def take_second_output(self, choice: str) -> None:
        """PORT ADDITION (user request, 2026-10-03): the second speech's output, said through it so its voice is
        heard - or, when it cannot speak, by the first speech, saying the second will be silent."""
        from ..platform.speech import OUTPUTS, Speech
        GameParameters.shared().set_second_speech_output(choice)
        speech = Speech.shared()
        if speech.can_speak(choice):
            speech.speak_second('Speech output: %s' % dict(OUTPUTS)[choice])
        else:
            self.say_silent(choice, True)

    def say_silent(self, choice: str, second: bool) -> None:
        """A speech's Speech output cannot speak just now: said through a speech that can - the first speech for
        the second's, and the automatic choice for the first's, since it could not be heard otherwise and the
        player would be left in silence without knowing why."""
        from ..platform.speech import OUTPUTS, PRISM_NAMES, Speech
        name = dict(OUTPUTS)[choice]
        speech = Speech.shared()
        no_prism = choice in PRISM_NAMES and speech.readers.ctx is None
        if second and no_prism:
            self.announce('Speech output: %s. It needs Prism, which is not installed, so the second speech will be '
                          'silent.' % name)
        elif second:
            self.announce('Speech output: %s. %s is not running, so the second speech will be silent until it is.'
                          % (name, name))
        # speak_automatic takes a line as it is, so these are put in the player's language here (2026-10-02)
        elif no_prism:
            speech.speak_automatic(localization.translate('Speech output: %s. It needs Prism, which is not '
                                                          'installed, so the game will be silent.' % name))
        else:
            speech.speak_automatic(localization.translate('Speech output: %s. %s is not running, so the game '
                                                          'will be silent until it is.' % (name, name)))

    def take_speech_output(self, choice: str) -> None:
        """The chosen Speech output.  Said through the new one - or, when that one cannot speak, through
        the automatic choice, since it could not be heard otherwise and the player would be left in
        silence without knowing why."""
        from ..platform.speech import OUTPUTS, Speech
        params = GameParameters.shared()
        changed = choice != params.speech_output()
        params.set_speech_output(choice)
        name = dict(OUTPUTS)[choice]
        speech = Speech.shared()
        # ask_for_calibration takes a line as it is, so this is put in the player's language here (2026-10-02)
        if changed and calibration_wanted():
            # PORT ADDITION (user request, 2026-10-02): the speech has never been measured - the question
            # at start-up found nothing it could be heard through - and it can be now: the game asks for a
            # Speech calibration at once, and the choice is said as the question opens rather than cut off
            # by it.  A measurement there is kept whatever the output: it is the speech's, not the voice's.
            self.ask_for_calibration(localization.translate('Speech output: %s' % name))
        elif speech.can_speak(choice):
            self.announce('Speech output: %s' % name)
        else:
            self.say_silent(choice, False)

    # --- SAPI 5 (PORT ADDITION) ------------------------------------------------------------------
    SAPI_STEP_HINT = 'Press Enter for the next setting and Shift plus Enter for the previous.'
    SPEECH_CHECK_EVERY = 1.0                              # seconds between looks at what speaks

    @staticmethod
    def sapi_speaking(second: bool = False) -> bool:
        """Whether SAPI 5 is what the first speech speaks with - or the second's, for `second`: chosen, or
        Automatic with no screen reader running."""
        from ..platform.speech import Speech
        params = GameParameters.shared()
        choice = params.second_speech_output() if second else params.speech_output()
        return choice == 'sapi' or (choice == 'auto' and Speech.shared().automatic_output() == 'sapi')

    def follow_speech(self) -> None:
        """On a speech's page, SAPI 5's rows come and go as it starts or stops being what speaks - a screen
        reader started or closed while the list is open - looked at once a second."""
        if (self.category != 'speech' or self.page is None or self.capturing is not None
                or self.choosing is not None or self.calibration.timing is not None):
            return
        now = time.monotonic()
        if now < self._speech_due:
            return
        self._speech_due = now + self.SPEECH_CHECK_EVERY
        if self.sapi_speaking(self.second_page()) != self.sapi_shown or self.engine_settled():
            self.reload_data()

    def engine_settled(self) -> bool:
        """PORT ADDITION (Android): an engine chosen in the engine row has started since the rows were made, so
        the row says Phone default again if the one chosen gave way to it."""
        if not system.ANDROID or not self.sapi_shown or self.page is None:
            return False
        return self.voice().settled != self._engine_settled

    # PORT ADDITION (user request, 2026-10-03): the rows below act on the speech whose page is open
    def second_page(self) -> bool:
        return self.page == 'second'

    def voice(self):
        """The voice of the speech whose page is open: SAPI 5's, the Mac's system voice or the phone's."""
        from ..platform.speech import Speech
        return Speech.shared().second_sapi if self.second_page() else Speech.shared().sapi

    def voice_config(self) -> dict:
        params = GameParameters.shared()
        return params.second_sapi_config() if self.second_page() else params.sapi_config()

    def set_voice(self, **changes) -> None:
        params = GameParameters.shared()
        if self.second_page():
            params.set_second_sapi(**changes)
        else:
            params.set_sapi(**changes)

    #: what the voice row says with no voice chosen
    CONTROL_PANEL_VOICE = 'System default' if system.MAC else 'Control Panel default'

    def sapi_rows(self, t, params, second: bool = False) -> None:
        """SAPI 5's voice, rate, rate boost (for a voice that has one), pitch and volume - the system voice's,
        on the Mac.  Each change is said in that voice itself, at the new setting, so it can be heard
        whatever else is speaking.  On the phone the engine takes the voice's place.  `second`: the second
        speech's voice, which has the same rows but Use modern output, one row for both."""
        from ..platform.speech import Speech
        sapi = Speech.shared().second_sapi if second else Speech.shared().sapi
        if sapi.voice is None:                            # no SAPI here (comtypes missing)
            return
        config = params.second_sapi_config() if second else params.sapi_config()
        if system.ANDROID:
            # PORT ADDITION (user request): the engine, by its name, and no voice row - each engine speaks with
            # the voice set in its own settings on the phone (2026-10-02)
            self._engine_settled = sapi.settled
            engine = params.second_speech_engine() if second else params.speech_engine()
            t.cell('Android speech engine',
                   dict(sapi.engines()).get(engine, engine) if engine else 'Phone default',
                   hint=("Which text-to-speech engine the second speech uses: Phone default, the one set in the "
                         "phone's settings, or any engine installed on the phone. Each engine speaks with the voice "
                         'set in its own settings. Press Enter for the list.' if second else
                         "Which text-to-speech engine speaks the game: Phone default, the one set in the phone's "
                         'settings, or any engine installed on the phone. Each engine speaks with the voice set '
                         'in its own settings. Press Enter for the list.'),
                   action=self.choose_speech_engine, shift_action=self.choose_speech_engine)
            voice = None
        else:
            names = dict(sapi.voices())
            t.cell(VOICE_NAME + ' voice', names.get(config['voice'], self.CONTROL_PANEL_VOICE),
                   hint='The voice %s speaks with: %s, or any installed voice. '
                        % (VOICE_NAME, VOICE_DEFAULT_HINT) + 'Press Enter for the list.',
                   action=self.choose_sapi_voice, shift_action=self.choose_sapi_voice)
            voice = config['voice'] if config['voice'] in names else None
        t.cell(VOICE_NAME + ' rate', str(sapi.rate()), hint='How fast %s speaks, from -10 to 10. ' % VOICE_NAME
               + ("At 0 it speaks at the speed set in the phone's text-to-speech settings. " if system.ANDROID else '')
               + self.SAPI_STEP_HINT,
               action=self.step_sapi_rate, shift_action=self.step_sapi_rate_back)
        if sapi.boost_supported(voice):
            t.cell(VOICE_NAME + ' rate boost', 'ON' if config['boost'] else 'OFF',
                   hint='Press Enter to toggle: when on, this voice speaks faster again than its rate.',
                   action=self.toggle_sapi_boost, shift_action=self.toggle_sapi_boost)
        t.cell(VOICE_NAME + ' pitch', str(config['pitch']), hint='How high %s speaks, from -10 to 10. ' % VOICE_NAME
                                                          + self.SAPI_STEP_HINT,
               action=self.step_sapi_pitch, shift_action=self.step_sapi_pitch_back)
        t.cell(VOICE_NAME + ' volume', '%d%%' % sapi.volume(), hint='How loud %s speaks. ' % VOICE_NAME + self.SAPI_STEP_HINT,
               action=self.step_sapi_volume, shift_action=self.step_sapi_volume_back)
        if not system.ANDROID and not second:             # the phone's voice is always played by the phone
            t.cell('Use modern output', 'ON' if params.modern_audio() else 'OFF',
                   hint='Press Enter to toggle: when on, the game plays %s itself, and a line stops the moment '
                        'you interrupt it. Turn it off to let Windows play it, which is slower to stop.'
                        % VOICE_NAME,
                   action=self.toggle_modern_audio, shift_action=self.toggle_modern_audio)

    # --- hints (PORT ADDITION, user request) ------------------------------------------------------
    @staticmethod
    def seconds_text(value: float) -> str:
        """A number of seconds as it is read: 1, 1.25, 0.5."""
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def row_said(self, title: str) -> str:
        """What the row whose English starts with `title` says now - said again as it changes, so the
        change is heard the way the row reads."""
        row = next((r for r in self.table_view.children if r.traits == CELL and r._label.startswith(title)),
                   None)
        return row.label if row is not None else title

    def toggle_hints(self) -> None:
        params = GameParameters.shared()
        params.set_speak_hints(not params.speak_hints())
        self.reload_data()
        self.announce('Hints %s' % ('ON' if params.speak_hints() else 'OFF'))

    def step_hint_pause(self, step: int = 1) -> None:
        params = GameParameters.shared()
        pauses = params.HINT_PAUSES
        i = max(0, min(len(pauses) - 1, pauses.index(params.hint_pause()) + step))   # the ends hold
        params.set_hint_pause(pauses[i])
        self.reload_data()
        self.announce(self.row_said('Pause before hints'))

    def step_hint_pause_back(self) -> None:
        self.step_hint_pause(-1)

    # --- speech calibration (PORT ADDITION, user request) ---------------------------------------
    def start_calibration(self) -> None:
        """Read the sample through the speech whose page is open, and time it until Enter (SpeechCalibration)."""
        params = GameParameters.shared()
        self.calibration.start(params.SECOND_SPEECH if self.second_page() else params.FIRST_SPEECH)

    def calibration_key(self, event) -> None:
        """Every key while a calibration is timing; the row says the pace once one is saved."""
        if self.calibration.key(event) is not None:
            self.reload_data()

    def ask_for_calibration(self, first: str, row: str = 'Speech output') -> None:
        """Ask for a Speech calibration over this screen, after `first`, as the game asks at start-up
        (SpeechCalibrationScreen); calibrated or skipped, back here to `row` - the Speech output row, or
        Reset all settings."""
        host = self.screen.host

        def back() -> None:
            host.dismiss_presented(asking)
            self.reload_data()
            self._focus_row(row)
        asking = SpeechCalibrationScreen(host, then=back, first=first)
        host.push_overlay(asking)

    def toggle_modern_audio(self) -> None:
        """PORT ADDITION: whether the game plays SAPI 5 itself (speech_audio.py) or Windows does."""
        from ..platform.speech import Speech
        params = GameParameters.shared()
        params.set_modern_audio(not params.modern_audio())
        Speech.shared().modern_audio_changed()            # off hands the voice back now, not next time
        self.reload_data()
        self.announce('Use modern output %s' % ('on' if params.modern_audio() else 'off'))
        self._sapi_say('This is how it sounds.')          # in that voice, through whichever plays it now

    def _sapi_say(self, text: str) -> None:
        """A change said by the voice being set, at its new setting, whatever else is speaking - and in the
        player's language, as Speech.speak says every other line of the tab.  Handed to the voice directly,
        these went out in English until 2026-10-02 (user request).  On the second speech's page, by the
        second speech's voice."""
        self.voice().speak(localization.translate(text), True)

    def choose_sapi_voice(self) -> None:
        """PORT ADDITION: the installed voices as a list (user request).  There are as many as the machine
        has - two hundred and fifty on the one this was written for - and stepping said every one of them
        on the way past."""
        voices = self.voice().voices()
        self.open_choices('%s voice' % VOICE_NAME, [(None, self.CONTROL_PANEL_VOICE)] + list(voices),
                          self.voice_config()['voice'], self.take_sapi_voice)

    def take_sapi_voice(self, voice_id) -> None:
        self.set_voice(voice=voice_id)
        names = dict(self.voice().voices())
        self._sapi_say('%s voice: %s' % (VOICE_NAME, names.get(voice_id, self.CONTROL_PANEL_VOICE)))

    def choose_speech_engine(self) -> None:
        """PORT ADDITION (Android, user request): the phone's text-to-speech engines as a list, the one set in
        the phone's settings first."""
        params = GameParameters.shared()
        engines = [(None, 'Phone default')] + list(self.voice().engines())
        self.open_choices('Android speech engine', engines,
                          params.second_speech_engine() if self.second_page() else params.speech_engine(),
                          self.take_speech_engine)

    def take_speech_engine(self, package) -> None:
        """The chosen engine.  The speech starts again with it, in the voice set in its own settings, and what
        is said meanwhile waits for it, so this is heard in the new engine.  One that would not start gives way
        to the phone's default, which the row then says (follow_speech, GameParameters.settle_speech_engine).
        The second speech's is said by the second speech, which starts it if it had not started yet."""
        from ..platform.speech import Speech
        names = dict(self.voice().engines())
        if self.second_page():
            GameParameters.shared().set_second_speech_engine(package)
            Speech.shared().speak_second('Android speech engine: %s'
                                         % (names.get(package, package) if package else 'Phone default'))
            return
        GameParameters.shared().set_speech_engine(package)
        self.announce('Android speech engine: %s' % (names.get(package, package) if package else 'Phone default'))

    def step_sapi_rate(self, step: int = 1) -> None:
        self.set_voice(rate=max(-10, min(10, self.voice().rate() + step)))   # the ends hold
        self.reload_data()
        self._sapi_say('%s rate %d' % (VOICE_NAME, self.voice().rate()))

    def step_sapi_rate_back(self) -> None:
        self.step_sapi_rate(-1)

    def toggle_sapi_boost(self) -> None:
        self.set_voice(boost=not self.voice_config()['boost'])
        self.reload_data()
        self._sapi_say('%s rate boost %s' % (VOICE_NAME, 'ON' if self.voice_config()['boost'] else 'OFF'))

    def step_sapi_pitch(self, step: int = 1) -> None:
        self.set_voice(pitch=max(-10, min(10, self.voice_config()['pitch'] + step)))
        self.reload_data()
        self._sapi_say('%s pitch %d' % (VOICE_NAME, self.voice_config()['pitch']))

    def step_sapi_pitch_back(self) -> None:
        self.step_sapi_pitch(-1)

    def step_sapi_volume(self, step: int = 1) -> None:
        self.set_voice(volume=max(0, min(100, self.voice().volume() + 10 * step)))
        self.reload_data()
        self._sapi_say('%s volume %d%%' % (VOICE_NAME, self.voice().volume()))

    def step_sapi_volume_back(self) -> None:
        self.step_sapi_volume(-1)

    def step_names_controller(self, step: int = 1) -> None:
        from ..platform.pad import Pads
        params = GameParameters.shared()
        models = Pads.shared().connected_models()
        current = params.names_controller()
        if len(models) < 2 or current is None:
            return
        params.set_names_controller(models[(models.index(current) + step) % len(models)])
        self.reload_data()
        self.announce('Controller for names: %s' % params.names_controller())

    def step_names_controller_back(self) -> None:
        self.step_names_controller(-1)

    def step_editing(self, step: int = 1) -> None:
        """Several kinds of controller connected: the next one's buttons, to see and set."""
        from ..platform.pad import Pads
        pads = Pads.shared()
        models = pads.connected_models()
        if len(models) < 2:
            return
        pads.editing = models[(models.index(pads.editing_model()) + step) % len(models)]
        self.reload_data()
        self.announce('%s, %d of %d' % (pads.editing, models.index(pads.editing) + 1, len(models)))

    def step_editing_back(self) -> None:
        self.step_editing(-1)

    def _pad_profile(self):
        """The bindings being shown and set: the controller chosen in the Controller row."""
        from ..platform.pad import PadMap, Pads
        model = self.pad_capturing_model or Pads.shared().editing_model()
        return PadMap.for_model(model) if model else None

    def capture_pad(self, action: str, replace: bool = False) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            self.announce('Connect a controller first.')
            return
        self.pad_capturing = action
        self.pad_capturing_replaces = replace
        self.pad_capturing_model = padmap.model           # the buttons go to this controller's profile
        self.announce('Press the button to %s %s, or Escape on the keyboard to keep %s'
                      % ('use instead of' if replace else 'add to', KeyMap.label(action), padmap.text(action)))

    def handle_captured_pad(self, name: str) -> None:
        """The next controller input while a button is being set."""
        action = self.pad_capturing
        if action is None:
            return
        padmap = self._pad_profile()
        if name in padmap.UNBINDABLE:
            why = ('Pushing a stick sideways turns' if name in ('stickleft', 'stickright')
                   else '%s is kept by %s' % (padmap.name_of(name), 'macOS' if system.MAC else 'Windows'))
            self.announce('%s. Press another button, or Escape to keep %s' % (why, padmap.text(action)))
            return
        replace = self.pad_capturing_replaces
        self.pad_capturing, self.pad_capturing_replaces, self.pad_capturing_model = None, False, None
        padmap.set(action, name) if replace else padmap.add(action, name)
        self.reload_data()
        self.announce('%s is now %s' % (KeyMap.label(action), padmap.text(action)))

    def cancel_pad_capture(self) -> None:
        padmap = self._pad_profile()
        action, self.pad_capturing, self.pad_capturing_replaces = self.pad_capturing, None, False
        self.pad_capturing_model = None
        if action is not None and padmap is not None:
            self.announce('%s keeps %s' % (KeyMap.label(action), padmap.text(action)))

    def remove_pad(self, action: str) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            return
        name = padmap.remove_last(action)
        if name is None:
            self.announce('%s keeps %s: an action needs at least one button'
                          % (KeyMap.label(action), padmap.text(action)))
            return
        self.reload_data()
        self.announce('%s removed from %s, now %s'
                      % (padmap.name_of(name), KeyMap.label(action), padmap.text(action)))

    def restore_pad(self) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            return
        padmap.restore_defaults()
        self.reload_data()
        self.announce('Default buttons restored for the %s, in both control schemes' % padmap.model)

    def toggle_menu_axis(self) -> None:
        params = GameParameters.shared()
        axes = [a for a, _text in params.MENU_AXES]
        axis = axes[(axes.index(params.menu_axis()) + 1) % len(axes)]
        params.set_menu_axis(axis)
        self.reload_data()
        self.announce('Menu layout %s' % self.menu_axis_text(axis))

    def capture_key(self, action: str, replace: bool = False) -> None:
        self.capturing = action
        self.capturing_replaces = replace
        keymap = KeyMap.shared()
        self.announce('Press the key to %s %s, or Escape to keep %s'
                      % ('use instead of' if replace else 'add to',
                         keymap.label(action), keymap.keys_text(action)))

    def handle_captured_key(self, code: int) -> bool:
        """The screen sends every key here while a binding is being set."""
        action, self.capturing = self.capturing, None
        replace, self.capturing_replaces = getattr(self, 'capturing_replaces', False), False
        if action is None:
            return False
        keymap = KeyMap.shared()
        if code == pygame.K_ESCAPE:
            self.announce('%s keeps %s' % (keymap.label(action), keymap.keys_text(action)))
            return True
        keymap.set_key(action, code) if replace else keymap.add_key(action, code)
        self.reload_data()
        self.announce('%s is now %s' % (keymap.label(action), keymap.keys_text(action)))
        return True

    def remove_key(self, action: str) -> None:
        """PORT ADDITION: Delete on a binding row takes off the key added last."""
        keymap = KeyMap.shared()
        name = keymap.remove_last_key(action)
        if name is None:
            self.announce('%s keeps %s: an action needs at least one key'
                          % (keymap.label(action), keymap.keys_text(action)))
            return
        self.reload_data()
        self.announce('%s removed from %s, now %s'
                      % (key_text(name), keymap.label(action), keymap.keys_text(action)))

    def restore_keys(self) -> None:
        KeyMap.shared().restore_defaults()
        self.reload_data()
        self.announce('Default keys restored in both control schemes')


@register('ADSettingsViewController')
class SettingsScreen(ViewControllerScreen):
    """ADSettingsViewController (tag-2781 view #54; the OK button #65 is labelled "OK")."""
    page_title = 'Settings'

    panel_title = 'Settings'                              # said when the panel takes the cursor

    def load_view(self) -> None:                          # 0x1000af3dc
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#54')
        self.control_scheme_view = View('', (30, 50, 508, 190), accessible=False, parent=v, name='#19')
        self.ok_button = Button('OK', (254, 245, 60, 50), parent=v, actions=[self.validate_button_pressed],
                                name='#65')
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x1000af1b8
        super().view_did_load()
        self.add_control_scheme_panel()
        sb = self.status_bar_view_controller
        sb.back_button.set_title('Main Menu')
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        pl = _headphones_playlist()
        if pl is not None:
            pl.activate()

    def add_control_scheme_panel(self) -> None:           # 0x1000af5b8
        f = self.control_scheme_view.frame
        self.control_scheme = ControlSchemePanel(self, self.view, (f[0] + f[2] / 2.0, f[1] + f[3] / 2.0))
        panel = self.control_scheme
        panel.focus_first_row('%s, %s. %s' % (self.panel_title, panel.category_keys_text(),
                                              dict(CATEGORIES)[panel.category]))

    def view_will_appear(self) -> None:                   # 0x1000af4e0
        self.status_bar_view_controller.back_button.hidden = False
        super().view_will_appear()

    # --- keys ------------------------------------------------------------------------------------
    def key_down(self, event) -> None:
        if self.control_scheme.calibration.timing is not None:   # PORT ADDITION: Speech calibration is timing
            self.control_scheme.calibration_key(event)
            return
        if self.control_scheme.capturing is not None:     # setting a binding: every key goes to the panel
            # PORT ADDITION: a controller button stands for a key in the menus; here it cancels, as Escape
            # does, rather than binding the key it stands for
            key = pygame.K_ESCAPE if getattr(event, 'pad', False) else event.key
            self.control_scheme.handle_captured_key(key)
            return
        panel = self.control_scheme
        if panel.pad_capturing is not None:               # PORT ADDITION: setting a controller button
            if not getattr(event, 'pad', False):
                if event.key == pygame.K_ESCAPE:
                    panel.cancel_pad_capture()
                else:
                    panel.announce('Press a button on the controller, or Escape to cancel')
            return
        if event.key == pygame.K_DELETE:                  # PORT ADDITION: take a key off the focused binding
            action = getattr(self.focus, 'binding_action', None)
            if action is not None:
                self.control_scheme.remove_key(action)
                return
            action = getattr(self.focus, 'pad_binding_action', None)
            if action is not None:
                self.control_scheme.remove_pad(action)
                return
        adjust = getattr(self.focus, 'adjust', None)      # PORT ADDITION: a slider takes the other swipes
        if adjust is not None and self.control_scheme.choosing is None and cross_axis_key(event) is not None \
                and not event.mod & JUMP_MODS:
            adjust(1 if event.key in (pygame.K_UP, pygame.K_RIGHT) else -1)
            return
        where = cross_axis_key(event)                     # PORT ADDITION: the other arrows change category
        if where is not None:
            if not self.control_scheme.on_a_page():       # while a row's list or a page is open, it has them
                self.control_scheme.move_category(where)
            return
        super().key_down(event)

    def frame(self) -> None:
        super().frame()
        self.control_scheme.follow_speech()               # PORT ADDITION: see there

    def on_dismiss(self) -> None:
        from ..platform.pad import Pads
        self.control_scheme._trigger_sample = None        # PORT ADDITION: no Trigger feel left on the pad
        self.control_scheme.stop_3d_test()                # nor Test 3D sound going round (2026-10-05)
        Pads.shared().set_triggers('off')
        super().on_dismiss()

    def pads_changed(self) -> None:
        """PORT ADDITION: a controller came or went.  The Joystick category names it and shows its
        buttons, and Miscellaneous names it or dims the choice, so they are laid out again; a button being
        set for a controller that has gone is given up."""
        from ..platform.pad import Pads
        panel = self.control_scheme
        if (panel.pad_capturing is not None
                and panel.pad_capturing_model not in Pads.shared().connected_models()):
            panel.cancel_pad_capture()
        if panel.category in ('joystick', 'misc'):
            panel.reload_data()

    # PORT ADDITION: while a controller button is being set, the host hands this screen the controller's
    # presses as they are, instead of the keys they stand for in a menu
    def takes_pad_input(self) -> bool:
        return self.control_scheme.pad_capturing is not None

    def pad_input(self, name: str) -> None:
        self.control_scheme.handle_captured_pad(name)

    # --- actions ---------------------------------------------------------------------------------
    def validate_button_pressed(self) -> None:            # 0x1000afa58
        self.host.dismiss_presented(self)

    # PORT ADDITION: a row's list of choices takes Escape and Back first, closing itself rather than the
    # screen - the armory does the same for an open weapon page (armory.accessibility_perform_escape)
    def accessibility_perform_escape(self) -> bool:
        if self.control_scheme.close_page():              # a row's list, or a speech's page (close_page)
            return True
        return super().accessibility_perform_escape()

    def back_button_pressed(self) -> None:                # 0x1000af948
        if self.control_scheme.close_page():
            return
        pl = _headphones_playlist()
        if pl is not None:
            pl.deactivate()
        App.delegate().go_to_main_menu()


@register('ADPauseViewController')
class PauseScreen(SettingsScreen):
    """ADPauseViewController (tag-2781 view #27): the settings panel plus Resume and End Game."""
    #: the pause screen is inside Play, but it is a fight rather than a menu: no coins, no diamonds
    shows_currencies = False
    page_title = 'Paused'

    panel_title = 'Paused'

    def __init__(self, host, pause_controller=None):
        super().__init__(host)
        self.pause = pause_controller

    def load_view(self) -> None:                          # 0x100055804
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#27')
        self.control_scheme_view = View('', (30, 45, 508, 210), accessible=False, parent=v, name='#66')
        self.resume_button = Button('Resume', (60, 263, 120, 40), parent=v,
                                    actions=[self.validate_button_pressed], name='#58')
        # PORT ADDITION: a challenge you have already lost - a missed time limit, an accuracy you cannot
        # get back - had to be played out or ended and then found again in the list.  It sits between the
        # two nib buttons, so the order read is Resume, Restart challenge, End Game: the least final
        # first and the most final last.  An endless game has no challenge to restart, so it is not built.
        if self.pause is not None and self.pause.challenge_dictionary() is not None:
            Button('Restart challenge', (196, 263, 150, 40), parent=v,
                   actions=[self.restart_button_touched], name='Restart challenge (port)')
        Button('End Game', (358, 263, 150, 40), parent=v, actions=[self.quit_button_touched], name='#29')
        self.first_accessible_element = self.resume_button
        # PORT ADDITION (Android, user request): the three-finger tap is only melee on the phone, so a line
        # of Dr. Bastard's is skipped from here.  It is first, because pausing just to skip is why you came.
        if system.ANDROID and self.pause is not None and self.pause.can_skip_dialogue():
            self.skip_button = Button('Skip dialogue', (60, 10, 150, 30), parent=v,
                                      actions=[self.skip_dialogue_touched], name='Skip dialogue (port)')
            self.first_accessible_element = self.skip_button
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x100055650
        super().view_did_load()                           # ADSettingsViewController (the panel posts last)
        sb = self.status_bar_view_controller
        sb.back_button.set_title('Resume')
        sb.set_currencies_visibility(False)
        if getattr(self, 'skip_button', None) is not None:   # PORT ADDITION: paused to skip, so start there
            self.post_screen_changed(self.skip_button)
        # loadMissionOverlay adds the mission bar at alpha 0
        pl = _headphones_playlist()
        if pl is not None:
            pl.activate()

    def view_will_appear(self) -> None:                   # 0x100055950: only [[self view] setNeedsLayout]
        if self.status_bar_view_controller is not None:
            self.status_bar_view_controller.view_will_appear()

    def validate_button_pressed(self) -> None:            # 0x100055bbc
        if self.pause is not None:
            self.pause.validate_button_pressed()
        else:
            self.host.dismiss_presented(self)

    def skip_dialogue_touched(self) -> None:              # PORT ADDITION (Android)
        if self.pause is not None:
            self.pause.skip_dialogue_touched()

    def restart_button_touched(self) -> None:             # PORT ADDITION
        # The same sound the challenge's own Play button makes (ADChallengeOverviewViewController
        # 0x1000d8b48) and the failed screen's Try again (0x100071ee8): a restart is a level starting,
        # and it should sound like one.  It is played here rather than beside the relaunch because the
        # relaunch waits for killGameplay's clean-up, and a level should start with this sound rather
        # than a fifth of a second after it.
        _play_buttons_sound('start_level_button')
        if self.pause is not None:
            self.pause.restart_button_touched()

    def quit_button_touched(self) -> None:                # 0x1000559c0
        if self.pause is not None:
            self.pause.quit_button_touched()

    def back_button_pressed(self) -> None:                # 0x1000559ac
        if self.control_scheme.close_page():              # PORT ADDITION: as on the settings screen
            return
        self.validate_button_pressed()


# ================================================================================= speech calibration
# PORT ADDITION (user request, 2026-10-02): the hints and the Extra mode's story are timed from a line's words
# (ui/reading.py), for every voice, at a pace the player measures.  The Speech tab's Speech calibration row
# measures it, and the game asks for it - at start-up, and after Reset all settings - until it has been.
def calibration_wanted() -> bool:
    """Whether the game asks for a Speech calibration: the speech has never been measured (`speechWordTime`),
    whatever speaks the game - a screen reader, SAPI 5, the Mac's system voice or the phone's.  Not while a
    chosen screen reader is not running, since then nothing could be heard: the game is silent until it
    is."""
    from ..platform.speech import Speech
    params = GameParameters.shared()
    return params.speech_word_time() is None and Speech.shared().can_speak(params.speech_output())


class SpeechCalibration:
    """One Speech calibration: a sample read through whatever speaks the game, timed until Enter, and the
    time a word saved or turned away (ui/reading.py).  The Speech tab's row runs it, and so does the screen
    that asks for one (SpeechCalibrationScreen)."""

    #: keys only ever held with another, which do not end a calibration by themselves - NVDA's own among them
    IGNORES = (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_LALT, pygame.K_RALT, pygame.K_LGUI, pygame.K_RGUI,
               pygame.K_CAPSLOCK, pygame.K_NUMLOCK, pygame.K_INSERT)

    def __init__(self, say):
        self.say = say                                    # how its lines are said
        self.timing = None                                # while the sample is read: (when, its words)
        self.speech = GameParameters.FIRST_SPEECH         # the speech being calibrated (`start`)

    @staticmethod
    def sample() -> str:
        """What is read to be timed: the one thing to do, then a sentence of the game's world - in the
        player's language, and in a controller's words when those are chosen.  Every word of it is counted."""
        from ..platform.pad import menu_words
        return menu_words(localization.translate(
            'Press Enter as soon as this ends. Somewhere past the fence a gate creaks open, the first footsteps '
            'come out of the dark, slow and uneven, and you check your clip and wait for them to come closer.'))

    def start(self, speech: str = GameParameters.FIRST_SPEECH) -> None:
        """Read the sample, and time it until Enter.  The second speech's is read by the second speech, with its
        own output, voice and settings (user request, 2026-10-03); what is said about it after is the first's,
        as everything in Settings is."""
        from ..platform.runloop import RunLoop
        from ..platform.speech import Speech
        from .reading import word_count
        self.speech = speech
        sample = self.sample()
        if speech == GameParameters.SECOND_SPEECH:
            Speech.shared().speak_second(sample)
        else:
            self.say(sample)
        self.timing = (RunLoop.main().now(), word_count(sample))

    def key(self, event):
        """Every key while the sample is timed.  Enter is the end of the reading; Escape, or any other key,
        cancels, since a key in the middle of the sentence may well have cut the reading short.  Returns the
        seconds a word once a pace has been saved, and None otherwise."""
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self.finish()
        if event.key not in self.IGNORES:
            self.cancel()
        return None

    def finish(self):
        from ..platform.runloop import RunLoop
        from .reading import measured_pace
        started, words = self.timing
        self.timing = None
        pace = measured_pace(RunLoop.main().now() - started, words)
        if pace == 'early':
            self.say('Too early: the sentence cannot have been read yet. Nothing was changed. Try again, and '
                     'press Enter as soon as the reading stops.')
            return None
        if pace == 'late':
            self.say('Too late: the sentence ended long before that. Nothing was changed. Try again, and '
                     'press Enter as soon as the reading stops.')
            return None
        GameParameters.shared().save_calibration(pace, self.speech)   # and Follow, as it says there
        self.say('Speech calibrated: %i words a minute.' % round(60.0 / pace))
        return pace

    def cancel(self) -> None:
        self.timing = None
        self.say('Calibration cancelled. Nothing was changed.')


@register('Port_SpeechCalibrationViewController')
class SpeechCalibrationScreen(MenuScreen):
    """The game asks for a Speech calibration (`calibration_wanted`), rather than leave the Speech tab's row
    saying "not done yet" to a player who may never open it.  It asks whatever speaks the game, on every
    platform, at start-up after the logo (and a first run's control scheme), before the opener
    (`App.go_to_opener`), and after Reset all settings; and when Speech output is changed with nothing
    measured (`ControlSchemePanel.take_speech_output`), which happens only when nothing could be heard at
    start-up.

    It says what the calibration is for and how it goes, and lands on Start calibration.  Enter starts it,
    and from there it is the Speech tab's own (`SpeechCalibration`): Enter at the end of the sentence, the
    result turned away when it is far too early or far too late, and any other key cancelling - after which
    it can be tried again.  It cannot be skipped (user request, 2026-10-02): skipped, the game went on timing
    the speech at a guessed pace, which is what the question is there to end.  Escape starts it as Enter
    does.  A pace saved is said, and the game goes on once that has
    been read: the next screen's first line would otherwise cut it off.  `then` is where it goes on to - the
    opener, or back to Settings."""

    #: seconds after the result has been read, at the pace just measured, before the game goes on
    GO_ON_MARGIN = 0.5

    def __init__(self, host, then=None, first: str = ''):
        from ..platform.pad import menu_words
        explanation = menu_words(localization.translate(
            'Speech calibration. The game works out when its speech has finished from how fast it reads, so that '
            'hints, and the story in Extra, come at the right moment. Press Enter to start: a sentence is read, '
            'and you press Enter again the moment it ends. It is needed once. Calibrate again in the Speech tab '
            'in Settings whenever you change the voice or its speed.'))
        super().__init__(host, title=joined([first, explanation]))   # `first`: what was said as it opened
        self.then = then if then is not None else App.delegate().go_to_main_menu
        self.calibration = SpeechCalibration(self.say)
        self.said = ''
        self.items = [MenuItem('Start calibration', self.start_pressed)]
        self.back_action = self.escape_pressed
        self.going_on = None                              # the result is being read: the timer that goes on
        self.gone = False

    def say(self, text: str) -> None:
        self.said = text
        self.speak(text)

    def start_pressed(self) -> None:
        self.calibration.start()
        play_button_click()

    def escape_pressed(self) -> None:
        """Not a way out: Escape starts the calibration as Enter does (user request, 2026-10-02).  A screen
        reader closed meanwhile leaves no one unable to hear it: Automatic goes over to SAPI 5, which reads
        the question and the sample instead."""
        self.start_pressed()

    def key_down(self, event) -> None:
        if self.gone:
            return
        if self.going_on is not None:                     # the result is being read: a key goes on at once
            if event.key not in SpeechCalibration.IGNORES:
                self.go_on()
            return
        if self.calibration.timing is not None:
            if self.calibration.key(event) is not None:
                self.calibrated()
            return
        super().key_down(event)

    def calibrated(self) -> None:
        """The pace is saved and said: go on once that has been read, timed by the pace just measured."""
        from ..platform.runloop import RunLoop
        from .reading import reading_seconds
        wait = reading_seconds(localization.translate(self.said)) + self.GO_ON_MARGIN
        self.going_on = RunLoop.main().schedule_timer(wait, self.go_on, False)

    def go_on(self) -> None:
        """On to the opener, or back to Settings, once calibrated."""
        if self.gone:
            return
        self.gone = True
        self.stop_waiting()
        self.then()

    def stop_waiting(self) -> None:
        if self.going_on is not None:
            self.going_on.invalidate()
            self.going_on = None

    def on_dismiss(self) -> None:
        self.stop_waiting()
        super().on_dismiss()
