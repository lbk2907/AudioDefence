"""ADTarotViewController and ADTarotCardViewController: Dr Bastard's tarot, shown before every Endless game."""
from __future__ import annotations

import logging

from ..app import App
from ..game import data
from ..platform import crand
from ..platform.defaults import UserDefaults
from ..platform.runloop import RunLoop
from ..platform.speech import Speech
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .accessibility import BUTTON, STATIC_TEXT, Button, View
from .host import register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.tarot')

#: PORT DIVERGENCE (user request): four cards are dealt, not two - `cardsToLoad` is set to 2 in
#: -viewDidLoad 0x10003461c.  Tarot.plist ships a third level of twelve cards, six good and six bad, that
#: the original never deals, and the port adds a fourth of its own (`additions.NEW_CARDS`) where every
#: card gives and takes at once.  Most of the way to three was already built: the layout maths divides the
#: container by `cardsToLoad`, -viewDidLoad prices a level-3 change at 1 diamond, and
#: -resetCardsModifiersIfNeeded 0x1000d42a8 already cleared three keys.  The fourth needed the reset
#: widened (it cleared 1 to 3, so a fourth card would have been dealt once and kept for good) and the
#: spacing rewritten, which goes negative at four.
CARDS_TO_LOAD = 4

#: PORT DIVERGENCE (user request): the deal takes as long as the original's, whatever is in it.  Both
#: numbers are the original's own: -viewDidLoad 0x10003461c waits 2.3 s before it lets you play, and its
#: two cards flip a second apart, the last of them 2 s in.  Those are the same number twice - a card
#: flipping on its own index - and at three cards the port had taken the second reading, so the wait grew
#: with the deck.  The last card lands at 2 s however many there are, and the deal ends 0.3 s later, so
#: two cards still flip at 1 s and 2 s exactly as they always did and nobody waits longer for more.
DEAL_LAST_FLIP = 2.0
DEAL_SECONDS = 2.3

#: PORT DIVERGENCE (user request): the third card is dealt and kept, and so is any card after it.  The
#: first two can still be bought out of, at 3 diamonds and 2; the level-3 deck is a near-even split of
#: good cards and bad, so the hand always holds one card the player did not choose and cannot pay to be
#: rid of.
LOCKED_CARD_LEVEL = 3

#: PORT ADDITION (user request): how often a hand is dealt the fourth card at all, as a chance per hand.
#: Most hands hold three; now and then a fourth turns up from the level-4 deck, where every card gives and
#: takes at once.  That is what those cards are for - a surprise worth reading, rather than a fixture - and
#: it is why they can be as strong and as costly as they are.
#:
#: A quarter is the number.  Rarer reads well on paper and badly in play: the deck has twelve cards, and at
#: one hand in ten a player would meet a card for the first time after an evening of runs and have no idea
#: what it was going to do to them.
FOURTH_CARD_CHANCE = 25

#: PORT ADDITION (user request): how long between the flips of a shuffle.  A shuffle deals every locked
#: card again, and each one gets a flip of its own, so two cards are two sounds - what a player hears is
#: how many cards moved.  Both new cards are read out after the last of them, not as each lands, because a
#: card read out while another is still arriving is a card read over.
SHUFFLE_FLIP_GAP = 0.5

#: PORT ADDITION (user request): what it costs to shuffle the cards that cannot be changed one by one.
#: The locked cards are the point of the hand - something nobody chose - so this is not a way to shop for
#: a card: it deals every locked slot again at random, and what comes back may be worse.  It is the way
#: out of a hand that has gone wrong, and it is priced to be thought about rather than leaned on.
#:
#: Both currencies, because they are earned differently: diamonds are scarce (about twenty a run) and
#: coins are not (twelve thousand in a long one), so the diamonds are the real price and the coins are
#: what makes it sting early on, before a player has a bank.  Three diamonds is what changing the first
#: card costs, which is the dearest single change the original sells.
SHUFFLE_DIAMONDS = 3
SHUFFLE_COINS = 2500

#: PORT ADDITION: how many cards this hand holds, kept with the hand itself.  The roll has to be made once
#: and then remembered: the screen is left and come back to - the armory opens over it - and a hand that
#: rolled its fourth card again each time would gain and lose one under the player.  The original has no
#: key for this because it always dealt two.  `resetCardsModifiersIfNeeded` clears it with the cards.
HAND_SIZE_KEY = 'tarotCardsDealt'

#: PORT ADDITION (testing, user request): `--free-cards` lets the cards from `LOCKED_CARD_LEVEL` on be
#: changed after all, and every card in the hand - locked or not, whatever the slot - costs nothing to
#: change, so a card can be looked for by pressing Enter instead of by playing hands until it turns up.
#: Off unless the flag is passed, because a locked card a player can change is not a locked card, and a
#: hand that can be rearranged for nothing is not a hand.
UNLOCK_CARDS_FOR_TESTING = False


