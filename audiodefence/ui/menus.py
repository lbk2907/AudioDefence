"""Launch and menu screens: logo, first control scheme choice, main menu, play menu, info pages.

Each class ports its original controller method by method (addresses in the comments) on the iPhone nib's
tag-2781 layout (see viewcontroller.py).  Frames are the nib's absolute frames in points.
"""
from __future__ import annotations

import logging
import os
import random

from .. import localization
from ..app import App
from ..game import data
from ..game.parameters import GameParameters
from ..platform.defaults import ns_int_value
from ..platform.runloop import RunLoop
from .accessibility import Button, View, play_button_click
from .host import AlertScreen, ask_for_text, register
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
        # checkout moves with git - so the button is replaced by a line that says so.  The Android app is
        # not frozen but updates all the same, by handing a newer app to Android (platform/updater_android.py).
        from .. import paths
        from ..platform import host as host_platform
        from ..platform import version
        if paths.FROZEN or host_platform.ANDROID:
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
    """PORT ADDITION (user request, 2026-10-01): the campaigns of arenas the port wrote, which the original
    has no screen for.  Extra is to hold more than one collection of arenas in time, so it opens on a list
    of them (`additions.CAMPAIGNS`), even while there is one; each opens its chapters.

    One button a campaign, Back to the play menu.  A campaign is always open, and its row says where a
    player stands with it as a chapter's row does: "The Long Way Home, 30 of 147 stars".
    """
    page_title = 'Extra'

    def load_view(self) -> None:
        from ..game.additions import CAMPAIGNS
        from ..game.challenge_data import ChallengeData
        cd = ChallengeData.shared()
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='extraMenu')
        self.buttons = []
        for i, (campaign, _chapters) in enumerate(CAMPAIGNS):
            b = Button(campaign, (192, 34 + i * 38, 187, 34), parent=v,
                       actions=[lambda c=campaign: self.campaign_chosen(c)], name='extra %s' % campaign)
            # Handed to `translate` so the localization tools offer the two lines: they read calls, not
            # assignments.
            b.label = localization.translate('%s, %i of %i stars' % (
                campaign, cd.stars_unlocked_for_campaign(campaign), cd.stars_available_in_campaign(campaign)))
            b.hint = localization.translate('Press Enter to open this campaign.')
            self.buttons.append(b)
        if self.buttons:
            self.first_accessible_element = self.buttons[0]
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        # PORT ADDITION (user request, 2026-10-01): the status bar's Armory, on this screen and the two
        # under it, as the tarot screen and the challenge overview show it: the armory opens over the
        # screen (`go_to_armory`, the status bar's delegate) and closes back onto it.  It is read where it
        # is on theirs, in the top row after Back and the coins and diamonds, before the first row below,
        # which is where the cursor starts.
        sb.set_armory_button_visibility(True)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Play')

    @staticmethod
    def campaign_chosen(campaign: str) -> None:
        App.delegate().go_to_extra_campaign(campaign)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_play_menu()


@register('Port_ExtraCampaignViewController')
class ExtraCampaignScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the chapters of one campaign.

    It is built like the play menu rather than like their world list, which is a table of worlds read out
    of `challenges_index` - and these are deliberately not worlds in that file, because `totalStarsUnlocked`
    0x10001ecd4 sums every world in it and gates theirs on the answer (`additions.CHAPTERS` says why).  One
    button a chapter, Back to the campaigns.

    A chapter opens on stars won in its own campaign, the way one of their worlds does, and the row says
    where a player stands: "Chapter 1, 3 of 21 stars", or "Chapter 2, You need 19 stars to play this level".
    A locked button does nothing and says nothing when pressed, which is what their selector's locked rows
    do.
    """
    def __init__(self, host, campaign: str = ''):
        super().__init__(host)
        self.campaign = campaign
        self.page_title = campaign or 'Extra'

    def load_view(self) -> None:
        from ..game.additions import campaign_chapters, chapter_stars_required
        from ..game.challenge_data import ChallengeData
        cd = ChallengeData.shared()
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='extraCampaign')
        self.buttons = []
        for i, (chapter, _arenas) in enumerate(campaign_chapters(self.campaign)):
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
                # Their world list's own words for a locked world (user request): "Maya Ruin, You need 40
                # stars to play this level" (ui/challenges.py, the world selector), so a chapter reads as
                # one of their worlds does, and a language file that has the line already translates it.
                b.label = '%s, %s' % (chapter, 'You need %i stars to play this level'
                                      % chapter_stars_required(chapter))
            self.buttons.append(b)
        # PORT ADDITION (user request): the arenas a *player* has written, under the chapters the port
        # wrote.  One row, because what is behind it is a list that grows: the folder beside the
        # executable can hold any number of arenas, and the Challenge maker is there to add to it.  Their
        # stars are counted on the far side of this row and nowhere else - `chapter_is_open` above asks
        # `total_stars_unlocked_for_chapters`, which walks `CHAPTERS` and so never sees one of them.
        self.custom_button = Button('Custom', (192, 34 + len(CHAPTERS) * 38, 187, 34), parent=v,
                                    actions=[self.custom_chosen], name='extra Custom')
        self.buttons.append(self.custom_button)
        self.read_out_custom()
        if self.buttons:
            self.first_accessible_element = self.buttons[0]
        self.roots = [v]

    def read_out_custom(self) -> None:
        """What the Custom row says: how many challenges are in the folder, or that there are none.

        Two whole sentences rather than one with a plural glued into it, as the Zombiepedia's unlock line
        is written (`EncyclopediaItemView.load_view`): a translator is offered each of them complete.
        """
        from ..game import custom
        found = sum(len(ids) for _title, ids in custom.arenas())
        if found == 1:
            self.custom_button.label = 'Custom, one challenge'
        elif found:
            self.custom_button.label = 'Custom, %i challenges' % found
        else:
            self.custom_button.label = 'Custom, nothing made yet'
        self.custom_button.hint = ('Press Enter to open the challenges you have made.' if found else
                                   'Press Enter to open the Challenge maker.')

    def view_will_appear(self) -> None:
        # Counted again on the way back in: the maker is one screen down from here, and a challenge
        # generated there changes what this row says.
        super().view_will_appear()
        self.read_out_custom()

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)             # PORT ADDITION: see ExtraMenuScreen
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Extra')

    @staticmethod
    def chapter_chosen(chapter: str) -> None:
        App.delegate().go_to_extra_chapter(chapter)

    @staticmethod
    def custom_chosen() -> None:                          # PORT ADDITION (user request)
        App.delegate().go_to_custom_menu()

    def back_button_pressed(self) -> None:
        App.delegate().go_to_extra_menu()


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
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='extraChapter')
        self.buttons = []
        self.arenas = list(chapter_arenas(self.chapter))
        for i, name in enumerate(self.arenas):
            d = data.plist(name) or {}
            # Seven of them in a view 320 points tall, so they sit closer together than the play menu's
            # buttons do.  One column: `reading_order` sorts by a frame's vertical centre, and a column is
            # the order they unlock in.  No click of their own: `challenge_chosen` makes one on the paths
            # that go somewhere, as the selector's rows do.
            b = Button(str(d.get('title') or name), (192, 34 + i * 38, 187, 34), parent=v, font_button=False,
                       actions=[lambda n=name: self.challenge_chosen(n)], name='extra %s' % name)
            self.buttons.append(b)
        self.read_out_arenas()
        if self.buttons:
            self.first_accessible_element = self.buttons[0]
        self.roots = [v]

    def read_out_arenas(self) -> None:
        """What each row says: its title and the status the accessible selector gives (0x100054960).

        Done again whenever the screen comes back, because the armory is presented over it: a player sent
        there to buy a gun comes back to a row whose status has changed under it."""
        from .challenges import AccessibleChallengeSelectorScreen
        for name, b in zip(self.arenas, self.buttons):
            d = data.plist(name) or {}
            status = AccessibleChallengeSelectorScreen.status_for_challenge_with_dict(d)
            b.label = '%s, %s' % (str(d.get('title') or name), status)
            # on the phone a locked row goes on to name the arena that opens it (statusForChallengeWithDict)
            b.hint = None if status.startswith('locked') else str(d.get('objective') or '')

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.read_out_arenas()

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)             # PORT ADDITION: see ExtraMenuScreen
        sb.set_currencies_visibility(False)
        # Back names where it goes, as every Back does: the campaign this chapter is in
        from ..game.additions import campaign_of
        sb.back_button.set_title(campaign_of(self.chapter) or 'Extra')

    def challenge_chosen(self, name: str) -> None:
        """PORT ADDITION (user request): what the selector's `tableView:didSelectRowAtIndexPath:` 0x100054f8c
        does with a row, in the same order.

        A gun not bought goes to the armory, which is what the row has just said it will do ("Hunting Rifle
        required, press Enter to go to armory").  A locked arena does nothing and says nothing.  Anything
        else opens the challenge's own overview (`ADChallengeOverviewViewController` 0x1000d8178), which
        reads out its title, what it asks of you, its tip and its three stars, with Play at the bottom.

        The order is the point.  This used to open the overview for every row that was not `locked` - and a
        row that wants a gun reads as the gun and not as `locked`, whether or not the arena before it has
        been beaten.  The overview only asks about guns (0x10003e980), since the original never shows it for
        a locked challenge, so a player could open an arena three places ahead, buy its gun from the
        overview's own armory button and play it (2026-09-28).  Big Game and The Last Word had that hole
        from the start; chapter 4, where four arenas of six want a gun bought, is what made it matter.
        """
        from ..game.challenge_data import ChallengeData
        from ..game.inventory import Inventory
        d = App.dictionary_for_challenge_with_name(name) or {}
        for w in d.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                play_button_click()
                App.delegate().go_to_armory(self, False)
                return
        if not ChallengeData.shared().has_challenge_requirements_for_challenge_with_name(name):
            return
        play_button_click()
        # The accessible overview whether a screen reader is running or not: the sighted one is a nib the
        # port never ported, so asking for it hands back a placeholder and a dead end.  This screen is
        # views like any other and reads the same dictionary.
        App.delegate().go_to_accessible_challenge_overview_with_dictionary(d)

    def back_button_pressed(self) -> None:
        from ..game.additions import campaign_of
        campaign = campaign_of(self.chapter)
        if campaign is None:
            App.delegate().go_to_extra_menu()
        else:
            App.delegate().go_to_extra_campaign(campaign)


# ================================================================================= custom challenges
@register('Port_CustomMenuViewController')
class CustomMenuScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the arenas a player has written, and the Challenge maker.

    An arena here is a `.adpack` in the challenges folder beside the executable, or the gathering of the
    loose `.adchallenge` files in it (`game/custom.py` says what a file looks like).  It is built like the
    Extra screen above rather than like their world list, and for the same reason: `challenges_index` is
    Somethin' Else's file, `totalStarsUnlocked` 0x10001ecd4 sums every world in it, and a player who
    generated twenty arenas would otherwise have opened City Crossroad and Maya Ruin without playing either.

    Nothing here is locked.  A chapter of the port's opens on stars because the chapters are an order
    somebody decided on; these are in no order at all, and an arena a player made to play is an arena they
    should be able to play.
    """
    page_title = 'Custom'

    def load_view(self) -> None:
        from ..game import custom
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='customMenu')
        self.arenas = [title for title, _ids in custom.arenas()]
        self.buttons = []
        for i, title in enumerate(self.arenas):
            # A click of its own, unlike a chapter's arenas: every row here opens something, so none of
            # them is the silent "nothing happened" a locked row is.
            b = Button(title, (192, 34 + i * 34, 187, 30), parent=v,
                       actions=[lambda t=title: self.arena_chosen(t)], name='custom %s' % title)
            self.buttons.append(b)
        # Under the arenas, wherever they end: the maker is what adds to the list above it, so it is read
        # after the list rather than before it, the way Extra's own rows come before Custom.
        self.maker_button = Button('Challenge maker', (192, 34 + len(self.arenas) * 34 + 8, 187, 30),
                                   parent=v, actions=[self.maker_chosen], name='custom maker')
        self.maker_button.hint = 'Press Enter to generate a challenge, or to find the folder they are kept in.'
        # And under that, one line for each file that could not be read, so a mistyped challenge says so
        # where a player is looking for it rather than only in the log.
        self.problem_views = []
        for i, (name, why) in enumerate(custom.problems()):
            self.problem_views.append(
                View('%s was skipped: %s' % (name, why),
                     (192, 34 + len(self.arenas) * 34 + 50 + i * 24, 187, 20), parent=v,
                     name='custom problem %i' % (i + 1)))
        self.read_out_arenas()
        self.first_accessible_element = self.buttons[0] if self.buttons else self.maker_button
        self.roots = [v]

    def read_out_arenas(self) -> None:
        """What each arena's row says: its name and how many of its stars are won, as a chapter's does.

        Done again whenever the screen comes back, because the maker and the armory are both reached from
        under it and both change what a row has to say.
        """
        from ..game import custom
        from ..game.challenge_data import ChallengeData
        cd = ChallengeData.shared()
        for title, b in zip(self.arenas, self.buttons):
            ids = custom.arena_challenges(title)
            won = sum(cd.stars_for_challenge_with_name(cid) for cid in ids)
            b.label = '%s, %i of %i stars' % (title, won, 3 * len(ids))
            b.hint = 'Press Enter to open this arena, Shift plus Enter to rename it.'
            b.shift_actions.clear()
            b.shift_actions.append(lambda t=title: self.rename_arena(t))

    def rename_arena(self, arena: str) -> None:
        """PORT ADDITION (user request): type an arena a name of your own.

        A pack says its arena once and the loose challenges say it each, so this may change several files
        at a time - `custom.rename_arena` does that and says how many.
        """
        from ..game import custom
        play_button_click()

        def done(typed):
            if typed is None or typed == arena:
                return
            if typed in [t for t, _i in custom.arenas()]:
                self.speak('There is already an arena called %s.' % typed)
                return
            try:
                custom.rename_arena(arena, typed)
            except Exception as exc:
                log.exception('the arena could not be renamed')
                self.speak('It could not be renamed: %s' % exc)
                return
            self.speak('%s is now called %s.' % (arena, typed))
            App.delegate().go_to_custom_menu()
        ask_for_text(self, 'Rename %s' % arena, value=arena, on_done=done, what='name')

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.read_out_arenas()

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Extra')

    @staticmethod
    def arena_chosen(arena: str) -> None:
        App.delegate().go_to_custom_arena(arena)

    @staticmethod
    def maker_chosen() -> None:
        App.delegate().go_to_challenge_maker()

    def back_button_pressed(self) -> None:
        App.delegate().go_to_extra_menu()


