"""Challenge screens: world list, challenge selector and overview, challenge completed and failed.

Screen reader path (the one the port targets): ADWorldChallengeListViewController,
Accessible_ADChallengeSelectorViewController, Accessible_ADChallengeOverviewViewController,
Accessible_ADChallengeCompletedViewController and ADChallengeFailedViewController (no accessible variant).

Tables are read like VoiceOver reads a UITableView: a section header label as static text, then each
ADAccessibleTableCell (UITableViewCellStyleSubtitle) as "text, detail"; Enter selects the row.
"""
from __future__ import annotations

import logging

from ..app import App
from ..game import data
from ..game.challenge_data import ChallengeData
from ..game.parameters import GameParameters
from ..platform import crand
from ..platform.cfloat import f32
from ..platform.defaults import ns_float_value, ns_int_value
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from . import results
from .accessibility import CELL, STATIC_TEXT, Button, View, play_button_click
from .gameover import AccessibleGameOverEndlessScreen, time_string_from_seconds
from .host import register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.challenges')


def _challenge_rows(challenge: dict, outcome: str) -> list:
    """PORT ADDITION: the first two lines of a challenge's Copy results - which challenge, and how it
    ended - so the paste still says what the old heading did now that the heading is the same for both."""
    rows = [(False, 'Challenge', challenge.get('title'))] if challenge.get('title') else []
    return rows + [(False, 'Result', outcome)]


def _statistics_heading(challenge: dict) -> str:
    """PORT ADDITION: the first line of a challenge's Copy results.  An Extra arena's says so (user request,
    2026-09-29), so a paste of one is not taken for one of the original's challenges."""
    from ..game.additions import chapter_of
    if chapter_of(challenge.get('challenge_id')) is not None:
        return 'Audio Defence Extra Challenge Statistics'
    return 'Audio Defence Challenge Statistics'


def _play_buttons_sound(key: str) -> None:
    """playButtonSound of the challenge screens: S3DSound <key> of the "buttons" playlist at gain 3."""
    pl = S3DEngine.engine().play_list_with_name('buttons')
    sound = pl.sound(key) if pl is not None else None
    if sound is not None:
        sound.set_gain(3.0)
        sound.play()


class _TableLoader:
    """[tableView reloadData]: rows are laid out again in order.  A row keeps its view object across reloads,
    so VoiceOver stays on the same row (as it stays on the same index path)."""

    def __init__(self, table: View):
        self.table = table
        self.old = list(table.children)
        table.children.clear()

    def _view(self, traits) -> View:
        i = len(self.table.children)
        if i < len(self.old) and self.old[i].traits == traits:
            v = self.old[i]
            v.actions.clear()
            v.shift_actions.clear()
            v.hint = None
            v.selected = False
            # PORT ADDITION: what Delete removes on a Settings binding row belongs to that row only, not to
            # whatever row reuses its view after a change of category
            v.__dict__.pop('binding_action', None)
            v.__dict__.pop('pad_binding_action', None)
            self.table.children.append(v)
            return v
        return View('', self.table.frame, traits=traits, parent=self.table)

    def header(self, text: str) -> View:
        """viewForHeaderInSection: a UILabel (ADAccessibilityTableHeaderLabel); an empty label is not read."""
        v = self._view(STATIC_TEXT)
        v.label = v.text = text or ''
        v.hidden = not text
        results.mark_header(v)                            # PORT ADDITION: for Copy results
        return v

    def cell(self, text, detail=None, hint=None, action=None, shift_action=None) -> View:
        v = self._view(CELL)
        v.label = ', '.join(str(p) for p in (text, detail) if p)
        results.mark_cell(v, text, detail)                # PORT ADDITION: for Copy results
        v.hint = hint
        if action is not None:
            v.add_target(action)
        if shift_action is not None:                      # PORT ADDITION: Shift+Enter on this row
            v.shift_actions.append(shift_action)
        return v


def game_over_with_stats_view_did_load(screen) -> None:
    """-[ADGameOverWithStatsViewController viewDidLoad] 0x100041958, after its [super viewDidLoad].

    initScrollView (swipe recognizers) and the stat labels are visual: those outlets are not in these nibs."""
    from ..game.ingame_stats import InGameStats
    from ..game.inventory import Inventory
    from ..game.modifiers import GameModifiers
    from ..game.persistent_stats import PersistentStats
    GameModifiers.shared().reset_modifiers()
    sb = screen.status_bar_view_controller
    sb.delegate = screen
    sb.armory_loadout_enabled = True
    # DIVERGENCE: [self ignoreRewards] is sent at 0x100042030 and its answer thrown away, so the crediting
    # below runs on every screen of this family - the challenge overview included, which sets ignoreRewards
    # to YES precisely to avoid it.  Opening the overview after a game therefore paid the last game's coins
    # and diamonds a second time, and again each time you looked.  The answer is tested here.
    if screen.ignore_rewards:
        return
    inv = Inventory.shared()
    stats = InGameStats.singleton()
    inv.set_coins(inv.coins + stats.total_coins)
    inv.set_diamonds(inv.diamonds + stats.diamond_loot)
    ps = PersistentStats.shared()                         # PORT ADDITION: what the run earned, for the stats
    ps.save_coins_earned(stats.total_coins)
    ps.save_diamonds_earned(stats.diamond_loot)


