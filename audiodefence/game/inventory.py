"""ADInventory - owned weapons and power-ups, loadout slots, coins and diamonds."""
from __future__ import annotations

from ..platform.defaults import UserDefaults, ns_bool_value, ns_int_value
from . import data


class Inventory:
    _shared: 'Inventory | None' = None

    @classmethod
    def shared(cls) -> 'Inventory':           # +[ADInventory sharedInventory] 0x10000c0ac
        if cls._shared is None:
            cls._shared = Inventory()
        return cls._shared

    def __init__(self):                       # -[ADInventory init] 0x10000c144
        self.defaults = UserDefaults.standard()
        self.weapons: list[dict] = []
        self.powerups: list[dict] = []
        self.weapon_slot1 = None
        self.weapon_slot2 = None
        self.weapon_slot_melee = None
        self.power_up_slot = None
        self._coins = 0
        self._diamonds = 0
        #: PORT ADDITION: true while the save is being restored, so putting the saved balance back is not
        #: counted as earning it.  A fresh profile's balance - none, STARTING_COINS - is not earnings either.
        self._restoring = True
        self.create_or_restore_weapon_dictionary()
        self._restoring = False

    #: PORT DIVERGENCE (user request, 2026-10-05): what a new save starts with.  The original gives a first
    #: start 5000 coins and 500 diamonds (0x10000c1c4), enough to buy most of the armory before a game is
    #: played; with none, the guns and upgrades are earned in Endless, the challenges and the missions, so
    #: there is something to play them for.  A save that has a balance keeps it.
    STARTING_COINS = 0
    STARTING_DIAMONDS = 0

    def create_or_restore_weapon_dictionary(self) -> None:   # 0x10000c1c4
        d = self.defaults
        if d.object('weaponDictionary') is not None:
            self.setup_weapons()
            self.setup_powerups()
            self.set_weapon_slot1(d.object('weaponSlot1'))
            self.set_weapon_slot2(d.object('weaponSlot2'))
            self.set_weapon_slot_melee(d.object('weaponSlotMelee'))
            self.set_power_up_slot(d.object('powerupSlot'))
            self.set_coins(ns_int_value(d.object('coins')))
            self.set_diamonds(ns_int_value(d.object('diamonds')))
            return
        self.weapons = []
        self.powerups = []
        self.set_coins(self.STARTING_COINS)               # PORT DIVERGENCE: 5000 in the original
        self.set_diamonds(self.STARTING_DIAMONDS)         # PORT DIVERGENCE: 500 in the original
        for w in weapons_plist()['Weapons']:
            if ns_int_value(w.get('price')) == 0:
                purchased = ns_int_value(w.get('priceInDiamonds')) == 0
            else:
                purchased = False
            entry = {'name': w.get('name'), 'purchased': purchased, 'level': 1}
            self.weapons.append(entry)
            # NOTE: slots are filled in plist order whether or not the weapon is purchased
            if ns_bool_value(w.get('melee')):
                if self.weapon_slot_melee is None:
                    self.set_weapon_slot_melee(entry['name'])
            elif self.weapon_slot1 is None:
                self.set_weapon_slot1(entry['name'])
            elif self.weapon_slot2 is None:
                self.set_weapon_slot2(entry['name'])
        for p in weapons_plist().get('PowerUps', []):
            self.powerups.append({'name': p.get('name'), 'level': 1})
        self.save_weapon_dictionary()

    def setup_weapons(self) -> None:          # 0x10000cf5c
        self.weapons = []
        for w in self.defaults.object('weaponDictionary') or []:
            self.weapons.append({'name': w.get('name'),
                                 'purchased': ns_int_value(w.get('purchased')) != 0,
                                 'level': ns_int_value(w.get('level'))})

    def setup_powerups(self) -> None:         # 0x10000d48c
        self.powerups = []
        for p in self.defaults.object('powerupsDictionary') or []:
            entry = {'name': p.get('name'), 'level': ns_int_value(p.get('level'))}
            self.powerups.append(entry)

    def _slot_setter(self, attr: str, key: str, value) -> None:
        old = getattr(self, attr)
        setattr(self, attr, value)
        if value is not None and value != old:
            self.defaults.set_object(value, key)
            self.defaults.synchronize()

    def set_weapon_slot1(self, v): self._slot_setter('weapon_slot1', 'weaponSlot1', v)
    def set_weapon_slot2(self, v): self._slot_setter('weapon_slot2', 'weaponSlot2', v)
    def set_weapon_slot_melee(self, v): self._slot_setter('weapon_slot_melee', 'weaponSlotMelee', v)
    def set_power_up_slot(self, v): self._slot_setter('power_up_slot', 'powerupSlot', v)

    def is_weapon_equipped(self, name: str) -> bool:
        return name in (self.weapon_slot1, self.weapon_slot2, self.weapon_slot_melee)

    @property
    def coins(self) -> int:
        return self._coins

    @property
    def diamonds(self) -> int:
        return self._diamonds

    def set_coins(self, value: int) -> None:            # 0x10000dfd8
        value = int(value)
        if self._coins > value:
            from .persistent_stats import PersistentStats
            PersistentStats.shared().save_coins_data(self._coins - value)
        elif value > self._coins and not self._restoring:
            # PORT ADDITION: the other half of the ledger.  saveCoinsData: 0x1000869f4 records what is
            # spent, and the statistics screen asks for "Money earned" as well - a key the original never
            # writes, so its row reads 0 for ever.  Every credit goes through here, so this is the one
            # place that sees them all: challenge rewards, Endless winnings, mission rewards.
            from .persistent_stats import PersistentStats
            PersistentStats.shared().save_coins_earned(value - self._coins)
        self._coins = value
        self.defaults.set_integer(value, 'coins')
        self.defaults.synchronize()

    def set_diamonds(self, value: int) -> None:         # 0x10000e0d4
        value = int(value)
        if self._diamonds > value:
            from .persistent_stats import PersistentStats
            PersistentStats.shared().save_diamonds_data(self._diamonds - value)
        elif value > self._diamonds and not self._restoring:
            from .persistent_stats import PersistentStats     # "Diamonds collected", as above
            PersistentStats.shared().save_diamonds_earned(value - self._diamonds)
        self._diamonds = value
        self.defaults.set_integer(value, 'diamonds')
        self.defaults.synchronize()

    def level_for_weapon(self, name: str) -> int:       # levelForWeaponWithName: 0x10000e1d0
        for w in self.weapons:
            if w.get('name') == name:
                return ns_int_value(w.get('level'))
        return 1                                        # 0x10000e314 / 0x10000e374: w21 = 1 when not found

    def set_level_for_weapon(self, level: int, name: str) -> None:
        for w in self.weapons:
            if w.get('name') == name:
                w['level'] = int(level)
        self.save_weapon_dictionary()

    def level_for_power_up(self, name: str) -> int:     # levelForPowerUpWithName: 0x10000e654
        for p in self.powerups:
            if p.get('name') == name:
                return ns_int_value(p.get('level'))
        return 1                                        # 0x10000e798 / 0x10000e7f8: w21 = 1 when not found

    def set_level_for_power_up(self, level: int, name: str) -> None:
        for p in self.powerups:
            if p.get('name') == name:
                p['level'] = int(level)
        self.save_weapon_dictionary()

    def has_unlocked_weapon(self, name: str) -> bool:   # 0x10000ef5c
        for w in self.weapons:
            if w.get('name') == name:
                return bool(w.get('purchased'))
        return False

    def number_of_weapons_unlocked(self) -> int:
        return sum(1 for w in self.weapons if w.get('purchased'))

    def unlock_weapon(self, name: str) -> None:         # 0x10000f338
        for w in self.weapons:
            if w.get('name') == name:
                w['purchased'] = True
                from .persistent_stats import PersistentStats
                PersistentStats.shared().update_number_of_weapons_owned()
        self.save_weapon_dictionary()

    def save_weapon_dictionary(self) -> None:           # 0x10000f5d4
        self.defaults.set_object(self.weapons, 'weaponDictionary')
        self.defaults.set_object(self.powerups, 'powerupsDictionary')
        self.defaults.synchronize()


def weapons_plist() -> dict:
    return data.plist_ro('Weapons')
