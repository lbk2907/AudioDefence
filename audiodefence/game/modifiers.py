"""ADGameModifiers - Tarot / Roulette effects and the Endless difficulty ramp."""
from __future__ import annotations

import datetime
import time

# ===================================================================== what the port's cards are worth
#: PORT DIVERGENCE (user request): the numbers behind the cards whose strength the port has changed.
#: They live here, together, because they are tuning rather than logic - each is read in one place and
#: meant to be argued about - and because a card that names its own odds builds the sentence it shows
#: from the number beside it (`data.REWORDED`), so the words cannot drift from the game.

#: Lucky Shot: the chance, per enemy hit, of a critical.  `calculateHitEnemies` 0x1000c2f14 rolls
#: `random() % 100 == 1`, one hit in a hundred, which is a whole game for one extra critical on a card a
#: player gave a tarot slot to.
#:
#: What this card is really for is the shot that is not lined up.  A weapon's own critical is rolled only
#: inside `criticalSpread`, a cone of 5 to 10 degrees, so a hit that lands without being aimed at can
#: never be a critical, whatever else is in play - Head-Seeking Bullets included, since that one only
#: multiplies the weapon's chance inside the same cone.  This roll sits outside the cone check, so it is
#: the only thing in the game that rewards a hit you did not line up.
#:
#: Fifty, then (user request).  It makes the card the strongest in its deck by some way - Military Grade
#: Weapons is 10% more damage - and that was said at the time and decided on anyway: a game played by
#: ear puts a great many shots into a zombie that was heard rather than aimed at, and a card that pays
#: for those is worth more here than a card that pays for the ones already going where they should.
LUCKY_SHOT_PERCENT = 50

#: Rusty Weapons: the chance, per shot, that the clip is emptied.  `resolveShoot` 0x100015b60 rolls
#: `rand() % 100 == 1`, and because the roll is per shot a small clip is few rolls - a pistol's six rounds
#: come through 94 times in 100, so most guns play a whole game without noticing.  At 3 a clip jams about
#: 17% of the time on the pistol and 78% on the machine gun, which rolls 50 times and takes the game's
#: longest reload at 6 seconds.  Five would put the machine gun at 92%: not a hazard, a broken gun.
RUSTY_JAM_PERCENT = 3

FLAGS = ('slowerEnemies', 'weakerEnemies', 'moreDamages', 'moreMeleeDamages', 'moreBullets', 'freeRevive',
         'luckyShots', 'metalDetector', 'tesla', 'goldenBullet', 'widerSpread', 'moreHeadshots',
         'baseComboBonus', 'morePowerUps', 'betterPowerUps', 'jukebox', 'strongerEnemies', 'cows', 'storm',
         'lessMeleeDamages', 'lessHeadshots', 'rustyWeapons', 'cars', 'enragedHorde', 'narrowedSpread',
         'machine', 'lessDamages', 'lessBullets', 'noCritical', 'fasterReloadTime', 'slowerReloadTime',
         'fasterEnemies')
# setters that exist on the class besides the flags reset by resetModifiers
EXTRA_SETTERS = ('fullMoon', 'bullshit', 'difficultyModifier')

#: PORT ADDITION: flags the port's own tarot cards set (user request).  They are kept apart from FLAGS so
#: that list stays what the original's class has - thirty-two of them, in its own order - and a glance says
#: which effects are Somethin' Else's and which are ours.  Everything that reads FLAGS reads these too:
#: they are cleared by `reset_modifiers` at the start of every game and accepted by `has_setter`, so a card
#: carrying one is applied by `applyModifier:` 0x100035da4 exactly as the original's cards are.
#: PORT ADDITION (user request): the level-4 cards, each of which gives with one hand and takes with the
#: other.  A card here is one flag that turns on two the game already has - a good one and a bad one - so
#: the deck needed no new effects written for it at all, and another card is a line here and a line in
#: `additions.NEW_CARDS`.  `apply_setter` does the turning on, so a paired flag is applied by
#: `applyModifier:` 0x100035da4 like any other and cleared by `resetModifiers` like any other.
#:
#: Nothing here pairs with `tesla`, which has a setter of its own (`set_tesla`) that starts a playlist.
PAIRED_FLAGS = {
    'glassCannon': ('alwaysCritical', 'strongerEnemies'),
    'thunderLuck': ('luckyShots', 'storm'),
    'berserker': ('moreMeleeDamages', 'lessDamages'),
    'bloodMoney': ('metalDetector', 'fasterEnemies'),
    'hairTrigger': ('fasterReloadTime', 'lessBullets'),
    'heavyArtillery': ('moreDamages', 'slowerReloadTime'),
    'cattleMarket': ('luckyNight', 'cows'),
    'steadyBreath': ('widerSpread', 'lessHeadshots'),
    'emergencySupplies': ('betterPowerUps', 'lessPowerUps'),
    'secondChance': ('freeRevive', 'enragedHorde'),
    'ironSights': ('moreHeadshots', 'narrowedSpread'),
    'houseBand': ('baseComboBonus', 'jukebox'),
}