def challenge_view_did_load(screen) -> None:
    """-[ADChallengeViewController viewDidLoad] 0x100077170, after its [super viewDidLoad].

    challengeTitle / challengeIcon are nil in these nibs; initStarUnlockArea builds ADStarUnlockViewController
    views for a starUnlockArea that is nil (visual only)."""
    sb = screen.status_bar_view_controller
    sb.armory_loadout_enabled = False
    sb.delegate = screen


# ========================================================================================= world list
@register('ADWorldChallengeListViewController')
class WorldChallengeListScreen(ViewControllerScreen):
    """ADWorldChallengeListViewController (no accessible nib: tag-2781 view #26, table #6 = firstAccessibleElement)."""
    page_title = 'Challenge'

    def __init__(self, host):                             # initWithNibName:bundle: 0x10004ba74
        super().__init__(host)
        self.number_of_sections_for_stats = 1
        self.world_names: list = []
        self.total_stars_unlocked = 0

    def load_view(self) -> None:                          # 0x10004c168
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#26')
        self.table_view = View('', (170, 124, 235, 206), accessible=False, parent=v, ordered=True, name='#6')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x10004bb48
        super().view_did_load()
        sb = self.status_bar_view_controller
        # [[sb pageTitle] setText:@"CHALLENGE"]: no pageTitle outlet in the iPhone nib
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        index = data.plist('challenges_index') or {}
        cd = ChallengeData.shared()
        # viewDidLoad_block_invoke 0x10004c04c answers NSOrderedDescending when a's requirement is larger and
        # NSOrderedSame otherwise: an ascending sort (every world has a different requirement)
        self.world_names = sorted(index.keys(), key=lambda w: cd.stars_requirement_for_world(w))
        self.total_stars_unlocked = cd.total_stars_unlocked()
        # registerNib: for "arenaCell" is only used without VoiceOver

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.reload_data()

    def reload_data(self) -> None:
        cd = ChallengeData.shared()
        t = _TableLoader(self.table_view)
        t.header('')                                      # tableView:viewForHeaderInSection: 0x10004c318
        for row, world in enumerate(self.world_names):   # tableView:cellForRowAtIndexPath: 0x10004c644
            if self.total_stars_unlocked >= cd.stars_requirement_for_world(world):
                n = cd.number_of_challenges_for_world(world)
                detail = 'Stars unlocked %i / %i' % (cd.total_stars_unlocked_for_world(world), n + (n << 1))
            else:
                detail = 'You need %i stars to play this level' % cd.stars_requirement_for_world(world)
            t.cell(world, detail, action=lambda r=row: self.select_row(r))

    def select_row(self, row: int) -> None:
        # tableView:willSelectRowAtIndexPath: 0x10004d118 returns nil for a locked world
        if self.total_stars_unlocked < ChallengeData.shared().stars_requirement_for_world(self.world_names[row]):
            return
        self.did_select_row(row)

    def did_select_row(self, row: int) -> None:           # tableView:didSelectRowAtIndexPath: 0x10004d270
        world = self.world_names[row]
        if self.total_stars_unlocked < ChallengeData.shared().stars_requirement_for_world(world):
            return
        _play_buttons_sound('start_button')              # playButtonSound 0x10004d534
        GameParameters.shared().last_challenge_world = world
        App.delegate().go_to_challenge_selector()

    def back_button_pressed(self) -> None:                # 0x10004d494
        App.delegate().go_to_play_menu()