@register('Port_CustomArenaViewController')
class CustomArenaScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the challenges of one custom arena.

    The same screen as a chapter of Extra, with one thing added: a challenge holding an enemy the
    Zombiepedia has not unlocked yet says so and cannot be opened.  `canUseBrickWithName:` 0x1000c259c
    refuses an Endless brick for exactly that reason, and a file written by somebody who has played further
    than you have is the case that makes it matter here - without it, a Colossus at 450 kills walks into a
    challenge played by somebody who has never been told what one is.
    """
    def __init__(self, host, arena: str = ''):
        super().__init__(host)
        self.arena = arena
        self.page_title = arena or 'Custom'

    def load_view(self) -> None:
        from ..game import custom
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='customArena')
        self.challenges = list(custom.arena_challenges(self.arena))
        self.buttons = []
        for i, name in enumerate(self.challenges):
            d = data.plist(name) or {}
            b = Button(str(d.get('title') or name), (192, 34 + i * 34, 187, 30), parent=v, font_button=False,
                       actions=[lambda n=name: self.challenge_chosen(n)], name='custom %s' % name)
            self.buttons.append(b)
        # Under the challenges: a new one goes into this arena, which is what an arena is for.
        self.add_button = Button('Add a challenge to this arena',
                                 (192, 34 + len(self.challenges) * 34 + 8, 187, 30), parent=v,
                                 actions=[self.add_challenge], name='custom add')
        self.add_button.hint = 'Press Enter to name a challenge of your own and start editing it.'
        # And under that: the arena as one file, recordings and all, for handing to somebody else.
        one_file = custom.is_one_file(self.arena)
        self.share_button = Button('Already one file' if one_file else 'Make this arena one file',
                                   (192, 34 + len(self.challenges) * 34 + 42, 187, 30), parent=v,
                                   actions=[self.pack_up], name='custom share')
        self.share_button.hint = (
            'This arena is already a single file with its recordings inside it, so it can be handed to '
            'somebody as it is. Press Enter to hear where it is.' if one_file else
            'Press Enter to put this arena and the recordings it speaks with into one file, so it can be '
            'handed over on its own. You are asked first, because the file it is in now is replaced.')
        self.read_out_challenges()
        self.first_accessible_element = self.buttons[0] if self.buttons else self.add_button
        self.roots = [v]

    def pack_up(self) -> None:
        """PORT ADDITION (user request, 2026-10-01): make this arena one file, recordings and all.

        A pack with dialogue in it used to be a file *and* the folder of recordings it speaks with, and
        somebody handed only the file heard none of it.  This makes the arena a `.adpack` that carries them
        (`custom.pack_up`), which the game then reads, plays and edits like any other pack.

        It asks first, because the files the arena is in now are replaced by the one.
        """
        from ..game import custom
        if custom.is_one_file(self.arena):
            self.speak('%s is already one file, %s, in the challenges folder. It can be handed to somebody '
                       'as it is.' % (self.arena, os.path.basename(custom.pack_files(self.arena)[0])))
            return
        was = len(custom.pack_files(self.arena))
        self.host.push_overlay(AlertScreen(
            self.host, 'Make %s one file?' % self.arena,
            'Its recordings go inside it, so it can be handed to somebody on its own and will not need '
            'the audio folder. The %s it is in now %s replaced. Your recordings stay where they are.'
            % ('file' if was == 1 else '%i files' % was, 'is' if was == 1 else 'are'),
            [('Leave it as it is', None), ('Make it one file', self.really_pack_up)]))

    def really_pack_up(self) -> None:
        from ..game import custom
        try:
            path, carried, missing, was = custom.pack_up(self.arena)
        except Exception as exc:
            log.exception('the arena could not be packed up')
            self.speak('It could not be made one file: %s. It is as it was.' % exc)
            return
        said = ['%s is one file now, %s.' % (self.arena, os.path.basename(path))]
        if carried == 1:
            said.append('One recording is inside it.')
        elif carried:
            said.append('%i recordings are inside it.' % carried)
        else:
            said.append('It has no dialogue, so there was nothing to carry.')
        if missing:
            # Said rather than refused: the arena is still worth having, and a line with no recording
            # behind it is a line the reader already passes over.
            said.append('%i of its sounds are no longer in the audio folder, so they could not go in.'
                        % len(missing))
        if was > 1:
            said.append('It replaced %i files.' % was)
        said.append('You can hand it over on its own now.')
        self.speak(' '.join(said))
        App.delegate().go_to_custom_arena(self.arena)

    def add_challenge(self) -> None:
        """PORT ADDITION (user request): a new challenge, named, in this arena."""
        from ..game import custom

        def done(typed):
            if typed is None:
                return
            try:
                cid = custom.create_challenge(typed, arena=self.arena)
            except Exception as exc:
                log.exception('the challenge could not be created')
                self.speak('It could not be made: %s' % exc)
                return
            self.speak('%s was added to %s. Edit it now.' % (typed, self.arena))
            App.delegate().go_to_challenge_editor(cid)
        ask_for_text(self, 'Name a challenge for %s' % self.arena, on_done=done, what='title')

    @staticmethod
    def status_for(name: str, d: dict) -> str:
        """The status the accessible selector gives a row (`statusForChallengeWithDict:` 0x100054960), and
        before it the one thing that selector never has to say."""
        from ..game import custom
        locked = custom.locked_kinds_in(name)
        if locked:
            # Named rather than counted: the name is what a player looks up in the Zombiepedia, which is
            # the screen that will tell them how many more kills it wants.
            return 'locked, it has a %s in it and you have not unlocked that enemy yet' % locked[0]
        # PORT ADDITION (user request, 2026-09-30): a challenge somebody has made and not filled in.  It is
        # not locked and nothing is wrong with it: it has no zombies in it yet, so there is nothing to play.
        if custom.nothing_to_kill_in(name):
            return 'nothing in it yet, press Shift plus Enter to put some zombies in it'
        from .challenges import AccessibleChallengeSelectorScreen
        return AccessibleChallengeSelectorScreen.status_for_challenge_with_dict(d)

    def read_out_challenges(self) -> None:
        for name, b in zip(self.challenges, self.buttons):
            d = data.plist(name) or {}
            status = self.status_for(name, d)
            b.label = '%s, %s' % (str(d.get('title') or name), status)
            if status.startswith('locked'):
                b.hint = None
                continue
            # PORT ADDITION (user request): Shift plus Enter opens the editor, the way Shift plus Enter is
            # the other half of a stepped row in Settings.  It is a row rather than a screen of its own
            # because every challenge here has one, and a list twice as long to walk is the cost of saying
            # so twice.  A locked one has no editor: there is nothing to be done about an enemy you have
            # not unlocked.
            b.hint = '%s Press Shift plus Enter to edit it.' % (d.get('objective') or '')
            b.shift_actions.clear()
            b.shift_actions.append(lambda n=name: self.edit_chosen(n))

    @staticmethod
    def edit_chosen(name: str) -> None:
        play_button_click()                               # shift_actions replace the button's own click
        App.delegate().go_to_challenge_editor(name)

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.read_out_challenges()

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Custom')

    def challenge_chosen(self, name: str) -> None:
        """What the selector's `tableView:didSelectRowAtIndexPath:` 0x100054f8c does with a row, in the same
        order as `ExtraChapterScreen.challenge_chosen` - and refusing, before any of it, a challenge whose
        enemies are not unlocked.  A gun not bought goes to the armory; a challenge waiting on another in
        its own pack does nothing and says nothing."""
        from ..game import custom
        from ..game.challenge_data import ChallengeData
        from ..game.inventory import Inventory
        if custom.locked_kinds_in(name) or custom.nothing_to_kill_in(name):
            return
        d = App.dictionary_for_challenge_with_name(name) or {}
        for w in d.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                play_button_click()
                App.delegate().go_to_armory(self, False)
                return
        if not ChallengeData.shared().has_challenge_requirements_for_challenge_with_name(name):
            return
        play_button_click()
        App.delegate().go_to_accessible_challenge_overview_with_dictionary(d)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_custom_menu()


#: PORT ADDITION: rounds a gun may be given, as the editor steps them.  A ladder rather than a step of one,
#: because the difference a player cares about is between forty rounds and four hundred, and walking there
#: one round at a time is not an editor.
AMMO_STEPS = (6, 12, 18, 24, 36, 48, 60, 80, 100, 120, 150, 200, 250, 300, 400, 500, 750, 999)


@register('Port_ChallengeEditorViewController')
class ChallengeEditorScreen(ViewControllerScreen):
    """PORT ADDITION (user request): editing a challenge a player has made.

    Every row is a stepped value, the way the port's own rows in Settings are - Enter for the next, Shift
    plus Enter for the previous - because this game has no text entry anywhere: nothing in the port reads a
    typed string, and a caret a screen reader can follow is a feature of its own.  So the title steps
    through names drawn from the same two word lists the generator uses, and anything a player wants that
    those cannot say is a line in the file, which the maker's Open the challenges folder reaches.

    What the rows change is the *challenge*; the waves are rebuilt by Reroll rather than edited one zombie
    at a time (user decision, 2026-09-30).  That keeps the promise the generator makes - `_size_wave` sizes
    every wave against the loadout it will actually be played with, so a challenge that can be saved can be
    won - which a hand-placed zombie could not be held to.

    Nothing is written until Save.  The file is patched rather than rebuilt (`custom.save_challenge`), so
    editing a hand-written challenge keeps whatever the port would not have thought to write back.
    """
    page_title = 'Edit'

    def __init__(self, host, challenge_id: str = ''):
        super().__init__(host)
        from ..game import custom
        self.challenge_id = challenge_id
        self.dirty = False
        #: whether Reroll has run: Save writes the waves back only when they have actually been replaced,
        #: so saving a change of title never rewrites a hand-placed wave through the generator's inverse
        self.rerolled = False
        self.names: list = []
        d = data.plist(challenge_id) or {}
        self.arena = d.get('custom_arena')
        weapons = list(d.get('weapons') or [])
        guns = [w for w in weapons if not custom.is_melee(w.get('name'))]
        melee = [w for w in weapons if custom.is_melee(w.get('name'))]
        self.draft = {
            'title': str(d.get('title') or challenge_id),
            'objective': str(d.get('objective') or ''),
            'tip': str(d.get('tip') or ''),
            'ambient': str((d.get('ambient') or {}).get('ambientPlaylist') or 'ambient_roman'),
            'guns': [g.get('name') for g in guns][:2],
            'ammo': [int(ns_int_value(g.get('ammo')) or 999) for g in guns][:2],
            'melee': melee[0].get('name') if melee else None,
            'accuracy': int(ns_int_value((d.get('accuracy_star') or {}).get('objective'))),
            'time': int(ns_int_value((d.get('time_limit_star') or {}).get('objective'))),
            'coins': int(ns_int_value((d.get('mission_star') or {}).get('reward'))),
            'difficulty': str(d.get('custom_difficulty') or custom.DEFAULT_DIFFICULTY),
            'wave_count': len(d.get('custom_waves') or d.get('bricks') or []),
            #: the whole list, not only the four the rows below toggle: a file may name any flag
            #: `GameModifiers` has, and saving must not quietly drop one somebody wrote by hand
            'modifiers': list(d.get('Modifiers') or []),
        }
        while len(self.draft['guns']) < 2:                # the second slot may be empty
            self.draft['guns'].append(None)
            self.draft['ammo'].append(999)
        self.waves = custom.waves_of(challenge_id)
        self.page_title = 'Edit %s' % self.draft['title']

    # --- the choices each row steps through ------------------------------------------------------
    def _guns(self) -> list:
        """Every gun the player has bought, in the order Weapons.plist lists them (user request).

        Not `custom.GENERATOR_GUNS`: that is the shorter list the *generator* draws from, and it leaves the
        crowd weapons out because it cannot size a wave for one - a shotgun or a bazooka is priced pack by
        pack rather than enemy by enemy.  That is a limit on building a crowd at random, not on what a
        challenge may hand out, and applying it here hid half the armory from somebody placing their own
        zombies.  The slack a wave reads is still counted one zombie at a time, so for a crowd weapon it is
        the pessimistic figure, which is the safe direction to be wrong in.
        """
        from ..game.inventory import Inventory
        from ..game.weapon_manager import WeaponManager
        wm = WeaponManager.shared()
        owned = [str(d.get('name')) for d in wm.get_all_weapons_array() or []
                 if not d.get('melee') and Inventory.shared().has_unlocked_weapon(d.get('name'))]
        return owned or ['pistol']

    def _melees(self) -> list:
        """The same for the melee weapons, which is all five of them when they have been bought."""
        from ..game.inventory import Inventory
        from ..game.weapon_manager import WeaponManager
        wm = WeaponManager.shared()
        owned = [str(d.get('name')) for d in wm.get_all_weapons_array() or []
                 if d.get('melee') and Inventory.shared().has_unlocked_weapon(d.get('name'))]
        return owned or ['wok']

    def _name_choices(self) -> list:
        """The title it has, and a handful drawn fresh from the generator's word lists."""
        from ..game import custom
        if not self.names:
            rng = random.Random()
            self.names = [self.draft['title']]
            while len(self.names) < 12:
                drawn = '%s %s' % (rng.choice(custom._FIRST), rng.choice(custom._SECOND))
                if drawn not in self.names:
                    self.names.append(drawn)
        return self.names

    def _objectives(self) -> list:
        from ..game import custom
        enemies = sum(len(w.get('Enemies') or {}) for w in self.waves)
        out = [custom.objective_for(mood, enemies) for mood in custom.DIFFICULTIES]
        if self.draft['objective'] and custom.generated_objective(self.draft['objective']) is None:
            out.insert(0, self.draft['objective'])        # a sentence somebody wrote: kept as a choice
        return out

    def _tips(self) -> list:
        from ..game import custom
        out = [custom.tip_for(mood) for mood in custom.DIFFICULTIES]
        if self.draft['tip'] and custom.generated_tip(self.draft['tip']) is None:
            out.insert(0, self.draft['tip'])
        return out

    def _step(self, key: str, choices, by: int) -> None:
        """The next (or previous) of `choices` for `key`, stopping at neither end - it wraps, because a
        list of names has no natural first or last the way a sensitivity does."""
        if not choices:
            return
        now = self.draft.get(key)
        at = choices.index(now) if now in choices else 0
        self.draft[key] = choices[(at + by) % len(choices)]
        self.dirty = True
        self.reload_data()

    def _step_slot(self, key: str, slot: int, choices, by: int, allow_none: bool = False) -> None:
        """The next gun for one slot, skipping whatever the other slot is already holding.

        Two slots of the same gun is a loadout that reads out twice and carries one weapon's worth of
        ammunition in two lines, which is not a choice anybody means to make.  `None` is exempt: both
        slots being empty is impossible anyway, since the first has no empty to step to.
        """
        now = self.draft[key][slot]
        taken = {self.draft[key][other] for other in range(len(self.draft[key])) if other != slot}
        options = [c for c in choices if c not in taken or c == now]
        if allow_none:
            options = options + [None]
        if not options:
            return
        at = options.index(now) if now in options else 0
        self.draft[key][slot] = options[(at + by) % len(options)]
        self.dirty = True
        self.reload_data()

    def _step_number(self, key: str, choices, by: int) -> None:
        nearest = min(choices, key=lambda v: abs(v - self.draft[key]))
        at = choices.index(nearest)
        self.draft[key] = choices[max(0, min(len(choices) - 1, at + by))]
        self.dirty = True
        self.reload_data()

    # --- views -----------------------------------------------------------------------------------
    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='challengeEditor')
        self.table_view = View('', (35, 50, 498, 262), accessible=False, parent=v, ordered=True,
                               name='editorTable')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title(self.arena or 'Custom')

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.reload_data()

    def reload_data(self) -> None:
        from ..game import custom
        from ..game.weapon_manager import WeaponManager
        from .challenges import _TableLoader
        wm = WeaponManager.shared()
        step = 'Press Enter for the next value, Shift plus Enter for the previous.'
        t = _TableLoader(self.table_view)
        t.header('What it is')
        t.cell('Title', self.draft['title'],
               hint='The name its row reads out. Press Enter to type one, or Shift plus Enter for a '
                    'suggestion.',
               action=self.rename,
               shift_action=lambda: self._step('title', self._name_choices(), 1))
        t.cell('Objective', self.draft['objective'],
               hint='What the challenge screen says this asks of you. Press Enter to write it yourself, '
                    'or Shift plus Enter for a suggestion.',
               action=lambda: self.write_line('objective', 'Write the objective'),
               shift_action=lambda: self._step('objective', self._objectives(), 1))
        t.cell('Tip', self.draft['tip'],
               hint='The advice under the objective. Press Enter to write it yourself, or Shift plus '
                    'Enter for a suggestion.',
               action=lambda: self.write_line('tip', 'Write the tip'),
               shift_action=lambda: self._step('tip', self._tips(), 1))
        ambiences = list(custom.AMBIENTS) + custom.ambience_keys()
        t.cell('Ambience', self.draft['ambient'],
               hint='What the arena sounds like around you: the ten the game ships, and any you have '
                    'imported. ' + step,
               action=lambda: self._step('ambient', ambiences, 1),
               shift_action=lambda: self._step('ambient', ambiences, -1))
        t.cell('Import an ambience', hint='Press Enter to choose a sound file to play under this arena. '
                                          'It is copied into the challenges folder and chosen here.',
               action=self.import_ambience)
        t.header('Loadout')
        for slot in (0, 1):
            name = self.draft['guns'][slot]
            label = 'First gun' if slot == 0 else 'Second gun'
            shown = wm.display_name_for_item_with_name(name) if name else 'none'
            t.cell(label, shown,
                   hint='Only guns you have bought are offered, so a challenge never sends you to the '
                        'armory to play what you made. ' + step,
                   action=lambda s=slot: self._step_slot('guns', s, self._guns(), 1, allow_none=s == 1),
                   shift_action=lambda s=slot: self._step_slot('guns', s, self._guns(), -1,
                                                               allow_none=s == 1))
            if name:
                t.cell('%s, rounds' % label, str(self.draft['ammo'][slot]),
                       hint='How much ammunition it is given. ' + step,
                       action=lambda s=slot: self._step_ammo(s, 1),
                       shift_action=lambda s=slot: self._step_ammo(s, -1))
        t.cell('Melee', wm.display_name_for_item_with_name(self.draft['melee']) or 'wok',
               hint='The melee weapon, which never runs out. ' + step,
               action=lambda: self._step('melee', self._melees(), 1),
               shift_action=lambda: self._step('melee', self._melees(), -1))
        t.header('Stars')
        t.cell('Accuracy goal', '%i%%' % self.draft['accuracy'],
               hint='The accuracy the second star asks for. ' + step,
               action=lambda: self._step_number('accuracy', list(range(0, 101, 5)), 1),
               shift_action=lambda: self._step_number('accuracy', list(range(0, 101, 5)), -1))
        t.cell('Time goal', '%i seconds' % self.draft['time'],
               hint='How quickly the third star asks you to finish. ' + step,
               action=lambda: self._step_number('time', list(range(30, 601, 10)), 1),
               shift_action=lambda: self._step_number('time', list(range(30, 601, 10)), -1))
        t.cell('Coins for finishing', str(self.draft['coins']),
               hint='What beating it pays. A challenge you made pays at most %i. %s'
                    % (custom.REWARD_CAP, step),
               action=lambda: self._step_number('coins', list(range(0, custom.REWARD_CAP + 1, 25)), 1),
               shift_action=lambda: self._step_number('coins', list(range(0, custom.REWARD_CAP + 1, 25)), -1))
        t.header('Waves')
        t.cell('Difficulty', self.draft['difficulty'],
               hint='How little room a rerolled wave leaves you at its tightest moment. It takes effect '
                    'when you reroll. ' + step,
               action=lambda: self._step('difficulty', list(custom.DIFFICULTIES), 1),
               shift_action=lambda: self._step('difficulty', list(custom.DIFFICULTIES), -1))
        t.cell('Number of waves', str(self.draft['wave_count']),
               hint='How many crowds a reroll builds. ' + step,
               action=lambda: self._step_number('wave_count', list(range(1, custom.MAX_WAVES + 1)), 1),
               shift_action=lambda: self._step_number('wave_count', list(range(1, custom.MAX_WAVES + 1)), -1))
        t.cell('Place the zombies yourself', self.wave_summary(),
               hint='Press Enter to put each zombie in the wave you choose, and say where it comes from '
                    'and when. Nothing here is rerolled unless you ask for it.',
               action=self.edit_waves)
        t.cell('Reroll the waves', self.wave_summary(),
               hint='Press Enter to build the crowds again at random, to the difficulty and the number '
                    'above and sized for the guns you have chosen. A shotgun, a grenade launcher or a '
                    'bazooka is counted one zombie at a time, so a crowd built for one of those is sized '
                    'more harshly than it plays. Everything you placed by hand is replaced, though a wave '
                    'keeps its cutscene.',
               action=self.reroll)
        t.cell('Cutscenes', self.cutscene_summary(),
               hint='Press Enter to add dialogue to the waves, from sound files of your own.',
               action=self.edit_cutscenes)
        t.header('In the arena')
        for flag, title, does in custom.arena_extras():
            on = custom.arena_extra_shows_yes(self.draft['modifiers'], flag)
            t.cell(title, 'yes' if on else 'no',
                   hint='%s Press Enter to toggle.' % does,
                   action=lambda f=flag: self.toggle_extra(f))
        t.header('')
        t.cell('Save', 'unsaved changes' if self.dirty else 'saved',
               hint='Press Enter to write this back to its file.', action=self.save)
        t.cell('Delete this challenge', hint='Press Enter to delete the file it came from. You are asked '
                                             'first.', action=self.confirm_delete)

    def wave_summary(self) -> str:
        """What the Reroll row reads as its value: how big the waves are and how much room the tightest
        one leaves, which is the one number that says whether this is still winnable."""
        from ..game import custom
        enemies = sum(len(w.get('Enemies') or {}) for w in self.waves)
        guns = [g for g in self.draft['guns'] if g]
        best = max((custom.sustained_damage(g) for g in guns), default=1.0)
        slack = min((custom.wave_margin(w, best) for w in self.waves), default=0.0)
        # A wave with nothing to kill leaves infinite room, which is true and is not a number to read out -
        # and `%i` of it raises, which on a challenge just made (one empty wave) would be every wave of it.
        # Each of the four is a whole sentence rather than a stem and an ending: a line with a gap in it goes
        # to a translator in one piece, and gluing two translated halves ties them to the English order.
        if not enemies:
            if len(self.waves) == 1:
                return 'one wave, nothing in it yet'
            return '%i waves, nothing in them yet' % len(self.waves)
        if len(self.waves) == 1:
            return 'one wave, %i zombies, %i seconds to spare at the tightest' % (enemies, slack)
        return '%i waves, %i zombies, %i seconds to spare at the tightest' % (len(self.waves), enemies, slack)

    def write_line(self, key: str, title: str) -> None:
        """PORT ADDITION (user request): write the objective or the tip in your own words.

        A sentence rather than a name, so it takes the punctuation writing needs.  What is written stays
        written: `custom.generated_objective` only recognises the three the generator writes, so rerolling
        the waves afterwards leaves a sentence of your own exactly as you left it.
        """
        from .host import sentence_is_allowed

        def done(typed):
            if typed is None or typed == self.draft[key]:
                return
            self.draft[key] = typed
            self.dirty = True
            self.reload_data()
            self.speak(typed)
        ask_for_text(self, title, value=self.draft[key], on_done=done, what='sentence',
                     max_length=240, allowed=sentence_is_allowed)

    def rename(self) -> None:
        """PORT ADDITION (user request): type the challenge a name of your own."""
        def done(typed):
            if typed is None or typed == self.draft['title']:
                return
            self.draft['title'] = typed
            self.page_title = 'Edit %s' % typed
            self.dirty = True
            self.reload_data()
            self.speak('Now called %s.' % typed)
        ask_for_text(self, 'Name this challenge', value=self.draft['title'], on_done=done,
                     what='title')

    def import_ambience(self) -> None:
        """PORT ADDITION (user request): a bed of your own under the arena.

        The same road a cutscene takes - the system's file dialog, then a copy into the challenges folder -
        and it is chosen here as soon as it lands, because importing one and then having to find it in a
        list is a step nobody wants.
        """
        from ..game import custom
        from ..platform.filedialog import choose_audio_file
        chosen = choose_audio_file('Choose an ambience for %s' % self.draft['title'])
        if not chosen:
            self.speak('No sound was chosen.')
            return
        try:
            key = custom.import_ambience(chosen)
        except OSError as exc:
            log.warning('the ambience could not be imported: %s', exc)
            self.speak('That sound could not be copied in: %s' % exc)
            return
        self.draft['ambient'] = key
        self.dirty = True
        self.reload_data()
        said = '%s was imported, and is this arena\'s ambience.' % key
        if inside:
            said += ' It is inside the arena file, so it travels with it.'
        self.speak(said)

    def cutscene_summary(self) -> str:
        from ..game import custom
        lines = sum(len(custom.cutscene_of(w, where))
                    for w in self.waves for where in custom.PLACES)
        if lines == 1:
            return 'one line'
        return '%i lines' % lines if lines else 'none'

    def edit_waves(self) -> None:
        """To the wave editor, saving anything waiting first - it writes as it goes, so an unsaved title
        left behind here would be a change that never landed under one that did."""
        if self.dirty:
            self.save()
        App.delegate().go_to_wave_editor(self.challenge_id)

    def edit_cutscenes(self) -> None:
        """Straight to the cutscene screen, saving first if anything is waiting.

        The cutscene screen writes to the file as it goes - importing a sound copies it in there and then -
        so leaving an unsaved title behind would be a screen whose changes had landed sitting on top of one
        whose changes had not.
        """
        if self.dirty:
            self.save()
        App.delegate().go_to_cutscene_editor(self.challenge_id)

    def toggle_extra(self, flag: str) -> None:
        """PORT ADDITION (user request, 2026-09-30): the cows, the car alarms, the jukebox and the generator,
        switched on or off for this challenge.

        Each is one of the original's own `GameModifiers` flags, and what it switches on is the original's own
        arena furniture - `ADPasserByManager` 0x1000d570c owns all four.  So this writes a flag into the
        challenge's `modifiers` and nothing more; the game does the rest on its own, as it does in Endless
        when a tarot card turns one on.
        """
        from ..game import custom
        title = dict((f, t) for f, t, _d in custom.arena_extras()).get(flag, flag)
        mods = list(self.draft['modifiers'])
        inverted = flag in custom.ARENA_EXTRAS_INVERTED
        # Which way the press goes is decided by what the row *says*, not by whether the plain flag is in
        # the list: a row reading yes has to turn off when it is pressed, however it came to read yes.
        wants_yes = not custom.arena_extra_shows_yes(mods, flag)
        # And whether that means writing the flag or taking it out depends on which way the flag runs:
        # `noZombieThemes` is the one that turns a thing off, so a row going to no is what writes it.
        write_it = (not wants_yes) if inverted else wants_yes
        if write_it:
            if not custom.arena_extra_is_on(mods, flag):
                mods.append(flag)
            said = ('%s do not play.' if inverted else '%s is in the arena.') % title
        else:
            mods = [m for m in mods if m != flag]
            said = ('%s play.' if inverted else '%s is not in the arena.') % title
            # A level-4 flag of the port's own stands for two things at once, and one of them may be this.
            # Taking that flag out to stop the cows would quietly take away what it gives with its other
            # hand, so it is left alone and the row says why it still reads the way it does.
            paired = custom.paired_sources_of(mods, flag)
            if paired:
                said = '%s is still asked for by %s, which this does not take out.' % (title, paired[0])
        self.draft['modifiers'] = mods
        self.dirty = True
        self.reload_data()
        self.speak(said)

    def _step_ammo(self, slot: int, by: int) -> None:
        now = self.draft['ammo'][slot]
        nearest = min(AMMO_STEPS, key=lambda v: abs(v - now))
        at = AMMO_STEPS.index(nearest)
        self.draft['ammo'][slot] = AMMO_STEPS[max(0, min(len(AMMO_STEPS) - 1, at + by))]
        self.dirty = True
        self.reload_data()

    # --- what the three buttons do ---------------------------------------------------------------
    def reroll(self) -> None:
        from ..game import custom
        guns = [g for g in self.draft['guns'] if g]
        best = max((custom.sustained_damage(g) for g in guns), default=1.0)
        try:
            fresh = custom.build_waves(self.draft['difficulty'], self.draft['wave_count'], best)
        except Exception as exc:                          # a button a player presses never crashes the game
            log.exception('the waves could not be rerolled')
            self.speak('The waves could not be rerolled: %s' % exc)
            return
        # A cutscene belongs to the place in the challenge rather than to the crowd that was there, so
        # wave one's dialogue stays wave one's - all three of its cutscenes, since a scene before a wave is
        # about where it comes in the story and not about what arrives.  Rerolling to fewer waves drops the
        # dialogue of the ones that are gone, which is the only thing it can mean.
        for i, wave in enumerate(fresh):
            if i < len(self.waves):
                for where in custom.PLACES:
                    custom.set_cutscene(wave, where, custom.cutscene_of(self.waves[i], where))
        self.waves = fresh
        # The objective counts the zombies, so a reroll that changed how many of them there are has to
        # restate it - but only when it is one of the generator's own sentences.  Somebody's own words are
        # theirs, and are left exactly as they wrote them.
        enemies = sum(len(w.get('Enemies') or {}) for w in self.waves)
        if custom.generated_objective(self.draft['objective']) is not None:
            self.draft['objective'] = custom.objective_for(self.draft['difficulty'], enemies)
        if custom.generated_tip(self.draft['tip']) is not None:
            self.draft['tip'] = custom.tip_for(self.draft['difficulty'])
        self.dirty = True
        self.rerolled = True
        self.reload_data()
        self.speak(self.wave_summary())

    def save(self) -> None:
        from ..game import custom
        weapons = []
        for slot in (0, 1):
            if self.draft['guns'][slot]:
                weapons.append({'name': self.draft['guns'][slot], 'ammo': self.draft['ammo'][slot]})
        weapons.append({'name': self.draft['melee'] or 'wok'})
        changes = {
            'title': self.draft['title'],
            'objective': self.draft['objective'],
            'tip': self.draft['tip'],
            'ambient': self.draft['ambient'],
            'weapons': weapons,
            'accuracy': {'objective': self.draft['accuracy'], 'reward': 150},
            'time': {'objective': self.draft['time'], 'reward': 150},
            'coins': self.draft['coins'],
            'difficulty': self.draft['difficulty'],
            'modifiers': self.draft['modifiers'],
        }
        try:
            custom.save_challenge(self.challenge_id, changes,
                                  waves=self.waves if getattr(self, 'rerolled', False) else None)
        except Exception as exc:
            log.exception('the challenge could not be saved')
            self.speak('It could not be saved: %s' % exc)
            return
        self.dirty = False
        self.reload_data()
        self.speak('%s was saved.' % self.draft['title'])

    def confirm_delete(self) -> None:
        self.host.push_overlay(AlertScreen(
            self.host, 'Delete %s?' % self.draft['title'],
            'This deletes the file it came from, and cannot be undone. A challenge that is part of a pack '
            'takes the rest of that pack with it.',
            [('Keep it', None), ('Delete it', self.delete)]))

    def delete(self) -> None:
        from ..game import custom
        try:
            custom.delete_challenge(self.challenge_id)
        except Exception as exc:
            log.exception('the challenge could not be deleted')
            self.speak('It could not be deleted: %s' % exc)
            return
        App.delegate().go_to_custom_menu()

    def back_button_pressed(self) -> None:
        if not self.dirty:
            self.leave()
            return
        # An edit that is lost without being mentioned is the worst thing a screen like this can do, and on
        # a screen you cannot see there is nothing to show that a value has moved.
        self.host.push_overlay(AlertScreen(
            self.host, 'Leave without saving?',
            'The changes you have made to %s have not been written to its file.' % self.draft['title'],
            [('Save and leave', self.save_and_leave), ('Leave without saving', self.leave)]))

    def save_and_leave(self) -> None:
        self.save()
        self.leave()

    def leave(self) -> None:
        if self.arena:
            App.delegate().go_to_custom_arena(self.arena)
        else:
            App.delegate().go_to_custom_menu()


