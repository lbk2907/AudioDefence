"""Launch and menu screens: logo, first control scheme choice, main menu, play menu, info pages.

Each class ports its original controller method by method (addresses in the comments) on the iPhone nib's
tag-2781 layout (see viewcontroller.py).  Frames are the nib's absolute frames in points.
"""
from __future__ import annotations

import logging

from .. import localization
from ..app import App
from ..game import data
from ..game.parameters import GameParameters
from ..platform.runloop import RunLoop
from .accessibility import Button, View, play_button_click
from .host import AlertScreen, register
from .viewcontroller import NoBarScreen, ViewControllerScreen

log = logging.getLogger('ui.menus')


def _animate(duration: float, completion) -> None:
    """[UIView animateWithDuration:animations:completion:]: the completion runs when the animation ends."""
    RunLoop.main().call_later(duration, completion)


# ================================================================================================ logo
@register('ADLogoScreenViewController')
class LogoScreen(NoBarScreen):
    """ADLogoScreenViewController (nib: an image view only, nothing VoiceOver can reach)."""

    def load_view(self) -> None:                          # 0x10009ded4
        self.view = View('', (0, 0, 568, 320), accessible=False, name='#21')
        self.logo = View('', (0, 0, 568, 320), accessible=False, parent=self.view, name='#33 ADlogo_black')
        self.roots = [self.view]

    def view_did_load(self) -> None:                      # 0x10009de3c
        self.logo.alpha = 0.0

    def view_did_appear(self) -> None:                    # 0x10009def0
        super().view_did_appear()
        self.logo.alpha = 1.0

        def faded_in():                                   # viewDidAppear:_block_invoke_2 0x10009e068
            delay = 0.5 if self.host.screen_reader_running() else 2.0
            RunLoop.main().call_later(delay, self.move_to_opener)
        _animate(0.5, faded_in)

    def move_to_opener(self) -> None:                     # 0x10009e154
        self.logo.alpha = 0.0

        def faded_out():                                  # moveToOpener_block_invoke_2 0x10009e264
            if GameParameters.shared().control_scheme == -1:
                App.delegate().go_to_input_mode_select_screen()
            else:
                App.delegate().go_to_opener()
        _animate(0.5, faded_out)