def _cards_for_level(level: int) -> list:
    """[[NSDictionary dictionaryWithContentsOfURL:Tarot.plist] objectForKey:"level_%i"]."""
    return list((data.plist_ro('Tarot') or {}).get('level_%i' % level) or [])


def cards_in_play() -> list:
    """PORT ADDITION: [(1, title), ...] - the cards this Endless run was dealt, for the game-over screen's
    first row and so for Copy results.

    They are kept as tarotCard1, tarotCard2 and tarotCard3, each by its selector, and a selector is looked up in its
    own level of Tarot.plist: the same selector names a different card on another level.  The game-over
    screen clears them as it opens after a long enough run, so it has to ask before that."""
    out = []
    defaults = UserDefaults.standard()
    for level in range(1, CARDS_TO_LOAD + 1):             # one card from each level of the deck
        selector = defaults.object('tarotCard%i' % level)
        if selector is None:
            continue
        title = next((card.get('title') for card in _cards_for_level(level)
                      if card.get('selector') == selector), None)
        if title:
            out.append((level, title))
    return out


def _flip_sound_play() -> None:
    pl = S3DEngine.engine().play_list_with_name('tarot')
    sound = pl.any_sound_containing('flip') if pl is not None else None
    if sound is not None:
        sound.play()


class TarotCardViewController:
    """ADTarotCardViewController (an ADNoBarViewController whose view the tarot screen adds as a subview).

    Card views (nib ADTarotCardViewController): view #18 (140x190), cardFront #62 (image, cardTitle #79,
    cardDescription #22, changeCardButton #42), cardBack #75 (image).  Frames of the subviews are relative to
    the card view; ``place`` turns them into screen frames once the tarot screen has positioned the card.
    """

    def __init__(self, host, card_level: int, modifier=None):   # initWithCardLevel:modifier: 0x1000a54c4
        self.host = host
        self.card_level = card_level
        self.card_dictionary = None
        cards = _cards_for_level(card_level)
        for entry in cards:
            if modifier is not None and entry.get('selector') == modifier:
                self.card_dictionary = entry
        if self.card_dictionary is None and cards:
            self.card_dictionary = cards[crand.rand() % len(cards)]
        self.tarot_view_controller = None
        # PORT DIVERGENCE: see LOCKED_CARD_LEVEL, and UNLOCK_CARDS_FOR_TESTING for the way out of it
        self.locked = card_level >= LOCKED_CARD_LEVEL and not UNLOCK_CARDS_FOR_TESTING
        self.cost = 0
        self.current_title = None
        self.flipped = False
        self.accessible_card: View | None = None
        self._view: View | None = None
        self._relative: dict = {}

    # --- view ------------------------------------------------------------------------------------
    @property
    def view(self) -> View:
        if self._view is None:
            self.load_view()
            self.view_did_load()
        return self._view

    def load_view(self) -> None:                          # UIViewController loadView (nib ADTarotCardViewController)
        self._view = View('', (0, 0, 140, 190), accessible=False, name='card #18')
        self.card_front = View('', (0, 0, 130, 190), accessible=False, name='cardFront #62')
        self.card_title = View('Label', (15, 39, 100, 25), parent=self.card_front, name='#79')
        self.card_description = View('Label', (15, 64, 100, 77), parent=self.card_front, name='#22')
        self.change_card_button = None                    # PORT DIVERGENCE: a locked card has no button
        if not self.locked:
            self.change_card_button = Button('Button', (15, 141, 100, 25), parent=self.card_front,
                                             actions=[self.change_card_button_pressed], name='#42')
            self.change_card_button.enabled = False       # PORT DIVERGENCE: until the deal is over
        self.card_back = View('', (0, 0, 130, 190), accessible=False, name='cardBack #75')
        for v in (self.card_front, self.card_title, self.card_description, self.change_card_button,
                  self.card_back):
            if v is not None:
                self._relative[id(v)] = v.frame

    def set_center(self, cx: float, cy: float) -> None:   # [[card view] setCenter:] in the container's coordinates
        w, h = self._view.frame[2], self._view.frame[3]
        self._view.frame = (cx - w / 2.0, cy - h / 2.0, w, h)
        self.place()

    def place(self) -> None:
        ox, oy = self._view.frame[0], self._view.frame[1]
        for child in self._view.children:
            self._place_tree(child, ox, oy)

    def _place_tree(self, v: View, ox: float, oy: float) -> None:
        rel = self._relative.get(id(v))
        if rel is not None:
            v.frame = (ox + rel[0], oy + rel[1], rel[2], rel[3])
        for c in v.children:
            self._place_tree(c, ox, oy)

    def _set_card_face(self, face: View) -> None:          # transitionFromView:toView: swaps the subview
        for old in (self.card_front, self.card_back):
            if old in self._view.children:
                self._view.children.remove(old)
                old.parent = None
        face.parent = self._view
        self._view.children.append(face)
        self.place()

    def view_did_load(self) -> None:                      # 0x1000a4bd4
        if self.card_level == 1:
            self.cost = 3
        if self.card_level == 2:
            self.cost = 2
        if self.card_level >= 3:                          # PORT DIVERGENCE: the original knows 1, 2, 3
            self.cost = 1
        if UNLOCK_CARDS_FOR_TESTING:
            self.cost = 0                                 # PORT ADDITION (testing): nothing to pay, on any card
        # changeCardButton setDiamonds:cost -> -setTitle:forState: labels it "<title> diamonds"
        if self.change_card_button is not None:
            title = 'Change for %d' % self.cost
            self.change_card_button.set_title(title)
            self.change_card_button.label = '%s diamonds' % title
        if self.host.screen_reader_running():
            self._view.children.clear()                   # [[view subviews] makeObjectsPerformSelector:removeFromSuperview]
            # [[ADButtonWithFont alloc] initWithFrame:view.frame]: no -awakeFromNib, so no click sound
            # PORT DIVERGENCE: a locked card is read as text, because it is not a button: there is nothing
            # to press on it, and "button" at the end of it would be an offer the card does not make.
            self.accessible_card = View('', self._view.frame, traits=STATIC_TEXT if self.locked else BUTTON,
                                        parent=self._view, name='accessibleCard')
            # PORT DIVERGENCE (user request): a card is not there until its own flip has been heard.  The
            # deal is a sound per card, and the cursor reaches exactly the cards that sound has brought
            # in - hear the second flip and there are two cards to read, whatever the hand will hold.
            # `reading_order` skips an element that is not `accessible`, so an undealt card is not
            # something to arrow past; it is not there at all.  `reveal` is what the flip calls.
            self.accessible_card.accessible = False
            # PORT DIVERGENCE (user request): a card cannot be changed while the cards are being dealt.
            # The original dims Back and Armory for those seconds (`deactivateButtons` 0x10001cee4) and
            # the port dims Play with them, but every card stayed live, so a hand could be paid for and
            # rerolled mid-deal.  A card is built during the deal and nowhere else, so it starts dimmed
            # and `_cards_dealt` lets it go.  `View.activate` refuses a dimmed element, and a screen
            # reader says "dimmed" on the way past, which is what the other three buttons do.
            self.accessible_card.enabled = False
            self.accessible_card.label_key_words = True   # PORT ADDITION: "press Enter to change", or a button
            self._relative[id(self.accessible_card)] = self._view.frame
            self.refresh_card()
        else:
            self.refresh_card()
            self._set_card_face(self.card_back)

    def refresh_card(self) -> None:                       # 0x1000a58e0
        if self.host.screen_reader_running():
            card = self.accessible_card
            self.refresh_accessible_text()
            if not self.locked:
                card.add_target(self.change_card_button_pressed)
            # makeAccessible / setupAsAccessibleTarotCardInfo: colours and fonts
        else:
            self.card_title.label = self.card_dictionary.get('title')
            self.card_description.label = self.card_dictionary.get('description')
            # backgroundImage: cards_front_bad / cards_front_good
        self.current_title = self.card_dictionary.get('title')

    def flip_card(self, animated_change: bool) -> None:   # flipCard: 0x1000a5e50
        if self.host.screen_reader_running():
            # DIVERGENCE: the original leaves here (UIAccessibilityIsVoiceOverRunning at 0x1000a5e78), and
            # since the flip sound is played at the end of the animation, a VoiceOver player hears nothing
            # while the cards are dealt - the deal is two seconds of silence.  The port keeps the animation
            # skipped and plays the sound, so the deal is something you can hear.
            _flip_sound_play()
            return
        to_view = self.card_back if self.flipped else self.card_front
        self._set_card_face(to_view)

        def completion():                                 # flipCard:_block_invoke 0x1000a60d0
            self.flipped = not self.flipped
            if animated_change:
                self.change_card()
                self.flip_card(False)
        RunLoop.main().call_later(0.5, completion)
        _flip_sound_play()

    def refresh_accessible_text(self) -> None:
        """PORT ADDITION: what refreshCard says, without re-adding the card's action.

        The action is added once, when the card is dealt.  Anything that only needs the words again -
        coming back to this screen with a different number of diamonds - calls this instead, because
        adding the target twice would change the card twice, and charge twice, on one press."""
        from ..game.inventory import Inventory
        card = self.accessible_card
        card.set_title(self.accessible_description())
        card.label = self.accessible_description()
        # PORT DIVERGENCE: the count is what you would be spending, so a card you cannot spend on is silent
        # about it.  The status bar still carries the number for anyone who wants it.
        card.hint = None if (self.locked or not self.cost) else \
            'You have %i diamonds' % Inventory.shared().diamonds

    def accessible_description(self, with_action: bool = True) -> str:   # 0x1000a61a0
        card = 'Tarot card number %i : %s \n\n %s' % (
            self.card_level, self.card_dictionary.get('title'), self.card_dictionary.get('description'))
        # PORT DIVERGENCE (user request): a card ends with what pressing Enter would do, and ends with
        # nothing when the answer is nothing.  A locked card is silent about being locked: there is no
        # button on it and nothing to press, so a sentence saying so was a sentence explaining an absence.
        # It read "(this card cannot be changed)" at first, and that came out again.
        #
        # `with_action` is False for a card that has this second been changed or shuffled: the price of
        # changing it again is not what somebody who has just paid wants to hear.
        if not with_action or self.locked:
            return card
        if not self.cost:                                 # PORT ADDITION (testing): free, so unpriced
            return card + ' \n\n(press Enter to change)'
        # PORT INPUT: the original says "(double tap to change for %i diamonds)"; the port names its key
        return card + ' \n\n(press Enter to change for %i diamonds)' % self.cost

    def change_card_button_pressed(self) -> None:         # changeCardButtonPressed: 0x1000a62b8
        from ..game.inventory import Inventory
        if self.locked:                                   # PORT DIVERGENCE: nothing reaches this on card 3
            return
        screen = self.tarot_view_controller               # PORT DIVERGENCE: not while they are dealt
        if screen is not None and screen.dealing:
            return
        if not Inventory.shared().diamonds >= self.cost:
            self.host.show_no_diamonds_alert()
            return
        if self.host.screen_reader_running():
            _flip_sound_play()
            self.change_card()
        else:
            self.flip_card(True)
        status_bar = App.delegate().status_bar
        if status_bar is not None:
            status_bar.animate_diamonds(-self.cost)
        Inventory.shared().set_diamonds(Inventory.shared().diamonds - self.cost)
        # DIVERGENCE: changeCardButtonPressed: 0x1000a62b8 runs -changeCard (0x1000a63fc, which ends in
        # -refreshCard) BEFORE -setDiamonds: at 0x1000a6518, so the card's "You have %i diamonds" hint is
        # built from the count you had before paying; the other card is never refreshed at all and keeps
        # the number it was dealt with.  Both cards are refreshed here, after the money has moved.
        if self.host.screen_reader_running():
            screen = self.tarot_view_controller
            for card in (screen.tarot_cards if screen is not None else [self]):
                card.refresh_card()
            # PORT ADDITION: the card's label is rewritten under a cursor that is already on it, and a
            # screen reader has no reason to read a label it is not being moved onto, so the player was
            # left holding a card whose words they could only hear by arrowing off it and back.  Saying
            # it is what the cursor would say if it landed here now - View.spoken(), the same text the
            # arrow keys produce - so the new card is heard exactly as a card is normally heard.
            self.announce_card()

    def reveal(self) -> None:
        """PORT ADDITION: the cursor can reach this card, its flip having been heard.

        It is still dimmed until the whole deal is over - a card that has arrived can be read, and cannot
        be paid to change, which is the state the other three buttons are in for those seconds.
        """
        if self.accessible_card is not None:
            self.accessible_card.accessible = True

    def announce_card(self) -> None:                      # PORT ADDITION
        """Read out a card that has just changed, under a cursor that may already be on it.

        The title and the description, and nothing else (user request).  What the cursor would say also
        carries the price of changing the card again, the count of diamonds in the purse and the word
        "button" - worth hearing on arriving at a card, not worth hearing to somebody who has this second
        paid to change it and wants to know what they got.  A shuffle reads two of these in a row, which
        is twice the reason to say only the card.
        """
        if self.accessible_card is None:
            return
        screen = self.tarot_view_controller
        speak = screen.speak if screen is not None else Speech.shared().speak
        speak(self.accessible_description(with_action=False))

    def change_card(self) -> None:                        # 0x1000a65a4
        cards = _cards_for_level(self.card_level)
        self.card_dictionary = cards[crand.rand() % len(cards)]
        while self.card_dictionary.get('title') == self.current_title:
            self.card_dictionary = cards[crand.rand() % len(cards)]
        self.refresh_card()
        # DIVERGENCE (user request): the original never stores the card you paid for.  Only
        # loadCardWithNumber: 0x100035390 writes tarotCardN, and only when the key is missing, so leaving
        # the screen and coming back deals the stored card again and the diamonds are gone.  The new card
        # is saved here under the same key, the way the deal saves the first one.  Nothing else changes:
        # applyAllModifiers 0x100035a5c still reads the live card, and resetCardsModifiersIfNeeded
        # 0x1000d42a8 still clears all three keys after an endless game lasting over 60 seconds.
        defaults = UserDefaults.standard()
        defaults.set_object(self.modifier_name(), 'tarotCard%i' % self.card_level)
        defaults.synchronize()

    def modifier_name(self):                              # 0x1000a68c8
        return self.card_dictionary.get('selector')

    def is_good(self) -> bool:                            # 0x1000a68ec
        return self.card_dictionary.get('goodbad') == 'good'