#: PORT ADDITION (user request): when a wave's air drop arrives, in seconds from the wave starting.  Shorter
#: steps early, where the difference between 2 and 5 seconds is the difference between having the minigun for
#: the first crowd and not.
POWERUP_TIMES = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0,
                 50.0, 60.0, 90.0, 120.0)

#: What a hand-placed zombie's rows step through.
ENEMY_BEARINGS = tuple(range(0, 360, 15))
ENEMY_DISTANCES = (5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 14.0, 16.0, 18.0, 20.0)
ENEMY_TIMES = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0,
               30.0, 40.0, 50.0, 60.0, 90.0, 120.0)


class _WaveWork:
    """What the two wave screens share: the challenge's waves, what its guns do, and writing them back."""

    def load_waves(self, challenge_id: str) -> None:
        from ..game import custom
        self.challenge_id = challenge_id
        d = data.plist(challenge_id) or {}
        self.title_text = str(d.get('title') or challenge_id)
        guns = [w.get('name') for w in (d.get('weapons') or []) if not custom.is_melee(w.get('name'))]
        # What the waves are measured against: the best gun the challenge hands out, at level 1, as the
        # generator sizes them.  A player placing zombies by hand is told the same number the generator
        # solves for, so "3 seconds of slack" means the same thing on both sides of the screen.
        self.damage = max((custom.sustained_damage(g) for g in guns), default=1.0)
        self.waves = custom.waves_of(challenge_id)

    def slack_of(self, wave: dict) -> str:
        from ..game import custom
        if not (wave.get('Enemies') or {}):
            return 'nothing to kill'
        margin = custom.wave_margin(wave, self.damage)
        if margin < 0:
            return 'too tight to win by %.0f seconds' % -margin
        return '%.0f seconds of slack' % margin

    def write_waves(self, said: str = '') -> bool:
        """Write the waves back, and then hold what the file now says rather than what was sent to it.

        `save_challenge` reads the folder again, which builds every wave afresh - so the dictionaries this
        screen is holding are last moment's, and go stale the instant they are written.  Re-reading them is
        what keeps a row's zombie the same zombie as the file's (`custom.slot_name`).
        """
        from ..game import custom
        try:
            custom.save_challenge(self.challenge_id, {}, waves=self.waves)
        except Exception as exc:
            log.exception('the waves could not be saved')
            self.speak('It could not be saved: %s' % exc)
            return False
        self.waves = custom.waves_of(self.challenge_id)
        if said:
            self.speak(said)
        return True