# ================================================================================ first control scheme
@register('ADInitialControlSchemeViewController')
class InitialControlSchemeScreen(NoBarScreen):
    """ADInitialControlSchemeViewController."""
    page_title = 'Control scheme'

    def load_view(self) -> None:                          # 0x100006784 (view #156)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#156')
        View('AUDIO DEFENCE ZOMBIE ARENA', (8, 8, 552, 25), parent=v, name='#239')
        View("This game requires you to explore a 3D audio environment. Select a control mode you are "
             "confortable with. You'll be able to change it at any time in the Settings menu. For a more "
             "immersive experience, we recommend the GYRO mode", (0, 41, 568, 110), parent=v, name='#182')
        self.gyro_button = Button('Gyro', (32, 122, 129, 54), parent=v, actions=[self.gyro_control], name='#50')
        self.tilt_button = Button('Tilt', (220, 122, 129, 54), parent=v, actions=[self.tilt_control], name='#230')
        self.swipe_button = Button('Swipe', (420, 122, 129, 54), parent=v, actions=[self.button_control],
                                   name='#150')
        self.gyro_description = View('Turn to face the zombie holding the device in front of you',
                                     (15, 171, 150, 122), parent=v, name='#29')
        self.tilt_description = View('Tilt the device left or right to turn', (210, 171, 150, 122), parent=v,
                                     name='#144')
        self.swipe_description = View('Drag your finger across the screen to turn', (405, 171, 150, 122),
                                      parent=v, name='#179')
        self.recommeded_label = View('RECOMMENDED', (25, 291, 135, 21), parent=v, name='#108')
        # QUIRK (nib): the gyroTextButton outlet is connected to the Gyro button itself, and tiltTextButton,
        # swipeTextButton, descriptionText, titleLabel and subTitleLabel are not connected (nil).
        self.gyro_text_button = self.gyro_button
        self.tilt_text_button = None
        self.swipe_text_button = None
        self.description_text = None
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x100006030
        self.swipe_description.label = data.localized('SWIPE_DESCRIPTION')
        self.tilt_description.label = data.localized('TILT_DESCRIPTION')
        self.gyro_description.label = data.localized('GYRO_DESCRIPTION')
        if self.host.screen_reader_running():
            self.swipe_description.hidden = True
            self.tilt_description.hidden = True
            self.gyro_description.hidden = True
            # DIVERGENCE: the nib wires gyroTextButton to the Gyro button itself (tiltTextButton and
            # swipeTextButton are not connected at all), so hiding the "text buttons" here hid the Gyro
            # button - the recommended scheme, and the one a fresh profile starts on - leaving Tilt and
            # Swipe as the only choices on the one screen that exists to make that choice.  The three
            # descriptions above are still hidden; the button stays.
            if self.gyro_text_button is not self.gyro_button:
                self.gyro_text_button.hidden = True
            self.gyro_button.hint = data.localized('GYRO_DESCRIPTION')
            self.swipe_button.hint = data.localized('SWIPE_DESCRIPTION')
            self.tilt_button.hint = data.localized('TILT_DESCRIPTION')
        # [[self descriptionText] setText:INITIAL_PAGE_TEXT] goes to nil: the nib's text stays

    def tilt_control(self) -> None:                       # tiltControl: 0x1000067dc
        GameParameters.shared().set_control_scheme(3)
        self.go_to_main_menu()

    def gyro_control(self) -> None:                       # gyroControl: 0x100006868
        GameParameters.shared().set_control_scheme(1)
        self.go_to_main_menu()

    def button_control(self) -> None:                     # buttonControl: 0x1000068f4
        GameParameters.shared().set_control_scheme(2)
        self.go_to_main_menu()

    @staticmethod
    def go_to_main_menu() -> None:                        # 0x100006980 (it goes to the opener)
        App.delegate().go_to_opener()