# ================================================================================= challenge selector
@register('Accessible_ADChallengeSelectorViewController')
class AccessibleChallengeSelectorScreen(ViewControllerScreen):
    """Accessible_ADChallengeSelectorViewController : ADChallengeSelectorViewController.
    ADChallengeSelectorViewController loadView (0x1000ca010) loads nib Accessible_ADChallengeSelectorViewController
    while VoiceOver runs: view #14, table #2 = firstAccessibleElement."""
    page_title = 'Challenge'

    def __init__(self, host, world_name=None, challenge_to_load=None):   # initWithNibName:bundle:loadChallenge:worldName: 0x100053f18
        super().__init__(host)
        self.challenge_to_load = challenge_to_load        # goToChallengeSelector (0x1000816e0) always passes nil
        entry = (data.plist('challenges_index') or {}).get(world_name) or {}
        self.challenge_files = entry.get('challenges') or []
        self.world_name = world_name
        if world_name:                                    # the world row that opened this list names it
            self.page_title = str(world_name)

    @staticmethod
    def dictionary_for_challenge_with_name(name):         # ADChallengeSelectorViewController 0x1000c9c58
        return data.plist(name)

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 480, 320), accessible=False, name='#14')
        self.table_view = View('', (0, 40, 480, 280), accessible=False, parent=v, ordered=True, name='#2')
        self.first_accessible_element = self.table_view
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x10005419c
        super().view_did_load()
        sb = self.status_bar_view_controller              # ADChallengeSelectorViewController viewDidLoad 0x1000c9d4c
        sb.set_armory_button_visibility(True)
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        # challengeWorldLabel / contentView / pageTitle: not in the accessible nib
        if self.challenge_to_load is not None:            # dispatch_after 0.2 s
            name = self.challenge_to_load
            from ..platform.runloop import RunLoop
            RunLoop.main().call_later(0.2, lambda: App.delegate().go_to_accessible_challenge_overview_with_dictionary(
                self.dictionary_for_challenge_with_name(name)))
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(False)
        # 0x1000542c4: "if (challengeToLoad == nil) challengeToLoad = nil" - it is never cleared

    def view_will_appear(self) -> None:                   # ADChallengeSelectorViewController 0x1000ca1a0
        super().view_will_appear()
        # initChallengeList only builds ADChallengeIconViewController views for a nil scroll view.
        # [self loadChallengeWithName:challengeToLoad] with nil: -hasWeaponForChallengeWithName:nil answers YES,
        # so it asks the delegate to load ADChallengeOverviewViewController - which -loadViewController:
        # (0x1000811bc) starts with [rootViewController dismissViewControllerAnimated:YES completion:], and
        # UIKit ignores that while this screen's own presentation (or the armory's dismissal) is running.
        self.reload_data()                                # viewWillLayoutSubviews 0x1000554e0

    def reload_data(self) -> None:
        t = _TableLoader(self.table_view)
        if self.challenge_to_load is not None:            # numberOfSectionsInTableView: 0x100054558 / rows 0x1000544d0
            return
        for row, name in enumerate(self.challenge_files):   # tableView:cellForRowAtIndexPath: 0x100054570
            d = self.dictionary_for_challenge_with_name(name) or {}
            status = self.status_for_challenge_with_dict(d)
            # PORT INPUT: the original hint is "double tap to play this challenge"
            hint = None if status == 'locked' else 'Press Enter to play this challenge.'
            cell = t.cell(d.get('title'), status, hint=hint, action=lambda r=row: self.did_select_row(r))
            cell.label_key_words = True                   # PORT ADDITION: "press Enter to go to armory"

    @staticmethod
    def status_for_challenge_with_dict(d: dict) -> str:   # statusForChallengeWithDict: 0x100054960
        from ..game.inventory import Inventory
        from ..game.weapon_manager import WeaponManager
        for w in d.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                name = WeaponManager.shared().display_name_for_item_with_name(w.get('name'))
                # PORT INPUT: the original says "%@ required, double tap to go to armory"
                return '%s required, press Enter to go to armory' % name
        cd = ChallengeData.shared()
        for req in d.get('challenges_requirement') or []:
            if not cd.has_completed_challenge_with_name(req):
                return 'locked'
        cid = d.get('challenge_id')
        stars = (1 if cd.has_completed_challenge_with_name(cid) else 0) \
            + (1 if cd.has_accuracy_star_for_challenge_with_name(cid) else 0) \
            + (1 if cd.has_time_limit_star_for_challenge_with_name(cid) else 0)
        return '%i star%s unlocked' % (stars, 's' if stars > 1 else '')

    def did_select_row(self, row: int) -> None:           # tableView:didSelectRowAtIndexPath: 0x100054f8c
        # PORT ADDITION: the original plays nothing here - its buttons click (ADButtonWithFont playSound
        # 0x100073578) but its table rows never do, and the world list one screen up plays start_button
        # from its own playButtonSound.  Opening a challenge was therefore the one step of that walk with
        # no sound at all, which on a keyboard is indistinguishable from a key that did not register.
        # The click goes on the paths that do something; a locked row stays silent, because nothing happens.
        from ..game.inventory import Inventory
        d = self.dictionary_for_challenge_with_name(self.challenge_files[row]) or {}
        for w in d.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                play_button_click()
                App.delegate().go_to_armory(self, False)
                return
        cd = ChallengeData.shared()
        for req in d.get('challenges_requirement') or []:
            if not cd.has_completed_challenge_with_name(req):
                return
        play_button_click()
        App.delegate().go_to_accessible_challenge_overview_with_dictionary(d)

    def back_button_pressed(self) -> None:                # ADChallengeSelectorViewController 0x1000cb9b8
        App.delegate().go_to_world_selector()