@register('Port_WaveEditorViewController')
class WaveEditorScreen(ViewControllerScreen, _WaveWork):
    """PORT ADDITION (user request): the zombies of a challenge, placed by hand, wave by wave.

    The generator sizes a crowd so it can be won; this is the other way of filling a wave, where the
    player decides what is in it and where.  The wave stays the unit - `brickIsCleared` 0x1000a1658 clears
    one and the manager loads the next, which is what a wave *is* - and what changes is that each zombie
    is put in the wave you chose rather than in the one a roll gave it.

    Every wave's header reads out the slack at its tightest moment, the same number `_size_wave` solves
    for, because a wave you cannot see is one you cannot judge by eye either: "Wave 2, 6 zombies, 3
    seconds of slack" is how you hear that you have gone too far.

    It writes as it goes, like the cutscene screen: there is no half-placed zombie worth keeping in memory.
    """
    page_title = 'Waves'

    def __init__(self, host, challenge_id: str = ''):
        super().__init__(host)
        self.load_waves(challenge_id)
        self.page_title = 'Waves: %s' % self.title_text

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='waveEditor')
        self.table_view = View('', (35, 50, 498, 262), accessible=False, parent=v, ordered=True,
                               name='waveTable')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title('Edit')

    def view_will_appear(self) -> None:
        from ..game import custom
        super().view_will_appear()
        self.waves = custom.waves_of(self.challenge_id)   # a zombie's own screen may have moved one
        self.reload_data()

    @staticmethod
    def enemy_text(place: dict) -> str:
        return '%g degrees, %g units, arrives at %g seconds' % (
            place.get('spawn_angle', 0.0), place.get('spawn_distance', 10.0),
            place.get('spawn_time', 0.0) or 0.0)

    def reload_data(self) -> None:
        from ..game import custom
        from .challenges import _TableLoader
        step = 'Press Enter for the next value, Shift plus Enter for the previous.'
        t = _TableLoader(self.table_view)
        for index, wave in enumerate(self.waves):
            enemies = wave.get('Enemies') or {}
            lines = len(wave.get('Sounds') or [])
            head = 'Wave %i, %i zombies, %s' % (index + 1, len(enemies), self.slack_of(wave))
            if lines:
                head += ', %s' % ('one cutscene line' if lines == 1 else '%i cutscene lines' % lines)
            t.header(head)
            # PORT ADDITION (user request): how many are in this wave, as one row.  Stepping it up adds a
            # zombie and stepping it down takes the last one off, so a wave can be sized without walking
            # its rows - which for a wave of twenty is the difference between a row and twenty of them.
            t.cell('Zombies in wave %i' % (index + 1), str(len(enemies)),
                   hint='How many are in this wave. Stepping it up puts another of the last one in, and '
                        'stepping it down takes the last one off. ' + step,
                   action=lambda w=index: self.step_count(w, 1),
                   shift_action=lambda w=index: self.step_count(w, -1))
            for slot, place in enemies.items():
                t.cell(custom.display_name(str(slot).split(' ')[0]), self.enemy_text(place),
                       hint='Press Enter to change or move this zombie, Shift plus Enter to remove it.',
                       action=lambda w=index, s=slot: self.open_enemy(w, s),
                       shift_action=lambda w=index, s=slot: self.remove_enemy(w, s))
            t.cell('Add a zombie to wave %i' % (index + 1),
                   hint='Press Enter to choose which zombie to put in this wave. Only the ones your '
                        'Zombiepedia has unlocked are offered.',
                   action=lambda w=index: self.add_enemy(w))
            # PORT ADDITION (user request): the air drop a wave can hand you, which the game's own
            # challenges do with a `PowerUp` block on the brick.  Two rows and only when there is one to
            # time, so a wave without a drop costs one row rather than two.
            kind = custom.powerup_kind_of(wave)
            t.cell('Power-up in wave %i' % (index + 1), self.powerup_text(wave),
                   hint='An air drop this wave hands you. Any is whatever the game feels like, as Endless '
                        'gives; the four named ones always come as named. ' + step,
                   action=lambda w=index: self.step_powerup(w, 1),
                   shift_action=lambda w=index: self.step_powerup(w, -1))
            if kind != 'none':
                t.cell('The power-up arrives', '%g seconds in' % custom.powerup_time_of(wave),
                       hint='How long after the wave starts the drop appears. ' + step,
                       action=lambda w=index: self.step_powerup_time(w, 1),
                       shift_action=lambda w=index: self.step_powerup_time(w, -1))
            # PORT ADDITION (user request): the diamonds a wave puts out, which until now only Endless
            # ever did - its own timer drops one every 40 to 70 seconds and nothing else called `addDiamond`.
            t.cell('Diamonds in wave %i' % (index + 1), str(custom.diamonds_in(wave)),
                   hint='Diamonds in the arena for this wave. Each arrives two seconds in, nine units out '
                        'at a bearing of its own, and leaves about nine seconds later unless you shoot it. '
                        + step,
                   action=lambda w=index: self.step_diamonds(w, 1),
                   shift_action=lambda w=index: self.step_diamonds(w, -1))
            # PORT ADDITION (user request): the music a zombie brings with it, wave by wave.  Four of them
            # have one - the Chainsaw, the Hulk, the Whisperer and the Zombie Dog - and whether it should
            # be heard is a question about this wave rather than about the whole challenge.
            t.cell('Zombie themes in wave %i' % (index + 1),
                   'yes' if custom.zombie_themes_in(wave) else 'no',
                   hint='The Chainsaw, the Hulk, the Whisperer and the Zombie Dog each bring their own '
                        'music in with them. Turn it off and this wave is heard over the arena you chose '
                        'instead. Press Enter to toggle.',
                   action=lambda w=index: self.toggle_themes(w))
            if len(self.waves) > 1:
                t.cell('Delete wave %i' % (index + 1),
                       hint='Press Enter to remove this wave and everything in it. You are asked first.',
                       action=lambda w=index: self.confirm_delete_wave(w))
        t.header('')
        t.cell('Add a wave', '%i of %i' % (len(self.waves), custom_max_waves()),
               hint='Press Enter to add an empty wave at the end.', action=self.add_wave)

    def step_count(self, index: int, by: int) -> None:
        """Add a zombie to this wave, or take the last one off."""
        from ..game import custom
        wave = self.waves[index]
        enemies = wave.get('Enemies') or {}
        if by > 0:
            if len(enemies) >= custom.MAX_ENEMIES:
                self.speak('A wave holds at most %i zombies.' % custom.MAX_ENEMIES)
                return
            # One press, one more zombie: this row is the quick way to size a wave, so it does not stop to
            # ask.  One at random out of what the Zombiepedia has unlocked (user request, 2026-10-01) - it
            # was another of the last one in the wave, which made stepping it up build a crowd all of one
            # kind, and a crowd worth listening to is a mixed one.  `Add a zombie` is the row that asks.
            roster = custom.pedia_roster()
            if not roster:
                self.speak('There are no zombies unlocked yet.')
                return
            shown, kinds = random.choice(roster)
            self.put_enemy(index, shown, kinds)
            return
        if not enemies:
            return
        gone = list(enemies)[-1]
        custom.remove_enemy(wave, gone)
        if self.write_waves():
            self.reload_data()
            self.speak('%i zombies in wave %i. %s'
                       % (len(enemies), index + 1, self.slack_of(wave)))

    # --- what the rows do ------------------------------------------------------------------------
    @staticmethod
    def powerup_text(wave: dict) -> str:
        """The drop's row as it reads: what it is, or that there is none."""
        from ..game import custom
        from ..game.weapon_manager import WeaponManager
        kind = custom.powerup_kind_of(wave)
        if kind == 'none':
            return 'none'
        if kind == 'any':
            return 'any'
        # The game's own name for it, out of Weapons.plist - "Tesla Coil", not "tesla"
        return WeaponManager.shared().display_name_for_item_with_name(kind) or kind

    def powerup_choices(self) -> list:
        """'none' and then the kinds, which is what the row steps through."""
        from ..game import custom
        return ['none'] + list(custom.POWERUP_KINDS)

    def step_powerup(self, index: int, by: int) -> None:
        """PORT ADDITION (user request, 2026-09-30): the wave's air drop, chosen on one row.

        A `PowerUp` block on the brick, which is how the game's own challenges hand one out
        (`Brick.update` 0x1000a0ed0 -> `forceToPopPowerUpContainerWithType:` 0x1000c7b68).  It wraps, as a
        list of names does, so 'none' is one step back from the first kind.
        """
        from ..game import custom
        wave = self.waves[index]
        choices = self.powerup_choices()
        now = custom.powerup_kind_of(wave)
        wanted = choices[(choices.index(now) + by) % len(choices)]
        # The time is kept across a change of kind, and a drop being switched on starts at the wave's
        # beginning - which is what a wave with a drop in it almost always wants.
        custom.set_powerup(wave, wanted, custom.powerup_time_of(wave))
        if self.write_waves():
            self.reload_data()
            if wanted == 'none':
                self.speak('Wave %i has no power-up.' % (index + 1))
            else:
                self.speak('Wave %i hands you %s, %g seconds in.'
                           % (index + 1, self.powerup_text(wave), custom.powerup_time_of(wave)))

    def step_powerup_time(self, index: int, by: int) -> None:
        from ..game import custom
        wave = self.waves[index]
        kind = custom.powerup_kind_of(wave)
        if kind == 'none':
            return
        now = custom.powerup_time_of(wave)
        nearest = min(POWERUP_TIMES, key=lambda v: abs(v - now))
        at = POWERUP_TIMES[max(0, min(len(POWERUP_TIMES) - 1, POWERUP_TIMES.index(nearest) + by))]
        custom.set_powerup(wave, kind, at)
        if self.write_waves():
            self.reload_data()
            self.speak('%g seconds in.' % at)

    def step_diamonds(self, index: int, by: int) -> None:
        """PORT ADDITION (user request, 2026-10-01): how many diamonds this wave puts in the arena."""
        from ..game import custom
        wave = self.waves[index]
        now = custom.diamonds_in(wave)
        wanted = max(0, min(custom.MAX_DIAMONDS, now + by))
        if wanted == now:
            if by > 0:
                self.speak('A wave holds at most %i diamonds.' % custom.MAX_DIAMONDS)
            return
        custom.set_diamonds(wave, wanted)
        if self.write_waves():
            self.reload_data()
            if not wanted:
                self.speak('No diamonds in wave %i.' % (index + 1))
            elif wanted == 1:
                self.speak('One diamond in wave %i.' % (index + 1))
            else:
                self.speak('%i diamonds in wave %i.' % (wanted, index + 1))

    def toggle_themes(self, index: int) -> None:
        """PORT ADDITION (user request, 2026-10-01): this wave with or without its zombies' own music."""
        from ..game import custom
        wave = self.waves[index]
        on = not custom.zombie_themes_in(wave)
        custom.set_zombie_themes(wave, on)
        if self.write_waves():
            self.reload_data()
            if on:
                self.speak('Wave %i plays the music its zombies bring.' % (index + 1))
            else:
                self.speak('Wave %i is heard over the arena, with no zombie music.' % (index + 1))

    def add_enemy(self, index: int) -> None:
        """PORT ADDITION (user request, 2026-10-01): ask which zombie, rather than adding the first one.

        It used to add `roster[0]`, which is the Chainsaw: the Zombiepedia's own order is by what it asks
        before it will show you an entry (`sort_zombie_names` 0x100079610), so its first row is the first
        zombie the game introduces and the Colossus is its twelfth.  Anybody who wanted a Colossus had to
        add a Chainsaw and then step its kind eleven times.

        An overlay rather than a screen of its own, so the wave editor keeps its rows and its cursor
        underneath - which is what an alert is for, and what every other list of choices in this game does.
        """
        from ..game import custom
        roster = custom.pedia_roster()
        if not roster:
            self.speak('There are no zombies unlocked yet.')
            return
        buttons = [(shown, lambda s=shown, k=kinds: self.put_enemy(index, s, k))
                   for shown, kinds in roster]
        buttons.append(('Cancel', None))
        self.host.push_overlay(AlertScreen(
            self.host, 'Add a zombie to wave %i' % (index + 1),
            'Only the ones your Zombiepedia has unlocked are offered.', buttons))

    def put_enemy(self, index: int, shown: str, kinds) -> None:
        """The zombie that was chosen, into that wave."""
        from ..game import custom
        wave = self.waves[index]
        enemies = wave.get('Enemies') or {}
        # Placed where it will not land on the one before it: a turn of about 137.5 degrees never settles
        # into a pattern, which is what the generator uses, and two seconds after the last arrival.
        angle = (len(enemies) * custom.GOLDEN_TURN) % 360.0
        last = max((float(p.get('spawn_time') or 0) for p in enemies.values()), default=-2.0)
        # The next set of recordings for that zombie, so two of a kind in one wave are heard as two.
        already = sum(1 for s in enemies if custom.display_name(custom.kind_of(s)) == shown)
        custom.add_enemy(wave, custom.variant_of(kinds, already), angle, 10.0,
                         max(0.0, round(last + 2.0, 1)))
        if self.write_waves():
            self.reload_data()
            self.speak('A %s was added to wave %i. %s'
                       % (shown, index + 1, self.slack_of(self.waves[index])))

    def remove_enemy(self, index: int, slot: str) -> None:
        from ..game import custom
        wave = self.waves[index]
        if not custom.remove_enemy(wave, slot):
            return
        shown = custom.display_name(custom.kind_of(slot))
        if self.write_waves():
            self.reload_data()
            self.speak('%s removed from wave %i. %s'
                       % (shown, index + 1, self.slack_of(self.waves[index])))

    def open_enemy(self, index: int, slot: str) -> None:
        play_button_click()
        App.delegate().go_to_enemy_editor(self.challenge_id, index, slot)

    def add_wave(self) -> None:
        from ..game import custom
        if len(self.waves) >= custom.MAX_WAVES:
            self.speak('A challenge holds at most %i waves.' % custom.MAX_WAVES)
            return
        # Empty (user request, 2026-09-30).  It used to arrive with a zombie in it, because a wave with
        # nothing in it was a file the reader refused; an empty wave is let by now, so a wave added is a wave
        # to fill rather than one to clear out first.
        self.waves.append(custom.blank_wave())
        if self.write_waves():
            self.reload_data()
            self.speak('Wave %i was added, with nothing in it yet.' % len(self.waves))

    def confirm_delete_wave(self, index: int) -> None:
        wave = self.waves[index]
        count = len(wave.get('Enemies') or {})
        self.host.push_overlay(AlertScreen(
            self.host, 'Delete wave %i?' % (index + 1),
            'It has nothing in it.' if not count else
            'It has %i zombies in it, and they go with it.' % count,
            [('Keep it', None), ('Delete it', lambda i=index: self.delete_wave(i))]))

    def delete_wave(self, index: int) -> None:
        if len(self.waves) <= 1:
            self.speak('A challenge needs at least one wave.')
            return
        self.waves.pop(index)
        if self.write_waves():
            self.reload_data()
            # Two whole sentences rather than one with a plural glued in, as the Zombiepedia's unlock line
            # is written: a translator is offered each of them complete.
            if len(self.waves) == 1:
                self.speak('Wave %i was deleted. One wave left.' % (index + 1))
            else:
                self.speak('Wave %i was deleted. %i waves left.' % (index + 1, len(self.waves)))

    def back_button_pressed(self) -> None:
        App.delegate().go_to_challenge_editor(self.challenge_id)