# =========================================================================================== main menu
@register('ADMainMenuViewController')
class MainMenuScreen(ViewControllerScreen):
    """ADMainMenuViewController."""
    page_title = 'Main Menu'

    def load_view(self) -> None:                          # 0x100064b8c (view #65)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#65')
        self.sliding_view = View('', (142, 0, 284, 240), accessible=False, parent=v, name='#161 ADSlidingView')
        self.use_headphones = View('', (0, 0, 0, 0), accessible=False, parent=self.sliding_view,
                                   name='#57 frame_headphones')
        play = Button('Play', (197, 100, 172, 78), parent=self.sliding_view, actions=[self.play_button_pressed],
                      name='#154')
        # REMOVED (user request): the Game Center button #185 (leaderboardsButtonPressed: 0x100065964); Windows
        # has no Game Center
        Button('Info', (247, 283, 65, 41), parent=v, actions=[self.move_to_encyclopedia], name='#24')
        Button('Settings', (426, 281, 117, 41), parent=v, actions=[self.settings_button_touched], name='#79')
        # PORT ADDITION: the App Store updated the phone game, so the two buttons below it have no
        # counterpart in the nib.  This view is not a table, so the cursor follows the frames rather than
        # the order they are made in: both sit below the nib's buttons, and Quit below the other, to read
        # Play, Info, Settings, Check for updates, Quit.  Check for updates is here because the start-up
        # check is silent when there is nothing to report, and a player who hears nothing cannot tell that
        # from a thing that is not working.  Its hint is the version, which is the other thing a player
        # asking about updates wants to know.  Run from source there is nothing to update from - a
        # checkout moves with git - so the button is replaced by a line that says so.
        from .. import paths
        from ..platform import version
        if paths.FROZEN:
            updates = Button('Check for updates', (426, 330, 117, 41), parent=v,
                             actions=[self.check_for_updates], name='Check for updates (port)')
            updates.hint = 'Current version is %s.' % version.text()
        else:
            View('Updating is not available here. This is the source version, so it updates with git '
                 'rather than from a release.', (426, 330, 117, 41), parent=v, name='No updates (port)')
        # PORT ADDITION: iOS has no Quit.
        Button('Quit', (426, 379, 117, 41), parent=v, actions=[self.quit_button_pressed], name='Quit (port)')
        self.cheat_menu = Button('', (191, 240, 187, 33), parent=v, actions=[self.cheat_button_pressed],
                                 name='#148')
        self.cheat_menu.label = self.cheat_menu.text = 'CHEAT'
        self.full_moon_view = None                        # outlets not connected in the iPhone nib
        self.version_number_label = None
        self.first_accessible_element = play
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x100064634
        super().view_did_load()
        from ..game.modifiers import GameModifiers
        _ = GameModifiers.shared().fullMoon               # [fullMoonView setHidden:] goes to nil
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.delegate = self
        sb.back_button.hidden = True
        self.cheat_menu.hidden = True
        # versionNumberLabel is nil; ADTracker / Google Analytics calls are not ported
        RunLoop.main().add_observer(self, 'AD_MESSAGE_AudioRouteChanged', lambda *_: self.audio_route_changed())
        self.audio_route_changed()
        # PORT ADDITION: the App Store updated the phone game; on Windows the main menu looks for a new
        # build itself.  It runs on a worker thread and says nothing unless there is one to offer.
        from .updates import check_on_start
        check_on_start(self.host, self)

    def dealloc(self) -> None:
        RunLoop.main().remove_observer(self)
        super().dealloc()

    def quit_button_pressed(self) -> None:                # PORT ADDITION
        self.host.quit_game()

    def check_for_updates(self) -> None:                  # PORT ADDITION
        from .updates import check_now
        check_now(self.host, self.speak)

    def armory_button_pressed(self) -> None:              # armoryButtonPressed: 0x100064fb0 (no button uses it)
        App.delegate().present_view_controller_named(self, 'ADArmoryViewController')

    def cheat_button_pressed(self) -> None:               # cheatButtonPressed: 0x100065044
        App.delegate().present_view_controller_named(self, 'ADCheatViewController')

    def play_button_pressed(self) -> None:                # playButtonPressed: 0x1000650d8
        if GameParameters.shared().is_headset_plugged_in():
            App.delegate().go_to_play_menu()
            return
        self.host.push_overlay(AlertScreen(self.host, data.localized('ALERT_TITLE'), data.localized('ALERT_CONTENT'),
                                           [('OK', self._alert_ok)]))

    def _alert_ok(self) -> None:                          # alertView:willDismissWithButtonIndex: 0x100065560
        App.delegate().go_to_play_menu()

    def settings_button_touched(self) -> None:            # settingsButtonTouched: 0x100065360
        App.delegate().present_view_controller_named(self, 'ADSettingsViewController')

    def move_to_encyclopedia(self) -> None:               # moveToEncyclopedia: 0x1000653f4
        App.delegate().present_view_controller_named(self, 'ADStatsPortalViewController')

    def audio_route_changed(self) -> None:                # 0x100065488
        self.use_headphones.hidden = GameParameters.shared().is_headset_plugged_in()

    # REMOVED (user request): the magic tap 0x100065d40 pressed Play.