# ================================================================================== challenge overview
@register('Accessible_ADChallengeOverviewViewController')
class AccessibleChallengeOverviewScreen(ViewControllerScreen):
    """Accessible_ADChallengeOverviewViewController : ADChallengeOverviewViewController : ADChallengeViewController
    : ADGameOverWithStatsViewController : ADViewController.  ADChallengeOverviewViewController loadView
    (0x1000d8688) loads nib Accessible_ADChallengeOverviewViewController (#35) while VoiceOver runs."""
    page_title = 'Challenge'

    def __init__(self, host, dictionary=None):            # ADChallengeOverviewViewController initWithDictionary: 0x1000d8178
        super().__init__(host)
        self.challenge_dict = dictionary or {}
        self.ignore_rewards = True
        self.required_weapon = None
        if self.challenge_dict.get('title'):              # the challenge row that opened this screen names it
            self.page_title = str(self.challenge_dict['title'])

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 480, 320), accessible=False, name='#35')
        self.table_view = View('', (0, 37, 480, 244), accessible=False, parent=v, ordered=True, name='#27')
        self.play_button = Button('PLAY', (183, 282, 128, 38), parent=v, font_button=False,
                                  actions=[self.play_button_pressed], name='#47')
        self.roots = [v]

    def view_did_load(self) -> None:                      # ADChallengeOverviewViewController viewDidLoad 0x1000d8248
        super().view_did_load()                           # ADViewController (no firstAccessibleElement outlet)
        game_over_with_stats_view_did_load(self)
        challenge_view_did_load(self)
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.armory_loadout_enabled = False
        sb.delegate = self
        # loadMissionOverlay (0x100018de4) adds ADMissionTopbarViewController's view, which sets its own alpha
        # to 0 (0x100019cd0): VoiceOver skips it.  loadEquipment is overridden empty (0x10004037c).

    def view_will_appear(self) -> None:                   # 0x10003e980
        from ..game.inventory import Inventory
        super().view_will_appear()
        b = self.play_button
        b.enabled = True
        b.set_title('Play')
        b.label = 'Play'                                  # no accessibilityLabel: VoiceOver reads the title
        b.hint = ''
        for w in self.challenge_dict.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                self.required_weapon = w.get('name')
                title = 'You need to purchase a %s in the armory to play this challenge' % self.required_weapon
                b.set_title(title)
                b.label = title
                b.hint = 'Use the armory button to purchase weapons'
                b.enabled = False
                break
        else:
            sb = self.status_bar_view_controller
            sb.set_armory_button_visibility(True)
            sb.set_currencies_visibility(False)
        self.reload_data()                                # viewWillLayoutSubviews 0x100040384

    def reload_data(self) -> None:
        from ..game.weapon_manager import WeaponManager
        cd = ChallengeData.shared()
        d = self.challenge_dict
        cid = d.get('challenge_id')
        weapons = d.get('weapons') or []
        wm = WeaponManager.shared()
        t = _TableLoader(self.table_view)
        # numberOfSectionsInTableView: 3; rows per section 2 / 3 / 3 (tconst_100181ba0)
        header = t.header('Challenge Info')               # tableView:viewForHeaderInSection: 0x10003efe8
        # tableView:cellForRowAtIndexPath: 0x10003f230
        t.cell(d.get('title'), 'Title')
        t.cell(d.get('objective'), 'Objective')
        t.header('Loadout')
        for row in range(3):
            w = weapons[row] if row < len(weapons) else {}
            if ns_int_value(w.get('ammo')) >= 1:
                detail = '%i bullets' % ns_int_value(w.get('ammo'))
            elif wm.is_melee_for_weapon_with_name(w.get('name')):
                detail = 'melee weapon'
            else:
                detail = 'empty'
            t.cell(wm.display_name_for_item_with_name(w.get('name')), detail)
        t.header('Stars')
        if cd.has_completed_challenge_with_name(cid):
            detail = 'already unlocked'
        else:
            detail = 'finish challenge to get %i coins' % ns_int_value((d.get('mission_star') or {}).get('reward'))
        t.cell('Challenge completed star', detail)
        acc = d.get('accuracy_star') or {}
        if cd.has_accuracy_star_for_challenge_with_name(cid):
            detail = 'already unlocked'
        else:
            detail = 'Accuracy goal : %i%% -- Reward : %i coins' % (ns_int_value(acc.get('objective')),
                                                                  ns_int_value(acc.get('reward')))
        t.cell('Accuracy star', detail)
        tl = d.get('time_limit_star') or {}
        if cd.has_time_limit_star_for_challenge_with_name(cid):
            detail = 'already unlocked'
        else:
            detail = 'Time goal : %i seconds -- Reward : %i coins' % (ns_int_value(tl.get('objective')),
                                                                    ns_int_value(tl.get('reward')))
        t.cell('Time limit star', detail)
        # the header of section 0 posts UIAccessibilityScreenChangedNotification with itself
        self.post_screen_changed(header)

    def play_button_pressed(self) -> None:                # ADChallengeOverviewViewController 0x1000d8b48
        _play_buttons_sound('start_level_button')         # playButtonSound 0x1000d8d50
        App.delegate().go_to_challenge_with_dict(self.challenge_dict)

    def back_button_pressed(self) -> None:                # ADChallengeOverviewViewController 0x1000d8cb0
        # PORT ADDITION: back to the list it was chosen from (App.go_to_challenge_list_for)
        App.delegate().go_to_challenge_list_for(self.challenge_dict.get('challenge_id'))

    # REMOVED (user request): the magic tap 0x1000403e0 pressed Play, even while Play was disabled.