def custom_max_waves() -> int:
    from ..game import custom
    return custom.MAX_WAVES


@register('Port_EnemyEditorViewController')
class EnemyEditorScreen(ViewControllerScreen, _WaveWork):
    """PORT ADDITION (user request): one zombie - what it is, which wave it is in, and where it comes from.

    The wave it belongs to is a row like any other, so a zombie is moved between waves by stepping it
    rather than by taking it out of one and putting it in another.  That is the whole of what "each zombie
    into a wave of my choosing" needs, and it keeps its bearing, distance and arrival time when it moves:
    the wave is what changed.

    Each change reads back the slack of the wave it is in, so the cost of what you just did is audible.
    """
    page_title = 'Zombie'

    def __init__(self, host, challenge_id: str = '', wave: int = 0, slot: str = ''):
        super().__init__(host)
        self.load_waves(challenge_id)
        self.wave_index = wave
        self.slot = slot
        from ..game import custom
        self.page_title = 'Zombie: %s' % custom.display_name(str(slot).split(' ')[0])

    def place(self) -> dict:
        return (self.waves[self.wave_index].get('Enemies') or {}).get(self.slot) or {}

    def kind(self) -> str:
        return str(self.slot).split(' ')[0]

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='enemyEditor')
        self.table_view = View('', (35, 50, 498, 262), accessible=False, parent=v, ordered=True,
                               name='enemyTable')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title('Waves')

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.reload_data()

    # --- stepping --------------------------------------------------------------------------------
    def step_kind(self, by: int) -> None:
        """Another zombie in the same place, stepping the Zombiepedia's names rather than the game's own.

        The twelve names a player has been shown, not the sixteen keys behind them: `Zombie`, `ZombieB`
        and `ZombieC` are one zombie with three sets of recordings, and three rows nobody can tell apart
        is not a choice.  Which set this one gets is chosen so two of a kind in a wave sound like two.
        The slot is renamed because the kind is read off the front of the key.
        """
        from ..game import custom
        roster = custom.pedia_roster()
        if not roster:
            return
        names = [name for name, _kinds in roster]
        now = custom.display_name(self.kind())
        at = names.index(now) if now in names else 0
        shown, kinds = roster[(at + by) % len(roster)]
        wave = self.waves[self.wave_index]
        if self.slot not in (wave.get('Enemies') or {}):
            return
        # Which set of recordings: the others of this kind already in the wave, so two of a kind are heard
        # as two.  This one is not counted, since it is about to become one of them.
        already = sum(1 for s in (wave.get('Enemies') or {})
                      if s != self.slot and custom.display_name(custom.kind_of(s)) == shown)
        # In place, so it keeps its turn in the wave - and so the zombies after it keep their names.
        self.slot = custom.rename_kind(wave, self.slot, custom.variant_of(kinds, already))
        self.page_title = 'Zombie: %s' % shown
        self.after_change('It is now a %s. %s' % (shown, self.slack_of(wave)))

    def step_wave(self, by: int) -> None:
        from ..game import custom
        if len(self.waves) < 2:
            self.speak('There is only one wave.')
            return
        was = self.wave_index
        wanted = (self.wave_index + by) % len(self.waves)
        if self.slot not in (self.waves[was].get('Enemies') or {}):
            return
        self.slot = custom.move_enemy(self.waves, was, self.slot, wanted)
        self.wave_index = wanted
        self.after_change('Moved to wave %i. That wave now leaves %s, and wave %i leaves %s.'
                          % (wanted + 1, self.slack_of(self.waves[wanted]), was + 1,
                             self.slack_of(self.waves[was])))

    def step_place(self, key: str, choices, by: int, default: float) -> None:
        place = self.place()
        now = place.get(key, default)
        nearest = min(choices, key=lambda v: abs(v - (now or 0.0)))
        at = choices.index(nearest)
        place[key] = choices[max(0, min(len(choices) - 1, at + by))]
        self.after_change(self.slack_of(self.waves[self.wave_index]))

    def after_change(self, said: str) -> None:
        if self.write_waves():
            self.reload_data()
            self.speak(said)

    def reload_data(self) -> None:
        from ..game import custom
        from .challenges import _TableLoader
        step = 'Press Enter for the next value, Shift plus Enter for the previous.'
        place = self.place()
        wave = self.waves[self.wave_index]
        t = _TableLoader(self.table_view)
        t.cell('Zombie', custom.display_name(self.kind()),
               hint='Which zombie this is, by the name the Zombiepedia gives it. Only the ones it has '
                    'unlocked are offered. ' + step,
               action=lambda: self.step_kind(1), shift_action=lambda: self.step_kind(-1))
        t.cell('In wave', '%i of %i' % (self.wave_index + 1, len(self.waves)),
               hint='Which wave it arrives in. It keeps where it comes from and when. ' + step,
               action=lambda: self.step_wave(1), shift_action=lambda: self.step_wave(-1))
        t.cell('Comes from', '%g degrees' % place.get('spawn_angle', 0.0),
               hint='Which way round you it walks in from. ' + step,
               action=lambda: self.step_place('spawn_angle', list(ENEMY_BEARINGS), 1, 0.0),
               shift_action=lambda: self.step_place('spawn_angle', list(ENEMY_BEARINGS), -1, 0.0))
        t.cell('How far away', '%g units' % place.get('spawn_distance', 10.0),
               hint='How far out it starts. Further out is more time to deal with it. ' + step,
               action=lambda: self.step_place('spawn_distance', list(ENEMY_DISTANCES), 1, 10.0),
               shift_action=lambda: self.step_place('spawn_distance', list(ENEMY_DISTANCES), -1, 10.0))
        t.cell('Arrives', 'at %g seconds' % (place.get('spawn_time', 0.0) or 0.0),
               hint='How long after the wave starts it appears. ' + step,
               action=lambda: self.step_place('spawn_time', list(ENEMY_TIMES), 1, 0.0),
               shift_action=lambda: self.step_place('spawn_time', list(ENEMY_TIMES), -1, 0.0))
        t.header('')
        t.cell('This wave', '%i zombies, %s' % (len(wave.get('Enemies') or {}), self.slack_of(wave)),
               hint='What wave %i leaves you at its tightest moment. Negative means nothing a player does '
                    'is fast enough.' % (self.wave_index + 1))
        t.cell('Remove this zombie', hint='Press Enter to take it out of the challenge.',
               action=self.remove)

    def remove(self) -> None:
        from ..game import custom
        wave = self.waves[self.wave_index]
        custom.remove_enemy(wave, self.slot)
        if self.write_waves():
            App.delegate().go_to_wave_editor(self.challenge_id)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_wave_editor(self.challenge_id)