# =========================================================================================== extra
@register('Port_ExtraMenuViewController')
class ExtraMenuScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the chapters of arenas the port wrote, which the original has no
    screen for.

    It is built like the play menu rather than like their world list, which is a table of worlds read out
    of `challenges_index` - and these are deliberately not worlds in that file, because `totalStarsUnlocked`
    0x10001ecd4 sums every world in it and gates theirs on the answer (`additions.CHAPTERS` says why).  One
    button a chapter, Back to the play menu.

    A chapter opens on stars, the way one of their worlds does, and the row says where a player stands:
    "Chapter 1, 3 of 21 stars", or "Chapter 2, locked, 12 stars needed".  A locked button does nothing and
    says nothing when pressed, which is what their selector's locked rows do.
    """
    page_title = 'Extra'

    def load_view(self) -> None:
        from ..game.additions import CHAPTERS
        from ..game.challenge_data import ChallengeData
        cd = ChallengeData.shared()
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='extraMenu')
        self.buttons = []
        for i, (chapter, _stars, _arenas) in enumerate(CHAPTERS):
            open_now = cd.chapter_is_open(chapter)
            b = Button(chapter, (192, 34 + i * 38, 187, 34), parent=v, font_button=open_now,
                       actions=[lambda c=chapter: self.chapter_chosen(c)] if open_now else (),
                       name='extra %s' % chapter)
            # What is drawn stays the chapter's name; what is read is the name and where the player stands
            # with it, because on this screen there is nothing else to say it.
            if open_now:
                b.label = '%s, %i of %i stars' % (chapter, cd.stars_unlocked_for_chapter(chapter),
                                                  cd.stars_available_in_chapter(chapter))
                b.hint = 'Press Enter to open this chapter.'
            else:
                # Which of the two things is missing, because "locked" on its own gives a player nothing to
                # work on.  The arenas come first when both are short: they are the longer job, and finishing
                # them pays a star each, so that is the way out of either.
                # PORT INPUT: their world list says "You need %i stars to play this level"
                # Both forms of each phrase go to `translate` rather than an 's' being stuck on the end
                # of one: a language whose plural does not work that way needs to be handed both.
                left = cd.arenas_left_before_chapter(chapter)
                if left:
                    reason = '%i %s' % (left, localization.translate(
                        'arena still to beat before this chapter' if left == 1 else
                        'arenas still to beat before this chapter'))
                else:
                    short = cd.stars_left_before_chapter(chapter)
                    reason = '%i %s' % (short, localization.translate(
                        'more star needed' if short == 1 else 'more stars needed'))
                b.label = '%s, locked, %s' % (chapter, reason)
            self.buttons.append(b)
        if self.buttons:
            self.first_accessible_element = self.buttons[0]
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Play')

    @staticmethod
    def chapter_chosen(chapter: str) -> None:
        App.delegate().go_to_extra_chapter(chapter)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_play_menu()


@register('Port_ExtraChapterViewController')
class ExtraChapterScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the arenas of one chapter.

    One button an arena, and the status each reads out is the one their accessible selector gives -
    `locked`, or how many of its three stars are won (`statusForChallengeWithDict:` 0x100054960) - because
    inside a chapter each arena names the one before it in `challenges_requirement`, the original's own key.
    What the arenas are is in `additions.PLISTS`, read by name through `data.plist` exactly as theirs are.
    """
    def __init__(self, host, chapter: str = ''):
        super().__init__(host)
        self.chapter = chapter
        self.page_title = chapter or 'Extra'

    def load_view(self) -> None:
        from ..game.additions import chapter_arenas
        from .challenges import AccessibleChallengeSelectorScreen
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='extraChapter')
        self.buttons = []
        for i, name in enumerate(chapter_arenas(self.chapter)):
            d = data.plist(name) or {}
            title = str(d.get('title') or name)
            status = AccessibleChallengeSelectorScreen.status_for_challenge_with_dict(d)
            locked = status == 'locked'
            # Seven of them in a view 320 points tall, so they sit closer together than the play menu's
            # buttons do.  One column: `reading_order` sorts by a frame's vertical centre, and a column is
            # the order they unlock in.
            b = Button(title, (192, 34 + i * 38, 187, 34), parent=v, font_button=not locked,
                       actions=() if locked else [lambda n=name: self.challenge_chosen(n)],
                       name='extra %s' % name)
            b.label = '%s, %s' % (title, status)
            b.hint = None if locked else str(d.get('objective') or '')
            self.buttons.append(b)
        if self.buttons:
            self.first_accessible_element = self.buttons[0]
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Extra')

    @staticmethod
    def challenge_chosen(name: str) -> None:
        """PORT ADDITION (user request): the challenge's own overview first, as the selector gives.

        `ADChallengeOverviewViewController` 0x1000d8178 takes a challenge dictionary and reads out its
        title, what it asks of you, its tip and its three stars, with Play at the bottom - and it tells a
        player who has not bought one of its guns to go and buy it.  A challenge of the port's is a
        challenge dictionary like any other, so it gets all of that for nothing.
        """
        app = App.delegate()
        # The accessible overview whether a screen reader is running or not: the sighted one is a nib the
        # port never ported, so asking for it hands back a placeholder and a dead end.  This screen is
        # views like any other and reads the same dictionary.
        app.go_to_accessible_challenge_overview_with_dictionary(
            App.dictionary_for_challenge_with_name(name))

    def back_button_pressed(self) -> None:
        App.delegate().go_to_extra_menu()