PORT_FLAGS = ('earlyPowerUp', 'luckyNight', 'lessPowerUps', 'lessCoins',
              'alwaysCritical') + tuple(PAIRED_FLAGS)


class GameModifiers:
    _shared: 'GameModifiers | None' = None

    @classmethod
    def shared(cls) -> 'GameModifiers':      # +[ADGameModifiers sharedModifiers] 0x1000de10c
        if cls._shared is None:
            m = GameModifiers()
            m.fullMoon = m.check_full_moon()
            m.reset_modifiers()
            cls._shared = m
        return cls._shared

    def __init__(self):
        for f in FLAGS + PORT_FLAGS:
            setattr(self, f, False)
        self.fullMoon = False
        self.bullshit = False
        self.difficultyModifier = 0.0

    def reset_modifiers(self) -> None:      # 0x1000de1f0
        for f in FLAGS + PORT_FLAGS:
            if f == 'tesla':
                self.set_tesla(False)
            else:
                setattr(self, f, False)
        self.difficultyModifier = 1.0

    def has_setter(self, selector: str) -> bool:
        return selector in FLAGS or selector in EXTRA_SETTERS or selector in PORT_FLAGS

    def apply_setter(self, selector: str, value) -> bool:
        """[ADGameModifiers set<Selector>:YES] when respondsToSelector: says so."""
        if not self.has_setter(selector):
            return False
        if selector == 'tesla':
            self.set_tesla(bool(value))
        else:
            setattr(self, selector, value)
        # PORT ADDITION: a level-4 card is one flag standing for two; see PAIRED_FLAGS
        for half in PAIRED_FLAGS.get(selector, ()):
            self.apply_setter(half, value)
        return True

    # --- derived values --------------------------------------------------------------------------
    def head_shot_modifier(self) -> float:          # 0x1000de51c
        v = 1.5 if self.moreHeadshots else 1.0
        return v - 0.5 if self.lessHeadshots else v

    def enemi_life_modifier(self) -> float:         # 0x1000de584
        v = 0.9 if self.weakerEnemies else 1.0
        if self.strongerEnemies:
            v += 0.2
        return v * self.difficultyModifier

    def enemi_speed_modifier(self) -> float:        # 0x1000de610
        v = 1.2 if self.fasterEnemies else 1.0
        if self.slowerEnemies:
            v -= 0.1
        return v * self.difficultyModifier

    def gun_damages_modifier(self) -> float:        # 0x1000de69c
        v = 1.1 if self.moreDamages else 1.0
        return v - 0.1 if self.lessDamages else v

    def melee_damages_modifier(self) -> float:      # 0x1000de714
        v = 1.25 if self.moreMeleeDamages else 1.0
        return v - 0.25 if self.lessMeleeDamages else v

    def reload_time_modifier(self) -> float:        # 0x1000de77c (only logged by the game)
        v = 1.2 if self.fasterReloadTime else 1.0
        return v - 0.2 if self.slowerReloadTime else v

    def spread_modifier(self) -> float:             # 0x1000de7f4
        v = -5.0 if self.narrowedSpread else 0.0
        return v + 5.0 if self.widerSpread else v

    def set_tesla(self, value: bool) -> None:       # 0x1000de904
        if self.tesla == value:
            return
        self.tesla = value
        try:
            from ..s3d.engine import S3DEngine
            pl = S3DEngine.engine().play_list_with_name('tesla')
        except Exception:
            return
        if pl is None:
            return
        if value:                                   # no deactivate when cleared (0x1000de9ac)
            pl.activate()

    @staticmethod
    def check_full_moon() -> bool:                  # 0x1000de9e8
        now = datetime.datetime.now()
        ref = datetime.datetime(1970, 1, 7, now.hour, now.minute)
        t = int((now - ref).total_seconds())
        m = t - int(t / 0x26ee93) * 0x26ee93        # C '%' (truncating)
        phase = int(m / 86400) + 1
        return phase == 15