@register('Port_CutsceneEditorViewController')
class CutsceneEditorScreen(ViewControllerScreen):
    """PORT ADDITION (user request): the dialogue of a custom challenge, wave by wave.

    A cutscene here is the original's own scripted sound (`ADSound` 0x1000b2d68) and nothing new: a wave
    may carry several, each with a time or another line to wait for, whether it holds the wave until it has
    finished (`blocker`, which `brickIsCleared` 0x1000a1658 reads) and whether the Skip button ends it.
    What the port adds is where the recording comes from - the game's own are under `game/sounds`, and a
    player's are in the challenges folder's `audio` folder, which Add a line copies them into.

    Each wave has three cutscenes (`custom.PLACES`): one before it, with the arena to itself; one during
    it, over a crowd that is already coming; and one after it, once the wave is cleared.  Before and after
    are what a cutscene usually is - the game's own dialogue holds its zombies back until the line has
    played (see `custom.PLACES`), so a line added here is one of those.  So a challenge is a run of scenes and crowds in whatever order somebody wants them, and the
    one after the last wave is the end of the challenge.  A line is added to the wave and moved between the
    three on its own screen, rather than there being three Add rows on every wave: one row to find is
    better than three to walk past, on a screen that is read out a row at a time.

    This screen writes as it goes rather than waiting for a Save: importing a recording copies a file on
    disk, so there is already no way back from it, and a screen where half of what you did is written and
    half is not is worse than one where all of it is.
    """
    page_title = 'Cutscenes'

    def __init__(self, host, challenge_id: str = ''):
        super().__init__(host)
        from ..game import custom
        self.challenge_id = challenge_id
        d = data.plist(challenge_id) or {}
        self.title_text = str(d.get('title') or challenge_id)
        self.page_title = 'Cutscenes: %s' % self.title_text
        self.waves = custom.waves_of(challenge_id)

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='cutsceneEditor')
        self.table_view = View('', (35, 50, 498, 262), accessible=False, parent=v, ordered=True,
                               name='cutsceneTable')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title('Edit')

    def view_will_appear(self) -> None:
        from ..game import custom
        super().view_will_appear()
        self.waves = custom.waves_of(self.challenge_id)    # a line screen may have changed one
        self.reload_data()

    @staticmethod
    def line_text(line: dict, where: str = 'during') -> str:
        """One line as its row reads it: where in the wave it plays, when, and whether the wave waits."""
        after = line.get('spawn_after')
        if isinstance(after, dict):
            when = 'after %s' % after.get('enemy')
        elif line.get('spawn_time'):
            when = 'at %g seconds' % line['spawn_time']
        else:
            when = 'at the start'
        parts = [PLACE_NAMES[where], when,
                 'holds the wave' if line.get('blocker') else 'does not hold the wave']
        if line.get('skippable'):
            parts.append('skippable')
        if line.get('finalPosition') is not None:
            parts.append('walks past you')
        elif line.get('position') is not None or line.get('spawn_angle') is not None:
            parts.append('placed')
        return ', '.join(parts)

    def reload_data(self) -> None:
        from ..game import custom
        from .challenges import _TableLoader
        t = _TableLoader(self.table_view)
        for index, wave in enumerate(self.waves):
            enemies = len(wave.get('Enemies') or {})
            if enemies == 1:
                t.header('Wave %i, one zombie' % (index + 1))
            elif enemies:
                t.header('Wave %i, %i zombies' % (index + 1, enemies))
            else:
                t.header('Wave %i, no zombies' % (index + 1))
            # In the order they are heard: the scene before the crowd, the dialogue over it, then the
            # scene after it.
            for where in custom.PLACES:
                for place, line in enumerate(custom.cutscene_of(wave, where)):
                    t.cell(line.get('name'), self.line_text(line, where),
                           hint='Press Enter to change this line, or to move it before or after the wave. '
                                'Shift plus Enter removes it.',
                           action=lambda w=index, p=place, g=where: self.open_line(w, p, g),
                           shift_action=lambda w=index, p=place, g=where: self.remove_line(w, p, g))
            t.cell('Add a line to wave %i' % (index + 1),
                   hint='Press Enter to choose a sound file. It is copied into the challenges folder, so '
                        'the challenge can be given to somebody else. It starts as a scene before the '
                        'wave, and its own screen moves it.',
                   action=lambda w=index: self.add_line(w))

    # --- what the rows do ------------------------------------------------------------------------
    def add_line(self, wave: int) -> None:
        from ..game import custom
        from ..platform.filedialog import choose_audio_file
        chosen = choose_audio_file('Choose a sound for wave %i' % (wave + 1))
        if not chosen:
            self.speak('No sound was chosen.')
            return
        try:
            key = custom.import_audio(chosen)
            # An arena that is one file has to stay one file: a recording added to it goes inside it as
            # well as into the audio folder, or the arena would be a file that no longer carries what it
            # speaks with.
            inside = custom.add_to_pack(self.challenge_id, key)
        except OSError as exc:
            log.warning('the sound could not be imported: %s', exc)
            self.speak('That sound could not be copied in: %s' % exc)
            return
        # Before the wave (user request, 2026-10-01).  A line added used to land on the wave itself, over
        # the crowd, which left the zombies walking about while it played - and that is not what the game
        # does.  Counted over the original's own data: of the 220 zombies in bricks that also have dialogue,
        # 124 wait for a line before they arrive and 94 wait for another zombie that does; two have a clock
        # of their own (`maya_2_brick_3`, one Hulk) and none at all simply arrives.  So the line plays and
        # then the zombies come, and that is what a cutscene added here does.
        lines = custom.cutscene_of(self.waves[wave], 'before')
        # It holds the wave until it has finished, and a player who has heard it can press Skip.
        lines.append({'name': key, 'spawn_time': 0.0, 'blocker': True, 'skippable': True,
                      'stopsOtherSounds': False, 'loop': False, 'gain': 0.0})
        custom.set_cutscene(self.waves[wave], 'before', lines)
        said = '%s was added before wave %i.' % (key, wave + 1)
        if inside:
            said += ' It is inside the arena file, so it travels with it.'
        if self.write(said):
            self.reload_data()

    def remove_line(self, wave: int, place: int, where: str = 'during') -> None:
        from ..game import custom
        lines = custom.cutscene_of(self.waves[wave], where)
        if place >= len(lines):
            return
        gone = lines.pop(place)
        custom.set_cutscene(self.waves[wave], where, lines)
        # The recording itself is left in the audio folder: another challenge may be speaking with it, and
        # a line removed by accident is then one Add a line away rather than one file-manager trip.
        if self.write('%s was removed from %s of wave %i. The sound is still in the audio folder.'
                      % (gone.get('name'), PLACE_NAMES[where], wave + 1)):
            self.reload_data()

    def open_line(self, wave: int, place: int, where: str = 'during') -> None:
        play_button_click()
        App.delegate().go_to_cutscene_line(self.challenge_id, wave, place, where)

    def write(self, said: str) -> bool:
        from ..game import custom
        try:
            custom.save_challenge(self.challenge_id, {}, waves=self.waves)
        except Exception as exc:
            log.exception('the cutscene could not be saved')
            self.speak('It could not be saved: %s' % exc)
            return False
        self.speak(said)
        return True

    def back_button_pressed(self) -> None:
        App.delegate().go_to_challenge_editor(self.challenge_id)