# =========================================================================================== play menu
@register('ADPlayMenuViewController')
class PlayMenuScreen(ViewControllerScreen):
    """ADPlayMenuViewController."""
    page_title = 'Play'
    #: the coins and the diamonds belong to what is under this menu - challenge, endless, whatever is added
    #: later - and not to the choice between them (user request; StatusBar._wanted)
    shows_currencies = False

    def __init__(self, host, should_animate: bool = False):   # initWithNibName:bundle:shouldAnimate: 0x1000aafe8
        super().__init__(host)
        self.animate_check = should_animate

    def load_view(self) -> None:                          # 0x1000ab45c (view #157)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#157')
        self.sliding_view = View('', (142, 0, 284, 291), accessible=False, parent=v, name='#53 ADSlidingView')
        s = self.sliding_view
        challenge = Button('Challenge', (192, 114, 187, 46), parent=s, actions=[self.challenge_button_touched],
                           name='#232')
        self.endless_mode_button = Button('Endless', (212, 168, 149, 46), parent=s,
                                          actions=[self.endless_mode_button_touched], name='#146')
        self.endless_mode_lock_view = View('', (200, 206, 180, 70), accessible=False, parent=s, name='#242')
        View('Finish 5 challenges to unlock this mode', (200, 206, 180, 70), parent=self.endless_mode_lock_view,
             name='#181')
        # PORT ADDITION (user request): Extra, where the challenges the port wrote itself live.  Its frame
        # puts it after Endless and before the two info buttons, `reading_order` sorting by the vertical
        # centre of a frame: 168+46/2 is Endless at 191, and this is at 237.
        self.extra_button = Button('Extra', (212, 222, 149, 30), parent=s,
                                   actions=[self.extra_button_touched], name='extraButton')
        self.challenge_info_button = Button('Challenge Info', (373, 126, 22, 22), parent=s, font_button=False,
                                            actions=[self.challenge_info_button_pressed], name='#186')
        # PORT ADDITION (user request): an info button for Extra, as Challenge and Endless have.  Its
        # frame shares Extra's vertical centre (222 + 30/2 = 237) and sits to the right of it, which is
        # what puts it straight after Extra: `reading_order` sorts by vertical centre and then by x.
        self.extra_info_button = Button('Extra Info', (373, 226, 22, 22), parent=s, font_button=False,
                                        actions=[self.extra_info_button_pressed], name='extraInfoButton')
        self.endless_info_button = Button('Endless Info', (357, 177, 22, 22), parent=s, font_button=False,
                                          actions=[self.endless_info_button_pressed], name='#131')
        self.first_accessible_element = challenge
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x1000ab0c4
        super().view_did_load()
        from ..game.challenge_data import ChallengeData
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Main Menu')
        if ChallengeData.shared().has_completed_challenge_with_name('tutorial_5'):
            self.endless_mode_lock_view.hidden = True
            return
        self.endless_mode_button.enabled = False
        self.endless_mode_lock_view.hidden = False
        self.endless_mode_button.hint = 'Finish the tutorial to unlock'
        self.endless_mode_button.label = 'Endless mode is locked'
        self.endless_info_button.hidden = True

    def endless_mode_button_touched(self) -> None:        # endlessModeButtonTouched: 0x1000ab744
        from ..game.persistent_stats import PersistentStats
        if PersistentStats.shared().high_score() >= 1:
            App.delegate().go_to_tarot()
            return
        PersistentStats.shared().save_score(1)
        self.endless_info_button_pressed()

    @staticmethod
    def challenge_button_touched() -> None:               # challengeButtonTouched: 0x1000ab8c8
        App.delegate().go_to_world_selector()

    @staticmethod
    def extra_button_touched() -> None:                   # PORT ADDITION: see load_view
        App.delegate().go_to_extra_menu()

    def back_button_pressed(self) -> None:                # 0x1000ab96c
        App.delegate().go_to_main_menu()

    @staticmethod
    def challenge_info_button_pressed() -> None:          # challengeInfoButtonPressed: 0x1000abb08
        play_button_click()
        App.delegate().go_to_info_screen('challenge')

    @staticmethod
    def endless_info_button_pressed() -> None:            # endlessInfoButtonPressed: 0x1000abbc4
        play_button_click()
        App.delegate().go_to_info_screen('endless')

    @staticmethod
    def extra_info_button_pressed() -> None:              # PORT ADDITION (user request): see load_view
        play_button_click()
        App.delegate().go_to_info_screen('extra')

    # REMOVED (user request): the magic tap 0x1000abc80 pressed Endless once tutorial_5 had been
    # completed, and Challenge before that.