# =================================================================================== challenge failed
@register('ADChallengeFailedViewController')
class ChallengeFailedScreen(ViewControllerScreen):
    """ADChallengeFailedViewController : ADChallengeViewController (no accessible nib: tag-2781 view #67)."""
    page_title = 'Challenge failed'

    def __init__(self, host, dictionary=None):            # ADChallengeViewController initWithDictionary: 0x1000770bc
        super().__init__(host)
        self.challenge_dict = dictionary or {}
        self.ignore_rewards = False
        self.game_over_playlist = None

    def load_view(self) -> None:                          # 0x100071cd0 (the 2781 layout keeps the nib's outlets)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#67')
        self.tip_text_view = View('Lorem ipsum dolor sit er elit lamet, consectetaur cillium adipisicing pecu, sed '
                                  'do eiusmod tempor incididunt ut labore et dolore magna aliqua.', (34, 138, 500, 60),
                                  parent=v, name='#29 UITextView')
        # DIVERGENCE: #103 and #84 carry an image (menu_try_again_single, menu_challenge_selection_single)
        # and nothing else - no title, no accessibility label in the nib or the code, and this screen has no
        # Accessible_ nib - so VoiceOver would read them by their image file name.  The port names them for
        # what they do, after their actions (tryAgainButtonPressed:, missionSelectButtonPressed:).
        Button('Try again', (209, 215, 150, 60), parent=v, font_button=False,
               actions=[self.try_again_button_pressed], name='#103')
        Button('Challenge selection', (144, 266, 280, 60), parent=v,
               font_button=False, actions=[self.mission_select_button_pressed], name='#84')
        # PORT ADDITION: this screen shows no statistics in the original - only the tip and these two
        # buttons - so a copy here would hand the player numbers they were never told.  The figures are
        # read out as well, one row each and first, exactly as Copy results pastes them (user request, as
        # on the other two results screens): the challenge, "Result: Failed", and the same three figures
        # the completed screen shows, so that a failed attempt and a won one can be compared.  The tip
        # follows them.
        self.results_view = View('', (34, 40, 500, 90), accessible=False, parent=v, ordered=True,
                                 name='Results (port)')
        # PORT ADDITION: read straight after the results and the tip, before the two buttons (user request);
        # its centre is a row above Try again's, so the reading order cannot merge them
        copy = Button(results.COPY_LABEL, (144, 205, 280, 30), parent=v, font_button=False,
                      actions=[self.copy_results_button_pressed], name='Copy results (port)')
        copy.hint = results.COPY_HINT
        self.first_accessible_element = self.tip_text_view   # until show_statistics has made the rows
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x100071718
        super().view_did_load()
        game_over_with_stats_view_did_load(self)
        challenge_view_did_load(self)
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)
        sb.set_currencies_visibility(False)
        sb.set_diamonds_visibility(False)
        sb.back_button.set_title('Main Menu')             # the button keeps its "Back" accessibility label
        Tracker.shared().challenge_completed(0)
        Tracker.shared().accuracy_objective_reached(0)
        Tracker.shared().time_objective_reached(0)
        tip = self.challenge_dict.get('tip')
        self.tip_text_view.label = self.tip_text_view.text = tip if tip is not None else ''
        sb.set_currencies_visibility(False)
        sb.set_armory_button_visibility(True)
        self.show_statistics()                            # PORT ADDITION
        self.game_over_playlist = S3DEngine.engine().play_list_with_name('gameover_%i' % (crand.c_mod(crand.rand(), 3) + 1))
        if self.game_over_playlist is not None:
            self.game_over_playlist.activate(self._game_over_playlist_activated)

    def _game_over_playlist_activated(self, _pl=None) -> None:   # viewDidLoad_block_invoke 0x100071c4c
        sound = self.game_over_playlist.any_sound() if self.game_over_playlist is not None else None
        if sound is not None:
            sound.play()

    def _deactivate_playlist(self) -> None:
        if self.game_over_playlist is not None:
            self.game_over_playlist.deactivate()

    def result_rows(self) -> list:                         # PORT ADDITION
        """(text, value) for each line: the challenge, how it ended, and the three figures the completed
        screen shows, for a challenge that was not completed."""
        from ..game.ingame_stats import InGameStats
        stats = InGameStats.singleton()
        rows = [(text, detail) for _header, text, detail in _challenge_rows(self.challenge_dict, 'Failed')]
        return rows + [('Kills', '%i' % stats.number_of_enemy_kills),
                       ('Accuracy', '%.2f %%' % f32(f32(stats.current_accuracy()) * f32(100.0))),
                       ('Survival time', time_string_from_seconds(int(stats.challenge_time_elapsed)))]

    def show_statistics(self) -> None:                    # PORT ADDITION
        self.results_view.children.clear()
        for n, (text, detail) in enumerate(self.result_rows()):
            row = View(results.line(text, detail), self.results_view.frame, parent=self.results_view,
                       name='result %i (port)' % n)
            results.mark_cell(row, text, detail)
        if self.results_view.children:                    # the screen opens on its results, as the others do
            self.first_accessible_element = self.results_view.children[0]

    def copy_results_button_pressed(self) -> None:        # PORT ADDITION: the rows, as they read
        results.copy_results(self, _statistics_heading(self.challenge_dict),
                             rows=results.rows_from_table(self.results_view))

    def mission_select_button_pressed(self) -> None:      # 0x100071e1c
        # PORT ADDITION: this one really is silent in the original - unlike the completed screen's, which
        # calls playButtonSound - so the two screens answered the same key differently.  Try again above it
        # plays start_level_button from its own playButtonSound 0x1000720c4.
        _play_buttons_sound('click_button')
        # PORT ADDITION: the list it was chosen from, which for the port's own is Extra
        App.delegate().go_to_challenge_list_for(self.challenge_dict.get('challenge_id'))
        self._deactivate_playlist()

    def try_again_button_pressed(self) -> None:           # 0x100071ee8
        _play_buttons_sound('start_level_button')         # playButtonSound 0x1000720c4
        App.delegate().go_to_challenge_with_dict(self.challenge_dict)
        self._deactivate_playlist()

    def back_button_pressed(self) -> None:                # 0x100072004
        App.delegate().go_to_main_menu()
        self._deactivate_playlist()