#: PORT ADDITION (user request): what each of a wave's three cutscenes is called on a screen.  Written to
#: read as part of a sentence - "bastard_1, before the wave, at the start, holds the wave" - so the row says
#: where a line plays without a column of its own.
PLACE_NAMES = {'before': 'before the wave', 'during': 'during the wave', 'after': 'after the wave'}

#: What a cutscene line's timing row steps through, in seconds.
CUTSCENE_TIMES = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 45.0, 60.0)
#: Where a placed line can be heard from: a bearing, and how far out.
CUTSCENE_BEARINGS = (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330)
CUTSCENE_DISTANCES = (2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0)


@register('Port_CutsceneLineViewController')
class CutsceneLineScreen(ViewControllerScreen):
    """PORT ADDITION (user request): one line of a cutscene, and everything `ADSound` can be told.

    Stepped rows like the challenge editor's.  Two of them are worth saying twice.

    **Where in the wave** moves the line between the wave's three cutscenes (`custom.PLACES`): before the
    wave, during it, or after it.  That is the row a storyline is built with - a scene, then the crowd, then
    a scene - and the one after the last wave is the end of the challenge.

    **Placement** is where the line is heard from.  A line can be centred (heard from everywhere, as
    narration is), placed on a bearing, or made to walk, which is what the original's Dr Bastard does when
    he talks his way around you.  A walking line is `position` and `finalPosition`, and `ADSound.update`
    0x1000b3914 moves it between them at two units a second until it arrives.
    """
    page_title = 'Cutscene line'

    def __init__(self, host, challenge_id: str = '', wave: int = 0, place: int = 0,
                 where: str = 'during'):
        super().__init__(host)
        from ..game import custom
        self.challenge_id = challenge_id
        self.wave_index = wave
        self.place = place
        #: which of the wave's three cutscenes this line is in; the row below moves it between them
        self.where = where if where in custom.PLACES else 'during'
        self.waves = custom.waves_of(challenge_id)
        lines = self.lines() if wave < len(self.waves) else []
        self.line = dict(lines[place]) if place < len(lines) else {}
        self.page_title = 'Line: %s' % (self.line.get('name') or '')

    # --- the cutscene this line is in -------------------------------------------------------------
    def lines(self, where=None) -> list:
        from ..game import custom
        return custom.cutscene_of(self.waves[self.wave_index], where or self.where)

    def set_lines(self, lines, where=None) -> None:
        from ..game import custom
        custom.set_cutscene(self.waves[self.wave_index], where or self.where, lines)

    def step_where(self, by: int) -> None:
        """The line, moved to the cutscene before or after the one it is in now.

        Its timing starts again from the top of its new scene: a line that was waiting for another line of
        the old one cannot wait for it from a wave away, and `_cutscene` refuses a file that says it can.
        """
        from ..game import custom
        order = list(custom.PLACES)
        wanted = order[(order.index(self.where) + by) % len(order)]
        if wanted == self.where:
            return
        staying = self.lines()
        if self.place >= len(staying):
            return
        staying.pop(self.place)
        self.set_lines(staying)
        self.line.pop('spawn_after', None)
        self.line.setdefault('spawn_time', 0.0)
        arriving = self.lines(wanted) + [self.line]
        self.set_lines(arriving, wanted)
        self.where, self.place = wanted, len(arriving) - 1
        self.save_waves()
        self.reload_data()
        self.speak('%s now plays %s.' % (self.line.get('name'), PLACE_NAMES[self.where]))

    # --- placement is three states rather than a pile of keys -------------------------------------
    def placement(self) -> str:
        if self.line.get('finalPosition') is not None:
            return 'walks past you'
        if self.line.get('position') is not None or self.line.get('spawn_angle') is not None:
            return 'placed'
        return 'centred'

    def step_placement(self, by: int) -> None:
        order = ['centred', 'placed', 'walks past you']
        now = order.index(self.placement())
        wanted = order[(now + by) % len(order)]
        for key in ('position', 'finalPosition', 'spawn_angle', 'spawn_distance'):
            self.line.pop(key, None)
        if wanted == 'placed':
            self.line['spawn_angle'] = 90.0
            self.line['spawn_distance'] = 6.0
        elif wanted == 'walks past you':
            # Across the front of the player and out the other side, which is the shape the original's
            # moving lines use and the one a listener can actually follow.
            self.line['position'] = '{-8, 4}'
            self.line['finalPosition'] = '{8, 4}'
        self.write()

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='cutsceneLine')
        self.table_view = View('', (35, 50, 498, 262), accessible=False, parent=v, ordered=True,
                               name='cutsceneLineTable')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title('Cutscenes')

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.reload_data()

    def _others(self) -> list:
        """The other lines of this cutscene, which this one may be told to wait for.  Of this cutscene and
        not of this wave: each of the three is a wave of its own by the time the game plays it, and a line
        cannot wait for one that is not on at the same time."""
        return [line.get('name') for i, line in enumerate(self.lines()) if i != self.place]

    def when_text(self) -> str:
        after = self.line.get('spawn_after')
        if isinstance(after, dict):
            return 'after %s has finished' % after.get('enemy')
        return 'at %g seconds' % (self.line.get('spawn_time') or 0.0)

    def step_when(self, by: int) -> None:
        """Every time on the ladder, and then each of the other lines of the wave to wait for."""
        options = [('at', t) for t in CUTSCENE_TIMES] + [('after', n) for n in self._others()]
        after = self.line.get('spawn_after')
        now = ('after', after.get('enemy')) if isinstance(after, dict) else \
              ('at', min(CUTSCENE_TIMES, key=lambda t: abs(t - (self.line.get('spawn_time') or 0.0))))
        at = options.index(now) if now in options else 0
        kind, value = options[(at + by) % len(options)]
        if kind == 'at':
            self.line.pop('spawn_after', None)
            self.line['spawn_time'] = value
        else:
            self.line.pop('spawn_time', None)
            self.line['spawn_after'] = {'enemy': value, 'time': 0.0, 'afterStart': False}
        self.write()

    def step_sound(self, by: int) -> None:
        from ..game import custom
        keys = sorted(custom.audio_files())
        if not keys:
            return
        now = self.line.get('name')
        at = keys.index(now) if now in keys else 0
        self.line['name'] = keys[(at + by) % len(keys)]
        self.write()

    def toggle(self, key: str) -> None:
        self.line[key] = not bool(self.line.get(key))
        self.write()

    def step_value(self, key: str, choices, by: int, default=0.0) -> None:
        now = self.line.get(key, default) or default
        nearest = min(choices, key=lambda v: abs(v - now))
        at = choices.index(nearest)
        self.line[key] = choices[max(0, min(len(choices) - 1, at + by))]
        self.write()

    def reload_data(self) -> None:
        from ..game import custom
        from .challenges import _TableLoader
        step = 'Press Enter for the next value, Shift plus Enter for the previous.'
        t = _TableLoader(self.table_view)
        t.cell('Sound', self.line.get('name') or 'none',
               hint='Which recording in the audio folder this line plays. ' + step,
               action=lambda: self.step_sound(1), shift_action=lambda: self.step_sound(-1))
        t.cell('Where in the wave', PLACE_NAMES[self.where],
               hint='Before the wave and after it are scenes with the arena to themselves: nothing is '
                    'walking while they play, which is how the game itself does its dialogue. During the '
                    'wave is the unusual one, talking over a crowd that is already coming. After the last '
                    'wave is the end of the challenge. ' + step,
               action=lambda: self.step_where(1), shift_action=lambda: self.step_where(-1))
        t.cell('Plays', self.when_text(),
               hint='When it starts: a time from this cutscene beginning, or after another line of the '
                    'same cutscene has finished. ' + step,
               action=lambda: self.step_when(1), shift_action=lambda: self.step_when(-1))
        t.cell('Holds the wave', 'yes' if self.line.get('blocker') else 'no',
               hint='When it holds, the wave is not finished until this line is - so the challenge waits '
                    'for it even with nothing left to kill. Press Enter to toggle.',
               action=lambda: self.toggle('blocker'))
        t.cell('Can be skipped', 'yes' if self.line.get('skippable') else 'no',
               hint='Whether the Skip button ends it. Press Enter to toggle.',
               action=lambda: self.toggle('skippable'))
        t.cell('Silences other sounds', 'yes' if self.line.get('stopsOtherSounds') else 'no',
               hint='Whether starting this line stops everything else in the wave. Press Enter to toggle.',
               action=lambda: self.toggle('stopsOtherSounds'))
        t.cell('Loops', 'yes' if self.line.get('loop') else 'no',
               hint='Whether it plays over and over. A looping line that holds the wave would never let '
                    'it end, so it is worth one or the other. Press Enter to toggle.',
               action=lambda: self.toggle('loop'))
        gain = self.line.get('gain') or 0.0
        t.cell('Loudness', 'as recorded' if not gain else '%g' % gain,
               hint='Louder than the recording is, for a line that is too quiet under the arena. ' + step,
               action=lambda: self.step_value('gain', [0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0], 1),
               shift_action=lambda: self.step_value('gain', [0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0], -1))
        t.cell('Placement', self.placement(),
               hint='Centred is heard from everywhere at once, the way narration is. Placed is heard from '
                    'one direction. Walks past you crosses the arena while it talks. ' + step,
               action=lambda: self.step_placement(1), shift_action=lambda: self.step_placement(-1))
        if self.placement() == 'placed':
            t.cell('Heard from', '%g degrees' % (self.line.get('spawn_angle') or 0.0),
                   hint='Which way round you it is. ' + step,
                   action=lambda: self.step_value('spawn_angle', list(CUTSCENE_BEARINGS), 1),
                   shift_action=lambda: self.step_value('spawn_angle', list(CUTSCENE_BEARINGS), -1))
            t.cell('How far away', '%g units' % (self.line.get('spawn_distance') or 6.0),
                   hint='How far out it stands. ' + step,
                   action=lambda: self.step_value('spawn_distance', list(CUTSCENE_DISTANCES), 1, 6.0),
                   shift_action=lambda: self.step_value('spawn_distance', list(CUTSCENE_DISTANCES), -1, 6.0))
        t.header('')
        t.cell('Hear it', hint='Press Enter to play this recording now, as the arena will.',
               action=self.preview)
        t.cell('Remove this line', hint='Press Enter to take it out of the wave. The recording stays in '
                                        'the audio folder.', action=self.remove)
        _ = custom

    # --- actions ---------------------------------------------------------------------------------
    def preview(self) -> None:
        """PORT ADDITION: the recording, played through the engine as the arena would play it.

        Not through the wave's own playlist, which only exists while the wave is loaded: a sound of its own
        on the file, so a line can be heard while it is being placed rather than only by playing the
        challenge.
        """
        from ..game import custom
        from ..s3d.engine import S3DEngine
        path = custom.audio_path(self.line.get('name'))
        if not path:
            self.speak('That recording is no longer in the audio folder.')
            return
        try:
            sound = S3DEngine.engine().sound_from_path(path)
            if sound is None:
                raise RuntimeError('it could not be loaded')
            sound.play(False)
        except Exception as exc:
            log.exception('the cutscene line could not be previewed')
            self.speak('It could not be played: %s' % exc)

    def remove(self) -> None:
        lines = self.lines()
        if self.place < len(lines):
            lines.pop(self.place)
        self.set_lines(lines)
        self.save_waves()
        App.delegate().go_to_cutscene_editor(self.challenge_id)

    def write(self) -> None:
        """The edited line back into its cutscene, and the waves back into the file."""
        lines = self.lines()
        if self.place < len(lines):
            lines[self.place] = self.line
            self.set_lines(lines)
        self.save_waves()
        self.reload_data()

    def save_waves(self) -> None:
        from ..game import custom
        try:
            custom.save_challenge(self.challenge_id, {}, waves=self.waves)
        except Exception as exc:
            log.exception('the cutscene line could not be saved')
            self.speak('It could not be saved: %s' % exc)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_cutscene_editor(self.challenge_id)


