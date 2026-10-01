"""PORT ADDITION: spoken text for the tutorial announcer.

The tutorial's announcer lines tell you which part of the phone to touch - tilt the device, swipe, tap the
corner button.  None of that exists on a keyboard, so a player following the audio is told to do something
they cannot do.  Each line is given an equivalent here, written for this port by the user, with the key
names filled in from the live key map: rebind Fire and the shoot line says the new key.  With a game
controller connected, and the player's choice in Settings -> Joystick, the same lines name its buttons
instead (``_pad_words``), and aiming gets a line of its own, since it is a stick rather than two keys -
and the buttons that turn as well, when there are any, by whatever they are bound to.

The brick scripts name these sounds with a placeholder - ``announcer_tutorial_aim_CONTROLMODE``,
``announcer_tutorial_shoot_BUTTONMODE`` - which ``ADSound.init_sound`` 0x1000b3594 resolves against the
control scheme and the button mode.  The resolved key comes back here, so ``aim_gyroMode``, ``aim_swipeMode``
and ``aim_tiltMode`` share one line, as do the button and gesture pairs.

``announcer_tutorial_aimhelp`` and ``announcer_tutorial_aimprompt`` have no line: they name no key, so there
is nothing for a keyboard player to be told differently.
"""
from __future__ import annotations

import logging
import re

from ..platform import host
from ..platform.keymap import KeyMap

log = logging.getLogger('game.tutorial')

PREFIX = 'announcer_tutorial_'

#: topic -> the line, with {action} standing for whatever that action is bound to now
LINES = {
    'aim': 'Use your {turn_left} or {turn_right} key to aim.',
    'shoot': 'Listen carefully and turn until you feel the zombie is right in front of you, '
             'then use the {fire} key to fire your weapon.',
    'reload': 'Use the {reload} key to reload your weapon.',
    'changeControl': 'You can change your aim control at any time in the pause menu, '
                     'which can be accessed using the {pause} key.',
    'switch': 'Use the {next_weapon} key to switch between weapons.',
    'skip': 'You can use the {skip} key to skip dialogs.',
    'melee': 'To use the melee weapon, turn to face the zombies first. Then, press the {melee} key.',
}

#: the suffixes ADSound.init_sound substitutes into the name
_MODE_SUFFIX = re.compile(r'_(gyro|swipe|tilt|button|gesture)Mode$')


def topic_for(sound_key: str):
    """'announcer_tutorial_shoot_buttonMode' -> 'shoot'; None for a sound that has no line."""
    if not sound_key or not sound_key.startswith(PREFIX):
        return None
    topic = _MODE_SUFFIX.sub('', sound_key[len(PREFIX):])
    return topic if topic in LINES else None


#: PORT ADDITION: with Settings -> Miscellaneous -> Names in hints and tutorial set to a controller, the
#: lines name its buttons instead - "the {fire} key" becomes "the R2 button", a flick of a stick "a stick
#: flicked up" (pad.button_words) - and aiming, which is a stick and not two keys, has a line of its own.
#: The buttons that turn are named after it, by what they are bound to now (user request); with neither of
#: them bound to anything the line is the sticks alone, as it was.
PAD_AIM = 'To aim, push either stick left or right.'
PAD_AIM_BUTTONS = '%s, or press %s.'
#: and under Gesture a controller that can feel movement swings the melee weapon when it is shaken, as the
#: phone did, so the melee line says so - on the controller that is being named, if that one can be shaken
PAD_SHAKE = ', or shake the controller'


#: PORT ADDITION (Android build): on a phone the lines name the touches, not keys - the same things the
#: announcer's own recordings ask for, in the words of this build's controls.  Aiming has a line per aim
#: control, and the others a line for gestures and one for Button mode (the four corners of the screen).
PHONE_AIM = {
    1: 'Hold the phone in front of you and turn your whole body to aim.',
    2: 'Swipe left or right with one finger to turn and aim.',
    3: 'Tilt the phone left or right to aim.',
}
PHONE_LINES = {
    'shoot': ('Listen carefully and turn until you feel the zombie is right in front of you, then tap the '
              'screen to fire, or touch and hold for continuous fire.'),
    'reload': 'Swipe down with one finger to reload your weapon.',
    'changeControl': ('You can change your aim control at any time in the pause menu. To pause, double '
                      "tap the Pause button at the top middle of the screen, or use the phone's Back."),
    'switch': 'Swipe up with one finger to switch between weapons.',
    'skip': 'To skip a dialog, pause the game, then choose Skip dialogue.',
    'melee': ('To use the melee weapon, turn to face the zombies first. Then tap with three fingers, '
              'or shake the phone.'),
}
PHONE_BUTTON_LINES = {
    'shoot': ('Listen carefully and turn until you feel the zombie is right in front of you, then tap the '
              'top right corner of the screen to fire, or touch and hold it for continuous fire.'),
    'reload': 'Tap the bottom right corner of the screen to reload your weapon.',
    'switch': 'Tap the bottom left corner of the screen to switch between weapons.',
    'melee': ('To use the melee weapon, turn to face the zombies first. Then tap the top left corner '
              'of the screen.'),
}
_PHONE_AIM_MODE = {'gyro': 1, 'swipe': 2, 'tilt': 3}


def phone_text_for(sound_key: str):
    """The line for this announcer sound on a phone, or None."""
    from .parameters import GameParameters
    topic = topic_for(sound_key)
    if topic is None:
        return None
    params = GameParameters.shared()
    if topic == 'aim':
        mode = _MODE_SUFFIX.search(sound_key)
        scheme = _PHONE_AIM_MODE.get(mode.group(1)) if mode else None
        return PHONE_AIM.get(scheme or params.control_scheme, PHONE_AIM[2])
    if params.button_mode and topic in PHONE_BUTTON_LINES:
        return PHONE_BUTTON_LINES[topic]
    return PHONE_LINES.get(topic)


def text_for(sound_key: str):
    """The line for this announcer sound, with the keys that are bound right now, or None - or, when the
    player has chosen a controller's names, with its buttons."""
    from ..platform.pad import button_words
    from .parameters import GameParameters
    topic = topic_for(sound_key)
    if topic is None:
        return None
    if host.ANDROID and not GameParameters.shared().controller_names():
        return phone_text_for(sound_key)
    keymap = KeyMap.shared()
    line = LINES[topic]
    params = GameParameters.shared()
    if params.controller_names():
        if topic == 'aim':
            turns = [words for words in (button_words('turn_left'), button_words('turn_right')) if words]
            return PAD_AIM_BUTTONS % (PAD_AIM.rstrip('.'), ' or '.join(turns)) if turns else PAD_AIM
        for action in set(re.findall(r'\{(\w+)\}', line)):
            words = button_words(action)
            if words is not None:                         # an action with no button keeps its key
                line = line.replace('the {%s} key' % action, words)
        if topic == 'melee' and not params.button_mode:
            from ..platform.pad import Pads
            model = params.names_controller()
            if model and Pads.shared().can_shake(model):
                line = line.rstrip('.') + PAD_SHAKE + '.'
    for action in set(re.findall(r'\{(\w+)\}', line)):
        line = line.replace('{%s}' % action, keymap.keys_text(action))
    return line