# ================================================================================================ info
@register('ADInfoViewController')
class InfoScreen(ViewControllerScreen):
    """ADInfoViewController (nib ADInfoViewController: no Accessible_ variant exists)."""
    page_title = 'Info'

    #: the two buttons that reach this screen are "Challenge Info" and "Endless Info", so the screen says
    #: which one you opened rather than the original's bare "INFO"
    PAGE_TITLES = {'challenge': 'Challenge Info', 'endless': 'Endless Info',
                   'extra': 'Extra Info'}                    # PORT ADDITION (user request)

    def __init__(self, host, page_name: str = ''):       # initWithPageName: 0x100039738
        super().__init__(host)
        self.page_name = page_name
        self.page_title = self.PAGE_TITLES.get(page_name, 'Info')

    def load_view(self) -> None:                          # UIViewController loadView (view #85)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#85')
        self.title_label = View('Mission', (60, 85, 448, 21), parent=v, name='#18')
        self.info_text_view = View(
            'Lorem ipsum dolor sit er elit lamet, consectetaur cillium adipisicing pecu, sed do eiusmod tempor '
            'incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco '
            'laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate '
            'velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt '
            'in culpa qui officia deserunt mollit anim id est laborum. Nam liber te conscient to factor tum poen '
            'legum odioque civiuda.', (60, 114, 448, 131), parent=v, name='#89')
        self.continue_button = Button('Play', (234, 260, 100, 60), parent=v,
                                      actions=[self.continue_button_pressed], name='#58')
        self.info_title = None                            # infoTitle and armoryButton outlets are not connected
        self.armory_button = None
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x1000397e4
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        if self.page_name == 'challenge':
            self.title_label.label = data.localized('CHALLENGE_INFO_TITLE')
            self.info_text_view.label = data.localized('CHALLENGE_INFO_TEXT')
        elif self.page_name == 'endless':
            self.info_text_view.label = data.localized('ENDLESS_INFO_TEXT')
            self.title_label.label = data.localized('ENDLESS_INFO_TITLE')
        elif self.page_name == 'extra':
            # PORT ADDITION (user request): the original has no Extra, so it has no strings for one.  The
            # words are here rather than in `Localizable.strings`, which is theirs, and each goes to
            # `translate` on its own so the localization walk collects it.
            self.title_label.label = localization.translate('EXTRA MODE')
            self.info_text_view.label = localization.translate(
                'Arenas written for this version of the game, in chapters. Each one opens when the one '
                'before it is beaten, and none of them tells you how it is won.\n \nThey use the '
                'weapons they hand you, and the stars you earn here open the chapters that follow.')
        # [[self view] bringSubviewToFront:statusBar view] does not change the reading order

    def continue_button_pressed(self) -> None:            # continueButtonPressed: 0x100039f94
        if self.page_name == 'challenge':
            App.delegate().go_to_tabbed_challenge_screen()
        elif self.page_name == 'endless':
            App.delegate().go_to_tarot()
        elif self.page_name == 'extra':                   # PORT ADDITION (user request)
            App.delegate().go_to_extra_menu()

    def back_button_pressed(self) -> None:                # 0x10003a0f8
        App.delegate().go_to_play_menu()