@register('ADTarotViewController')
class TarotScreen(ViewControllerScreen):
    """ADTarotViewController."""
    #: the original's own title here is "Dr Bastard's Tarot"; this screen is how Endless starts,
    #: and the button that reaches it says Endless, so it is named for where you are.
    page_title = 'Endless'

    def __init__(self, host):
        super().__init__(host)
        self.shuffle_button = None
        self.shuffling = False                            # PORT ADDITION: a shuffle is still landing
        self.backbuttonpressed = False
        self.dealing = False                              # PORT ADDITION: the cards are being dealt
        self.tarot_playlist = None
        self.tarot_cards: list[TarotCardViewController] = []
        self.cards_to_load = 0

    def load_view(self) -> None:                          # 0x1000351c4 (view #121)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#121')
        self.info_text = View("Dr. Bastard's tarot cards will disrupt your game", (96, 55, 392, 39), parent=v,
                              name='#20')
        self.card_container = View('', (60, 95, 460, 190), accessible=False, parent=v, name='#115')
        # PORT ADDITION (user request): a shuffle for the cards that cannot be changed one at a time.  The
        # frame is what puts it after the cards and before Play: `reading_order` sorts by the vertical
        # centre of a frame, and 255 sits between the cards' 180 and Play's 302.
        self.shuffle_button = Button('Shuffle the locked cards', (214, 240, 140, 30), parent=v,
                                     actions=[self.shuffle_button_pressed], name='shuffleButton')
        self.play_button = Button('Play', (234, 272, 100, 60), parent=v, actions=[self.play_button_pressed],
                                  name='#71')
        self.play_button.alpha = 0.0                      # nib alpha
        self.mission_button = None                        # no missionButton outlet in the nib
        self.roots = [v]

    def view_will_appear(self) -> None:
        # DIVERGENCE: -refreshCard 0x1000a58e0 runs when a card is dealt and when one is changed, and
        # nothing runs it when this screen comes back.  A card's hint carries the count of diamonds you
        # had when it was dealt, so after spending in the armory - which is presented over this screen -
        # the card still said "You have 500 diamonds" until something else happened to rebuild it.  The
        # words are refreshed on the way in; the card, its cost and its action are untouched.
        super().view_will_appear()
        for card in self.tarot_cards:
            if getattr(card, 'accessible_card', None) is not None and self.host.screen_reader_running():
                card.refresh_accessible_text()
        if not self.dealing:                              # PORT ADDITION: the shuffle's price and purse
            self.refresh_shuffle_button()

    def view_did_load(self) -> None:                      # 0x10003461c
        super().view_did_load()
        # [self loadMissionOverlay]: ADMissionTopbarViewController's view is added with alpha 0 behind the
        # screen and only its missionButton (not connected) or showMissionsOverlay: (not connected) open it,
        # so VoiceOver never reaches it.  Not ported.
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)
        sb.armory_button.alpha = 0.0
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        sb.armory_loadout_enabled = False
        sb.delegate = self
        self.tarot_playlist = S3DEngine.engine().play_list_with_name('tarot')
        if self.tarot_playlist is not None:
            self.tarot_playlist.activate()
        if UserDefaults.standard().object('tarotCard1') is not None:
            self.info_text.text = data.localized('TAROT_NO_RELOAD')
        else:
            self.info_text.text = data.localized('TAROT_INFO')
        self.info_text.label = data.spoken_text(self.info_text.text)
        self.tarot_cards = []
        if self.host.screen_reader_running():
            # the original already lets a VoiceOver player press Play before the deal finishes.
            # DIVERGENCE: the Armory and Back buttons are dimmed until then (deactivate_buttons), and Play
            # was the one button on the screen that was not; it is dimmed with them now, and comes back
            # when the cards are dealt, as it does for a sighted player.
            self.play_button.alpha = 1.0
            self.play_button.enabled = False
            self.play_button.user_interaction_enabled = False
        else:
            self.play_button.user_interaction_enabled = False
        sb.deactivate_buttons()
        if self.shuffle_button is not None:               # PORT ADDITION: dimmed while the cards are dealt
            self.shuffle_button.enabled = False
        self.dealing = True
        self.cards_to_load = self.cards_this_hand()        # PORT DIVERGENCE: always 2 in the original
        n = 0
        while True:
            self.load_card_with_number(n + 1)
            n += 1
            if not n < self.cards_to_load:
                break
        RunLoop.main().call_later(DEAL_SECONDS, self._cards_dealt)

    def _cards_dealt(self) -> None:                       # viewDidLoad_block_invoke 0x100034e84
        self.dealing = False
        if self.backbuttonpressed:
            return
        for card in self.tarot_cards:                     # PORT DIVERGENCE: the cards come alive with Play
            if card.accessible_card is not None:
                card.reveal()                             # every card is in by now; this is the backstop
                card.accessible_card.enabled = True
            if card.change_card_button is not None:
                card.change_card_button.enabled = True
        if self.shuffle_button is not None:               # PORT ADDITION: and so does the shuffle
            self.shuffle_button.enabled = True
            self.refresh_shuffle_button()
        sb = self.status_bar_view_controller
        self.play_button.alpha = 1.0                      # 0.5 s animation
        if sb is not None:
            sb.armory_button.alpha = 1.0                  # 1 s animation (missionButton is nil)
            sb.activate_buttons()
        self.play_button.enabled = True
        self.play_button.user_interaction_enabled = True
        if sb is not None:
            sb.armory_loadout_enabled = True
            sb.set_armory_button_visibility(True)

    def cards_this_hand(self) -> int:
        """PORT ADDITION: three cards, or four when this hand has rolled one (see FOURTH_CARD_CHANCE).

        Rolled once and kept, so leaving this screen and coming back deals the same hand back - which is
        what the stored cards do, and a hand that changed size on the way past would be worse than either.
        """
        kept = UserDefaults.standard().object(HAND_SIZE_KEY)
        if kept is not None:
            return max(1, min(CARDS_TO_LOAD, int(kept)))
        return self.roll_hand_size()

    def roll_hand_size(self) -> int:
        """PORT ADDITION: roll for the fourth card, and remember the answer."""
        rolled = CARDS_TO_LOAD if crand.c_mod(crand.rand(), 100) < FOURTH_CARD_CHANCE \
            else CARDS_TO_LOAD - 1
        defaults = UserDefaults.standard()
        defaults.set_integer(rolled, HAND_SIZE_KEY)
        defaults.synchronize()
        log.info('this hand holds %d cards', rolled)
        return rolled

    def place_cards(self) -> None:
        """Every card's place, from how many there are.

        0x100035390 places one card as it is made, with `cardsToLoad` for the count.  It is a pass over all
        of them here because a hand can change size after it is dealt - a shuffle rolls for the fourth card
        again - and the spacing is a function of the count, so one card arriving or leaving moves the rest.
        """
        container = self.card_container.frame
        n = max(1, len(self.tarot_cards))
        for card in self.tarot_cards:
            w = card.view.frame[2]
            t1 = (container[2] - w * float(n)) / float(n + 1)
            if t1 >= 0.0:
                cx = (t1 + w * 0.5) + float(card.card_level - 1) * (t1 + w)
            else:
                # PORT DIVERGENCE: the original's spacing is a gap it puts between and around the cards,
                # and at four 140-wide cards in a 460-wide container that gap is -20: the row would hang
                # off both ends.  The cards are spread across the container instead, first and last flush
                # with its edges, overlapping each other as much as they must.  Nothing draws them, so
                # what this protects is the reading order, which follows the frames.
                step = (container[2] - w) / float(max(1, n - 1))
                cx = w * 0.5 + float(card.card_level - 1) * step
            cy = container[3] * 0.5 + -10.0
            card.set_center(container[0] + cx, container[1] + cy)

    def drop_card_with_number(self, number: int) -> None:
        """PORT ADDITION: take a card out of the hand, as though it had never been dealt.

        The fourth slot is a chance, so a shuffle rolls for it again and it can come back empty (user
        request).  The card leaves the hand, its view leaves the container, its key leaves the defaults,
        and the rest are placed again for the smaller hand.
        """
        for card in list(self.tarot_cards):
            if card.card_level != number:
                continue
            if card.view in self.card_container.children:
                self.card_container.children.remove(card.view)
            card.view.parent = None
            self.tarot_cards.remove(card)
        defaults = UserDefaults.standard()
        defaults.set_object(None, 'tarotCard%i' % number)
        defaults.synchronize()
        self.place_cards()

    def load_card_with_number(self, number: int, dealing: bool = True) -> None:   # 0x100035390
        defaults = UserDefaults.standard()
        key = 'tarotCard%i' % number
        if defaults.object(key) is not None:
            card = TarotCardViewController(self.host, number, defaults.object(key))
        else:
            card = TarotCardViewController(self.host, number, None)
            defaults.set_object(card.modifier_name(), key)
            defaults.synchronize()
        card.tarot_view_controller = self
        self.tarot_cards.append(card)
        card_view = card.view                              # loads the card (its viewDidLoad runs here)
        card_view.parent = self.card_container
        self.card_container.children.append(card_view)
        self.place_cards()
        if not dealing:
            # PORT ADDITION: a card a shuffle has just brought in, with the deal long over.  It is here to
            # be read and used at once; the shuffle's own flip is what announces it.
            card.reveal()
            if card.accessible_card is not None:
                card.accessible_card.enabled = True
            if card.change_card_button is not None:
                card.change_card_button.enabled = True
            return
        # QUIRK: dispatch_after is given the card number as its dispatch_time_t, a time already past, so the
        # block runs on the next pass; it then flips the card after <number> seconds
        # PORT DIVERGENCE: the original flips card N after N seconds; the cards share the same 2 s here,
        # so the last of them lands where the original's last one did.  See DEAL_LAST_FLIP.
        after = DEAL_LAST_FLIP * float(number) / float(max(1, self.cards_to_load))
        RunLoop.main().call_soon(
            lambda: RunLoop.main().call_later(after, lambda: self._deal_card(card)))

    def _deal_card(self, card) -> None:
        """PORT ADDITION: the flip that brings a card in, and the card arriving with it."""
        card.flip_card(False)
        card.reveal()

    # --- the shuffle ------------------------------------------------------------------------------
    def locked_cards(self) -> list:
        """PORT ADDITION: the cards a shuffle deals again - every slot from LOCKED_CARD_LEVEL up.

        Not `card.locked`, which `--free-cards` turns off: the slots the shuffle is for are the same
        whether or not a test run has unlocked them one by one."""
        return [c for c in self.tarot_cards if c.card_level >= LOCKED_CARD_LEVEL]

    def shuffle_cost(self) -> tuple:
        """PORT ADDITION: (diamonds, coins), and nothing at all while --free-cards is on."""
        if UNLOCK_CARDS_FOR_TESTING:
            return 0, 0
        return SHUFFLE_DIAMONDS, SHUFFLE_COINS

    def refresh_shuffle_button(self) -> None:
        """PORT ADDITION: the price, and what the player has to pay it with.

        Rebuilt on the way into the screen, as the cards' own hints are, because the armory opens over
        this screen and a number read from before a purchase is a number that lies."""
        from ..game.inventory import Inventory
        if self.shuffle_button is None:
            return
        diamonds, coins = self.shuffle_cost()
        # Both wordings are written out rather than built from a %s, so the walk in
        # tools/verify_localization.py can see them: a line with a substitution in it is dropped whole.
        cards = self.locked_cards()
        self.shuffle_button.set_title('Shuffle the locked card' if len(cards) == 1
                                     else 'Shuffle the locked cards')
        self.shuffle_button.label = self.shuffle_button.text
        inv = Inventory.shared()
        if not diamonds and not coins:
            self.shuffle_button.hint = 'Free while testing'
            return
        self.shuffle_button.hint = '%i diamonds and %i coins. You have %i diamonds and %i coins' % (
            diamonds, coins, inv.diamonds, inv.coins)

    def announce_cards(self, cards: list) -> None:
        """PORT ADDITION (user request): read several cards out as one thing to say.

        `Screen.speak` interrupts by default, so one call per card means every card but the last is cut
        off mid-sentence: a shuffle that dealt cards 3 and 4 read out only card 4.  They go in a single
        utterance, each still naming its own slot, so what is heard is the whole hand that moved.
        """
        said = [c.accessible_description(with_action=False) for c in cards if c.accessible_card is not None]
        if said:
            self.speak(' \n\n '.join(said))

    def shuffle_button_pressed(self) -> None:
        """PORT ADDITION (user request): deal every locked card again, at random, for a price.

        It is not a way to shop for a card: every locked slot is dealt again together and what comes back
        may be worse than what went.  It is the way out of a hand that has gone wrong."""
        from ..game.inventory import Inventory
        if self.dealing or self.shuffling:                 # as the cards are, while they are being dealt
            return
        cards = self.locked_cards()
        if not cards:
            return
        diamonds, coins = self.shuffle_cost()
        inv = Inventory.shared()
        if inv.diamonds < diamonds:
            self.host.show_no_diamonds_alert()
            return
        if inv.coins < coins:
            self.host.show_no_coins_alert()
            return
        status_bar = App.delegate().status_bar
        if status_bar is not None:
            if diamonds:
                status_bar.animate_diamonds(-diamonds)
            if coins:
                status_bar.animate_coins(-coins)
        inv.set_diamonds(inv.diamonds - diamonds)
        inv.set_coins(inv.coins - coins)
        # PORT ADDITION (user request): the fourth slot is a chance, so a shuffle rolls for it again.  A
        # hand can come back without it, as though it had never been dealt one, and a hand of three can
        # come back with it.  Nothing says so out loud: the flips do, one per card the shuffle deals, so
        # a four-card hand answering with a single flip has lost its fourth and a three-card hand
        # answering with two has gained one.  That is the language the deal already speaks.
        was = len(self.tarot_cards)
        self.cards_to_load = self.roll_hand_size()
        for number in range(was + 1, self.cards_to_load + 1):
            self.load_card_with_number(number, dealing=False)      # brand new: already its own card
        for number in range(self.cards_to_load + 1, was + 1):
            self.drop_card_with_number(number)
        cards = [c for c in self.locked_cards() if c.card_level <= was]
        for card in cards:
            card.change_card()                            # a new card, stored under its own key
        # every card's hint carries a count of money that has just moved, and the button's carries both
        for card in self.tarot_cards:
            if card.accessible_card is not None:
                card.refresh_accessible_text()
        self.refresh_shuffle_button()
        self._shuffle_lands(self.locked_cards())

    def _shuffle_lands(self, cards: list) -> None:
        """PORT ADDITION (user request): a flip for each card that moved, then both of them read out.

        One sound per card, so what a player hears is how many cards a shuffle dealt - a hand with two
        locked cards is two flips.  Nothing is read out until the last of them has been heard: a card
        spoken while another is still arriving is a card spoken over, and the whole point of paying for a
        shuffle is to find out what came back.

        The button is dimmed until then, so a second press cannot be paid for while the first is landing.
        """
        loop = RunLoop.main()
        self.shuffling = True
        if self.shuffle_button is not None:
            self.shuffle_button.enabled = False

        def flip(n: int) -> None:
            _flip_sound_play()
            if n + 1 < len(cards):
                loop.call_later(SHUFFLE_FLIP_GAP, lambda: flip(n + 1))
                return
            loop.call_later(SHUFFLE_FLIP_GAP, done)

        def done() -> None:
            self.shuffling = False
            if self.shuffle_button is not None:
                self.shuffle_button.enabled = True
            self.announce_cards(cards)

        flip(0)

    def reroll_card_with_number(self, number: int) -> None:   # 0x100035a48
        self.record_card_reload_with_number(number)

    def apply_all_modifiers(self) -> None:                # 0x100035a5c
        dims = {}
        for card in self.tarot_cards:
            self.apply_modifier(card.modifier_name())
            dims[card.modifier_name()] = bool(card.is_good())
        Tracker.shared().init_game_play_tracker()        # +[ADTracker initGamePlayTracker]
        Tracker.shared().set_modifier_dimensions(dims)

    @staticmethod
    def apply_modifier(name) -> None:                     # applyModifier: 0x100035da4
        from ..game.modifiers import GameModifiers
        values = {}
        if name and GameModifiers.shared().has_setter(name):
            values[name] = True
        for key, value in values.items():                 # setValuesForKeysWithDictionary:
            GameModifiers.shared().apply_setter(key, value)

    def play_button_pressed(self) -> None:                # playButtonPressed: 0x100036020
        from ..game.modifiers import GameModifiers
        GameModifiers.shared().reset_modifiers()
        self.apply_all_modifiers()
        App.delegate().go_to_gameplay()

    def show_missions_overlay(self) -> None:              # showMissionsOverlay: 0x1000361b8 (not connected)
        pass

    def record_card_reload_with_number(self, number: int) -> None:   # 0x100036220: analytics only
        pass

    #: PORT DIVERGENCE: Escape - and Circle on a controller, which stands for it - does nothing while the
    #: cards are being dealt (user request).  The Back button is dimmed for those two seconds
    #: (`deactivate_buttons`) and so is Play, but `accessibilityPerformEscape` 0x1000728e4 goes straight to
    #: `backButtonPressed` without asking whether the button it stands for can be pressed, so the original
    #: leaves the screen mid-deal and the port did too.  It said "The cards are still being dealt" at first
    #: and that was taken off again (user request): the deal is two seconds, the cards speak for themselves
    #: at the end of it, and a sentence in the way of them is one more thing to sit through.

    def accessibility_perform_escape(self) -> bool:
        if self.dealing:
            return False                                  # nothing happened, so nothing is heard
        return super().accessibility_perform_escape()

    def back_button_pressed(self) -> None:                # 0x1000364e8
        if self.dealing:                                  # the button itself is dimmed; this is the rest
            return
        self.backbuttonpressed = True
        App.delegate().go_to_play_menu()

    def dealloc(self) -> None:                            # 0x100036598
        if self.tarot_playlist is not None:
            self.tarot_playlist.deactivate()
        super().dealloc()

    # REMOVED (user request): the magic tap 0x100036634 pressed Play.