# ================================================================================ challenge completed
@register('Accessible_ADChallengeCompletedViewController')
class AccessibleChallengeCompletedScreen(AccessibleGameOverEndlessScreen):
    """Accessible_ADChallengeCompletedViewController : Accessible_ADGameOverEndlessViewController (nib
    Accessible_ADChallengeCompletedViewController #41).  Inherited: viewWillAppear: (reloadData), dealloc
    (deactivates "revive"), backButtonPressed (main menu) and cellForRewardsAtIndex:."""
    page_title = 'Challenge completed'

    def __init__(self, host, dictionary=None):            # initWithDictionary: 0x1000670f0
        super().__init__(host)
        self.challenge_dict = dictionary or {}
        self.mission_star_status = None
        self.accuracy_star_status = None
        self.time_star_status = None
        self.check_completion()

    def check_completion(self) -> None:                   # 0x100068074
        from ..game.ingame_stats import InGameStats
        from ..game.inventory import Inventory
        d = self.challenge_dict
        cid = d.get('challenge_id')
        cd = ChallengeData.shared()
        inv = Inventory.shared()
        stats = InGameStats.singleton()
        if cd.has_completed_challenge_with_name(cid):
            self.mission_star_status = 'already unlocked'
        else:
            reward = ns_int_value((d.get('mission_star') or {}).get('reward'))
            self.mission_star_status = 'Reward : %i coins' % reward
            inv.set_coins(inv.coins + reward)
        Tracker.shared().challenge_completed(1)
        acc = d.get('accuracy_star') or {}
        accuracy_unlocked = False
        # fcmp objective, accuracy * 100 (float); b.ls: NaN fails
        if not f32(ns_float_value(acc.get('objective'))) <= f32(f32(stats.current_accuracy()) * f32(100.0)):
            self.accuracy_star_status = 'objective failed. %i%% accuracy was required' % ns_int_value(acc.get('objective'))
            # DIVERGENCE: the pass path and the fail path converge at loc_100068794 and the report below is
            # sent from there, so the tracker was told the accuracy objective had been reached even when it
            # had just been failed.  The time star, three lines down, reports its failure properly; accuracy
            # now does the same.
            Tracker.shared().accuracy_objective_reached(0)
        elif cd.has_accuracy_star_for_challenge_with_name(cid):
            self.accuracy_star_status = 'already unlocked'
        else:
            reward = ns_int_value(acc.get('reward'))
            self.accuracy_star_status = 'You beat the %i%% goal -- Reward : %i coins' % (
                ns_int_value(acc.get('objective')), reward)
            inv.set_coins(inv.coins + reward)
            accuracy_unlocked = True
        if self.accuracy_star_status and 'objective failed' not in self.accuracy_star_status:
            Tracker.shared().accuracy_objective_reached(1)
        tl = d.get('time_limit_star') or {}
        time_unlocked = False
        # fcmp double(objective), challengeTimeElapsed (double); b.ge: NaN fails
        if not float(f32(ns_float_value(tl.get('objective')))) >= float(stats.challenge_time_elapsed):
            self.time_star_status = 'objective failed. Time limit was %i seconds' % ns_int_value(tl.get('objective'))
            Tracker.shared().time_objective_reached(0)
        else:
            if cd.has_time_limit_star_for_challenge_with_name(cid):
                self.time_star_status = 'already unlocked'
            else:
                reward = ns_int_value(tl.get('reward'))
                self.time_star_status = 'You beat the %i seconds time limit -- Reward : %i coins' % (
                    ns_int_value(tl.get('objective')), reward)
                inv.set_coins(inv.coins + reward)
                time_unlocked = True
            Tracker.shared().time_objective_reached(1)
        cd.player_did_complete_challenge(cid, accuracy_unlocked, time_unlocked)
        # REMOVED (user request): [self reportScoreToGameCenter] (0x1000693f0); Windows has no Game Center

    def load_view(self) -> None:                          # 0x100069224
        v = self.view = View('', (0, 0, 480, 320), accessible=False, name='#41')
        self.table_view = View('', (0, 25, 480, 259), accessible=False, parent=v, ordered=True, name='#4')
        # DIVERGENCE: the nib puts these three in a row - Challenge selection at x 5, Next challenge at 189,
        # Retry at 364 - so they are read in that order.  Retry is read first now (user request), the way
        # Try again comes before Challenge selection on the failed screen; they keep their widths and their
        # row, since nothing here is looked at.
        Button('Retry', (5, 285, 98, 30), parent=v, font_button=False, actions=[self.retry_button_pressed],
               name='#3')
        Button('Challenge selection', (110, 285, 154, 30), parent=v, font_button=False,
               actions=[self.mission_select_button_pressed], name='#70')
        self.next_challenge_button = Button('Next challenge', (270, 285, 154, 30), parent=v, font_button=False,
                                            actions=[self.next_mission_button_pressed], name='#32')
        # PORT ADDITION: between the results and the three nib buttons, so it is read straight after what it
        # copies (user request).  Its centre is a row above theirs, so the reading order cannot merge them.
        copy = Button(results.COPY_LABEL, (164, 250, 154, 30), parent=v, font_button=False,
                      actions=[self.copy_results_button_pressed], name='Copy results (port)')
        copy.hint = results.COPY_HINT
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x1000673f4 (no [super viewDidLoad])
        from ..game.ingame_stats import InGameStats
        from ..game.inventory import Inventory
        self.load_status_bar()
        self.status_bar_view_controller.set_armory_button_visibility(True)
        inv = Inventory.shared()
        inv.set_coins(inv.coins + InGameStats.singleton().total_coins)
        inv.set_diamonds(inv.diamonds + InGameStats.singleton().diamond_loot)
        if ChallengeData.shared().has_challenge_after(self.challenge_dict.get('challenge_id'),
                                                      GameParameters.shared().last_challenge_world):
            return
        from ..game.additions import arena_after, chapter_of
        cid = self.challenge_dict.get('challenge_id')
        if chapter_of(cid) is not None:
            # PORT ADDITION (user request, 2026-09-29): a chapter is to Extra what a world is to the
            # challenges.  Next challenge opens the arena after this one in its chapter
            # (App.go_to_challenge_after), and the last of a chapter says "next arena" and goes to its
            # campaign's chapters, as the last of a world says it and goes to the world list.  It used to say
            # "back to Chapter N" and go back to the chapter it came from, and then "Chapter selection"; the
            # original's own words are the same on both sides (user request, 2026-10-01).
            if arena_after(cid) is None:
                self.next_challenge_button.label = 'next arena'
                self.next_challenge_button.set_title('next arena')
            return
        self.next_challenge_button.label = 'next arena'
        self.next_challenge_button.set_title('next arena')

    def reload_data(self) -> None:
        """DIVERGENCE (user request): one row per line, read exactly as Copy results pastes it, as on the
        Endless game over screen.  The original (numberOfSectionsInTableView: 3, rows 3 / 2 / 3 at
        tconst_100181c50) has the headers "Stars", "Rewards" and "Statistics"
        (tableView:viewForHeaderInSection: 0x1000672f8) and reads its rewards as the inherited sentences
        (cellForRewardsAtIndex: 0x10009aa80).  Here there are no header rows, the rewards are numbers, and
        the challenge's name and "Result: Completed" come first, as they do in the paste."""
        from ..game.ingame_stats import InGameStats
        stats = InGameStats.singleton()
        t = _TableLoader(self.table_view)
        first = None
        for text, detail in self.result_rows(stats):      # tableView:cellForRowAtIndexPath: 0x1000677a8
            cell = t.cell(text, detail)
            cell.label = results.line(text, detail)
            first = first or cell
        # the original posts UIAccessibilityScreenChangedNotification with the header of section 0; with no
        # headers, the first row takes its place
        self.post_screen_changed(first)

    def result_rows(self, stats) -> list:                  # PORT ADDITION
        """(text, value) for each line: the challenge and how it ended, the stars, the rewards, the
        statistics (cellForStatsAtIndex: 0x100067c0c)."""
        rows = [(text, detail) for _header, text, detail in _challenge_rows(self.challenge_dict, 'Completed')]
        rows += [('Challenge completed star', self.mission_star_status),
                 ('Accuracy star', self.accuracy_star_status),
                 ('Time limit star', self.time_star_status)]
        rows += [self.copy_for_rewards_at_index(row, stats) for row in range(2)]
        rows += [('Kills', '%i' % stats.number_of_enemy_kills),
                 ('Accuracy', '%.2f %%' % f32(f32(stats.current_accuracy()) * f32(100.0))),
                 ('Survival time', time_string_from_seconds(int(stats.challenge_time_elapsed)))]
        return rows

    def mission_select_button_pressed(self) -> None:      # 0x100068f64
        _play_buttons_sound('click_button')               # playButtonSound 0x100049300, called at 0x048884
        # PORT ADDITION: the list it was chosen from, which for the port's own is Extra
        App.delegate().go_to_challenge_list_for(self.challenge_dict.get('challenge_id'))

    def back_button_pressed(self) -> None:                # 0x100048728
        # DIVERGENCE (user request): `-[ADChallengeCompletedViewController backButtonPressed]` 0x100048728
        # stops the screen's animations and calls `goToMainMenu` at 0x100048804, so Escape from a finished
        # challenge left the challenge list altogether and the next one was three screens away again - Play,
        # the world, the list.  Escape now does what this screen's own Select challenge button does
        # (`missionSelectButtonPressed` 0x100068f64) and returns to the list the challenge was started from;
        # the main menu is still one Escape further, through the world selector.  The button itself is
        # untouched, and the failed screen keeps the original's route to the main menu.  The navigation is
        # repeated rather than calling missionSelectButtonPressed, which plays the click: the Back button
        # plays its own already, and one press would click twice.
        App.delegate().go_to_challenge_list_for(self.challenge_dict.get('challenge_id'))

    def next_mission_button_pressed(self) -> None:        # 0x100069008
        _play_buttons_sound('click_button')               # playButtonSound 0x100049300, called at 0x0489e0
        App.delegate().go_to_challenge_after(self.challenge_dict.get('challenge_id'))

    def retry_button_pressed(self) -> None:               # 0x100069134
        _play_buttons_sound('click_button')               # playButtonSound 0x100049300, called at 0x048bc0
        App.delegate().go_to_challenge_with_dict(self.challenge_dict)

    def copy_results_button_pressed(self) -> None:        # PORT ADDITION: the table, as it reads
        results.copy_results(self, _statistics_heading(self.challenge_dict))

    # REMOVED (user request): the magic tap 0x10006974c pressed Next mission.
