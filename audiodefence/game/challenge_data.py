"""ADChallengeData - completed challenges and unlocked stars (NSUserDefaults "challengeData")."""
from __future__ import annotations

import copy
import logging

from ..platform.defaults import UserDefaults, ns_bool_value, ns_int_value
from . import data

log = logging.getLogger('challenges')


class ChallengeData:
    _shared: 'ChallengeData | None' = None

    @classmethod
    def shared(cls) -> 'ChallengeData':                   # +[ADChallengeData sharedChallengeData] 0x10001dd28
        if cls._shared is None:
            cls._shared = ChallengeData()
        return cls._shared

    def __init__(self):                                   # -[ADChallengeData init] 0x10001ddc0
        self.challenge_data: dict = {}
        self.create_or_restore_challenge_data()

    def create_or_restore_challenge_data(self) -> None:   # 0x10001de40
        stored = UserDefaults.standard().object('challengeData')
        if stored is not None:
            self.challenge_data = copy.deepcopy(stored)   # initWithDictionary:copyItems:YES
        else:
            self.challenge_data = {}
        self.save_challenge_data()

    def dictionary_for_challenge_with_name(self, name):   # 0x10001dfd0 (a mutable copy)
        d = self.challenge_data.get(name)
        return dict(d) if d is not None else None

    def has_completed_challenge_with_name(self, name) -> bool:        # 0x10001e124
        return ns_bool_value((self.dictionary_for_challenge_with_name(name) or {}).get('completed'))

    def has_accuracy_star_for_challenge_with_name(self, name) -> bool:   # 0x10001e1dc
        return ns_bool_value((self.dictionary_for_challenge_with_name(name) or {}).get('accuracy_star_unlocked'))

    def has_time_limit_star_for_challenge_with_name(self, name) -> bool:   # 0x10001e294
        return ns_bool_value((self.dictionary_for_challenge_with_name(name) or {}).get('time_limit_star_unlocked'))

    def player_did_complete_challenge(self, name, accuracy_unlocked: bool, time_limit_unlocked: bool) -> None:
        """-playerDidCompleteChallengeWithName:accuracyUnlocked:timeLimitUnlocked: 0x10001e34c"""
        d = self.dictionary_for_challenge_with_name(name)
        if d is None:
            d = {'completed': True}
        if not (self.has_accuracy_star_for_challenge_with_name(name) or not accuracy_unlocked):
            d['accuracy_star_unlocked'] = True
        if not (self.has_time_limit_star_for_challenge_with_name(name) or not time_limit_unlocked):
            d['time_limit_star_unlocked'] = True
        self.challenge_data[name] = d
        self.save_challenge_data()

    def compute_total_challenges_won(self) -> int:        # 0x10001e5f4
        total = 0
        for key in list(self.challenge_data.keys()):
            d = self.dictionary_for_challenge_with_name(key) or {}
            total = total + ns_bool_value(d.get('completed')) + ns_bool_value(d.get('accuracy_star_unlocked')) \
                + ns_bool_value(d.get('time_limit_star_unlocked'))
        return total

    def save_challenge_data(self) -> None:                # 0x10001e814
        ud = UserDefaults.standard()
        ud.set_object(self.challenge_data, 'challengeData')
        ud.synchronize()

    # --- challenges_index.plist ------------------------------------------------------------------
    @staticmethod
    def _world(world):
        return (data.plist_ro('challenges_index') or {}).get(world)

    def total_stars_unlocked_for_world(self, world) -> int:   # 0x10001e8e0
        total = 0
        for plist_name in ((self._world(world) or {}).get('challenges') or []):
            cid = (data.plist_ro(plist_name) or {}).get('challenge_id')
            total = int(self.has_accuracy_star_for_challenge_with_name(cid)) + total
            total = total + int(self.has_completed_challenge_with_name(cid))
            total = total + int(self.has_time_limit_star_for_challenge_with_name(cid))
        return total

    def total_stars_unlocked(self) -> int:                # 0x10001ecd4
        return sum(self.total_stars_unlocked_for_world(w) for w in (data.plist_ro('challenges_index') or {}).keys())

    def stars_requirement_for_world(self, world) -> int:  # 0x10001eefc
        return ns_int_value((self._world(world) or {}).get('starsRequired'))

    def number_of_challenges_for_world(self, world) -> int:   # 0x10001f094
        return len((self._world(world) or {}).get('challenges') or [])

    def _last_challenge_id(self, world):
        challenges = (self._world(world) or {}).get('challenges') or []
        last = challenges[-1] if challenges else None
        return (data.plist_ro(last) or {}).get('challenge_id') if last is not None else None

    # --- the port's own chapters (additions.CHAPTERS) --------------------------------------------
    # PORT ADDITION (user request): the arenas under Play, Extra are gathered into chapters, and a chapter
    # opens on stars as one of their worlds does.  The counting is here beside theirs and separate from it:
    # `totalStarsUnlocked` 0x10001ecd4 walks `challenges_index` and is what gates their worlds, so an arena
    # of ours must never reach it - twenty-one stars of ours would otherwise open City Crossroad (25) and
    # most of Maya Ruin (40) for a player who had never played either.
    def stars_for_challenge_with_name(self, name) -> int:
        """Nought to three, the way the accessible selector counts them."""
        return (int(self.has_completed_challenge_with_name(name))
                + int(self.has_accuracy_star_for_challenge_with_name(name))
                + int(self.has_time_limit_star_for_challenge_with_name(name)))

    def stars_unlocked_for_chapter(self, chapter) -> int:
        from .additions import chapter_arenas
        return sum(self.stars_for_challenge_with_name(cid) for cid in chapter_arenas(chapter))

    def stars_available_in_chapter(self, chapter) -> int:
        from .additions import chapter_arenas
        return 3 * len(chapter_arenas(chapter))

    def total_stars_unlocked_for_chapters(self) -> int:
        from .additions import CHAPTERS
        return sum(self.stars_unlocked_for_chapter(name) for name, _s, _a in CHAPTERS)

    def chapter_is_finished(self, chapter) -> bool:
        """Every arena in it beaten - not merely reachable."""
        from .additions import chapter_arenas
        return all(self.has_completed_challenge_with_name(cid) for cid in chapter_arenas(chapter))

    def chapters_before(self, chapter) -> list:
        from .additions import CHAPTERS
        out = []
        for name, _stars, _arenas in CHAPTERS:
            if name == chapter:
                break
            out.append(name)
        return out

    def chapter_is_open(self, chapter) -> bool:
        """Both of the two things, and not either of them (user request).

        Every arena of every chapter before this one has to be **beaten**, and the stars have to be there as
        well.  Either test on its own lets a player past too early in a way they would notice: seven arenas
        each finished once is seven stars and should not be enough, and four arenas taken for every star they
        have is twelve stars with three of the chapter never played.
        """
        from .additions import chapter_stars_required
        if not all(self.chapter_is_finished(before) for before in self.chapters_before(chapter)):
            return False
        return self.total_stars_unlocked_for_chapters() >= chapter_stars_required(chapter)

    def arenas_left_before_chapter(self, chapter) -> int:
        """How many arenas of the chapters before this one are still unbeaten."""
        from .additions import chapter_arenas
        return sum(1 for before in self.chapters_before(chapter)
                   for cid in chapter_arenas(before)
                   if not self.has_completed_challenge_with_name(cid))

    def stars_left_before_chapter(self, chapter) -> int:
        from .additions import chapter_stars_required
        return max(0, chapter_stars_required(chapter) - self.total_stars_unlocked_for_chapters())

    def has_challenge_after(self, challenge, world) -> bool:   # 0x10001f230
        # PORT ADDITION: a challenge of the port's own (Play, Extra) belongs to no world, so nothing
        # follows it.  Without this the world lookup came back empty and the index arithmetic below ran
        # off the end of an empty list - the crash a player found by pressing Next challenge after one.
        from .additions import EXTRA_CHALLENGES
        if challenge in EXTRA_CHALLENGES:
            return False
        if not ((self._world(world) or {}).get('challenges') or []):
            return False
        return not (self._last_challenge_id(world) == challenge and challenge is not None)

    def challenge_after(self, challenge, world):          # 0x10001f52c
        if challenge is not None and self._last_challenge_id(world) == challenge:
            return ''
        challenges = (self._world(world) or {}).get('challenges') or []
        if not challenges:
            return ''                                     # PORT ADDITION: nothing to be after
        index = challenges.index(challenge) if challenge in challenges else -1   # NSNotFound + 1 wraps to 0
        return challenges[index + 1]

    def has_weapon_for_challenge_with_name(self, name) -> bool:   # 0x10001f868
        from .inventory import Inventory
        d = data.plist_ro(name) or {}
        for w in d.get('weapons') or []:
            if not Inventory.shared().has_unlocked_weapon(w.get('name')):
                return False
        for req in d.get('challenges_requirement') or []:
            if not ChallengeData.shared().has_completed_challenge_with_name(req):
                return False
        return True

    def needs_weapon_to_complete_challenge_with_name(self, name) -> bool:   # 0x10001fc94
        from .inventory import Inventory
        has_requirements = self.has_challenge_requirements_for_challenge_with_name(name)
        for w in (data.plist_ro(name) or {}).get('weapons') or []:
            if not (Inventory.shared().has_unlocked_weapon(w.get('name')) or not has_requirements):
                return True
        return False

    def has_challenge_requirements_for_challenge_with_name(self, name) -> bool:   # 0x10001ffbc
        for req in (data.plist_ro(name) or {}).get('challenges_requirement') or []:
            if not ChallengeData.shared().has_completed_challenge_with_name(req):
                return False
        return True