@register('Port_ChallengeMakerViewController')
class ChallengeMakerScreen(ViewControllerScreen):
    """PORT ADDITION (user request): where a challenge is made.

    Opening this screen is what makes the challenges folder appear beside the executable
    (`paths.custom_challenges_dir`), so a player who wants to write one by hand has somewhere to put it
    before they have written anything.

    What it generates is a crowd, sized rather than guessed.  This game has no player health - one enemy
    reaching you ends the run - so what makes a wave hard is not the life in it but whether each enemy can
    be killed before its own clock runs out, and `custom._size_wave` widens the gap between arrivals until
    the tightest moment leaves the slack the roll asked for.  The enemies are whatever the Zombiepedia has
    unlocked and no more, so a fresh profile is handed the seven it has been shown and a Colossus joins
    them at 450 kills.
    """
    page_title = 'Challenge maker'

    def load_view(self) -> None:
        from .. import paths
        from ..game import custom
        folder = paths.custom_challenges_dir()             # this is what makes the folder appear
        custom.load(force=True)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='challengeMaker')
        # Naming one comes first: a challenge somebody sat down to make is the point of this screen, and
        # generating one is the shortcut past it rather than the other way round (user request).
        new_one = Button('Create a challenge', (172, 34, 227, 30), parent=v,
                         actions=[self.create_one], name='maker new')
        new_one.hint = 'Press Enter to name a challenge of your own and start editing it.'
        new_arena = Button('Create an arena', (172, 72, 227, 30), parent=v,
                           actions=[self.create_arena], name='maker new arena')
        new_arena.hint = 'Press Enter to name an arena of your own, with a first challenge in it.'
        one = Button('Generate a challenge', (172, 110, 227, 30), parent=v,
                     actions=[self.generate_one], name='maker one')
        one.hint = 'Press Enter to make one challenge at random and put it in the challenges folder.'
        pack = Button('Generate an arena', (172, 148, 227, 30), parent=v,
                      actions=[self.generate_pack], name='maker pack')
        pack.hint = 'Press Enter to make an arena of several challenges at random, as one pack file.'
        folder_button = Button('Open the challenges folder', (172, 186, 227, 30), parent=v,
                               actions=[self.open_folder], name='maker folder')
        folder_button.hint = 'Press Enter to open it in the file manager.'
        again = Button('Read the folder again', (172, 224, 227, 30), parent=v,
                       actions=[self.reload_folder], name='maker reload')
        again.hint = 'Press Enter after editing a file by hand, to pick the change up without restarting.'
        self.status_view = View('', (172, 262, 227, 30), parent=v, name='maker status')
        View('The folder is called challenges and sits beside the game. A file in it ending in %s is one '
             'challenge and a file ending in %s is an arena of several; both are written in JSON and can '
             'be edited in any text editor.' % (custom.CHALLENGE_SUFFIX, custom.PACK_SUFFIX),
             (172, 310, 227, 60), parent=v, name='maker help')
        View('The folder is at %s' % folder, (172, 375, 227, 20), parent=v, name='maker path')
        self.problem_views: list = []
        self.first_accessible_element = new_one
        self.roots = [v]
        self.read_out_status()

    def read_out_status(self) -> None:
        """The line under the buttons: what the folder holds, and what in it could not be read."""
        from ..game import custom
        arenas = custom.arenas()
        found = sum(len(ids) for _title, ids in arenas)
        if found == 1:
            self.status_text = 'The folder holds one challenge.'
        elif found:
            self.status_text = 'The folder holds %i challenges in %i arenas.' % (found, len(arenas))
        else:
            self.status_text = 'The folder is empty.'
        self.status_view.label = self.status_text
        for view in self.problem_views:
            self.view.children.remove(view)
        self.problem_views = []
        # A narrow band between the status line and the help text, so however many there are they are read
        # after the one and before the other: `reading_order` sorts by the vertical centre of a frame.
        for i, (name, why) in enumerate(custom.problems()):
            self.problem_views.append(
                View('%s was skipped: %s' % (name, why), (172, 292 + i * 4, 227, 4), parent=self.view,
                     name='maker problem %i' % (i + 1)))

    def view_did_load(self) -> None:
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        sb.back_button.set_title('Custom')

    def create_one(self) -> None:
        """PORT ADDITION (user request): name a challenge and start editing it.

        It is made playable rather than empty (`custom.starter_challenge`): one crowd sized against the
        guns its owner actually has, so the first thing you can do with a challenge you have just named is
        press Play on it.
        """
        from ..game import custom

        def done(typed):
            if typed is None:
                return
            try:
                cid = custom.create_challenge(typed)
            except Exception as exc:
                log.exception('the challenge could not be created')
                self.speak('It could not be made: %s' % exc)
                return
            self.speak('%s was made. Edit it now.' % typed)
            App.delegate().go_to_challenge_editor(cid)
        ask_for_text(self, 'Name your challenge', on_done=done, what='title')

    def create_arena(self) -> None:
        """PORT ADDITION (user request): name an arena, with a first challenge in it.

        An arena with nothing in it is a file the reader refuses and a row that opens on nothing, so
        naming one makes its first challenge at the same time; more are added from the arena's own list.
        """
        from ..game import custom

        def done(typed):
            if typed is None:
                return
            if typed in [t for t, _i in custom.arenas()]:
                self.speak('There is already an arena called %s.' % typed)
                return
            try:
                custom.create_arena(typed)
            except Exception as exc:
                log.exception('the arena could not be created')
                self.speak('It could not be made: %s' % exc)
                return
            self.read_out_status()
            self.speak('%s was made, with one challenge in it.' % typed)
            App.delegate().go_to_custom_arena(typed)
        ask_for_text(self, 'Name your arena', on_done=done, what='name')

    def generate_one(self) -> None:
        from ..game import custom
        try:
            _path, title = custom.generate_challenge()
        except Exception as exc:                          # a button a player presses never crashes the game
            log.exception('a challenge could not be generated')
            self.speak('The challenge could not be made: %s' % exc)
            return
        self.read_out_status()
        self.speak('%s was made, and is in the Custom list.' % title)

    def generate_pack(self) -> None:
        from ..game import custom
        try:
            _path, arena, count = custom.generate_pack()
        except Exception as exc:                          # as above
            log.exception('an arena could not be generated')
            self.speak('The arena could not be made: %s' % exc)
            return
        self.read_out_status()
        self.speak('%s was made, with %i challenges in it, and is in the Custom list.' % (arena, count))

    def reload_folder(self) -> None:
        from ..game import custom
        custom.load(force=True)
        self.read_out_status()
        self.speak(self.status_text)                      # the English, which `speak` translates itself

    @staticmethod
    def open_folder() -> None:
        """PORT ADDITION: the folder in the file manager, since a player editing a challenge by hand has to
        get to it and reading a path out loud is not getting to it."""
        import subprocess
        from .. import paths
        from ..platform import host as platform_host
        folder = paths.custom_challenges_dir()
        try:
            if platform_host.MAC:
                subprocess.Popen(['open', folder])
            else:
                os.startfile(folder)                      # noqa: S606 - the folder is the game's own
        except (OSError, AttributeError) as exc:
            log.info('the challenges folder could not be opened: %s', exc)

    def back_button_pressed(self) -> None:
        App.delegate().go_to_custom_menu()


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
                'These arenas are not from the original game. They were made for this version, and '
                'Dr. Bastard has had a long time to think about them.\n \nNone of them tells you how it is '
                'won. Survive one and the next opens. Earn enough stars, and another chapter is waiting.\n \n'
                'They tell a story, The Long Way Home, in text: now and then a wave waits while a part of it '
                'is read, and goes on when you do.\n \nA death need not be the end of an arena. Diamonds buy '
                'a revive, which plays the wave again, or, for ten times as much, a skip to the next wave, '
                'though never past the last.')
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
