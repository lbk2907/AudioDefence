"""PORT ADDITION: zombies the port's own tarot cards bring with them (user request).

Nothing in the original spawns an enemy outside a wave.  A wave is a plist - `Enemies` with a spawn angle,
a distance and a time - read once when `ADBrick` is built, which is also when the playlists its enemies
need are activated (`loadPLaylistWithName:` 0x10009fdec, `onPlaylistActivated:` 0x1000a0a1c).  That is why
a card that conjures a crowd is not simply a matter of making some `ADEnemy`s: one whose sounds are not
loaded is a zombie a player cannot hear coming, and in this game that is not a glitch but a death.

The way round it is to conjure **the kind of zombie the wave already holds**.  Its playlist is live by
definition, so the crowd is audible from the moment it arrives, and it needs nothing loaded and nothing
waited for.  It reads well too: what arrives is more of what you were already fighting.

The waves themselves are untouched.  `ADBrick` goes on spawning what its plist says, on its own clock, and
these are added to the list it already updates - so the ordinary game carries on around them exactly as it
would if the card had not been drawn.
"""
from __future__ import annotations

import logging
import math

from ..platform import crand

log = logging.getLogger('spawner')

#: How close the rigged ring is dealt.  It has to be inside 5 units for the blast to set a player's ears
#: ringing at all (`solveExplosionWithDictionary:` starts the tinnitus when the blast is nearer than that),
#: and far enough out that a zombie is still walking rather than already lunging - inside 3 units they go
#: aggressive at once (`ADEnemy.update` picks `aggressive` below a squared distance of 9).  3.5 leaves a
#: few seconds to shoot one, which is the whole move the card asks for.
RING_RADIUS = 3.5

#: How many are in it.  The ring's circumference at 3.5 is about 22 units, so ten of them stand 2.2 apart -
#: inside the 3-unit blast radius, which is what makes the chain run the whole way round from one shot.
RING_SIZE = 10

#: The crowd that follows: out where a wave's own zombies are dealt from, and no bigger than one.
CROWD_RADIUS = 10.0
CROWD_SIZE = 5

#: A moment before the first ring, and how long after one is cleared before the next is dealt.  The crowd
#: arrives as soon as a ring is gone, so the next ring lands while the player is still working through it.
FIRST_RING_AFTER = 6.0
NEXT_RING_AFTER = 15.0


class PowderKeg:
    """The Powder Keg card: rings of rigged zombies, and a crowd between them.

    A ring is dealt close and every one of it explodes.  Shoot one and the chain takes the ring with it -
    which is the original's own doing, a blast killing a neighbour that carries its own - and the blasts
    leave the player's ears ringing, several of them stacking up.  When the ring is gone a crowd is dealt
    further out, and nothing in that crowd explodes, the Farties included: it is there to be killed one at
    a time.  Then another ring, while the crowd is still about.  And so on.
    """

    def __init__(self):
        self.ring: list = []
        self.crowd: list = []
        self.ring_was_up = False
        self.next_ring_in = FIRST_RING_AFTER

    def reset(self) -> None:
        """A new game: nothing of the last one is still owed."""
        self.ring = []
        self.crowd = []
        self.ring_was_up = False
        self.next_ring_in = FIRST_RING_AFTER

    # --- the cycle --------------------------------------------------------------------------------
    def update(self, dt: float) -> None:
        from .brick_manager import BrickManager
        from .modifiers import GameModifiers
        if not GameModifiers.shared().times('powderKeg'):
            return
        bm = BrickManager.shared()
        if bm.player_is_dead:
            return
        self.ring = [z for z in self.ring if z.can_be_shot_at()]
        self.crowd = [z for z in self.crowd if z.can_be_shot_at()]
        if self.ring:
            return                                        # there is a ring to deal with first
        if self.ring_was_up:                              # it has just been cleared
            self.ring_was_up = False
            self.crowd += self._deal(CROWD_SIZE, CROWD_RADIUS, rigged=False)
            self.next_ring_in = NEXT_RING_AFTER
            return
        self.next_ring_in -= dt
        if self.next_ring_in > 0.0:
            return
        self.ring = self._deal(RING_SIZE, RING_RADIUS, rigged=True)
        self.ring_was_up = bool(self.ring)
        if not self.ring:                                 # no wave to borrow a zombie from yet
            self.next_ring_in = 1.0

    # --- the dealing ------------------------------------------------------------------------------
    def _deal(self, count: int, radius: float, rigged: bool) -> list:
        """`count` zombies in a circle at `radius`, rigged to blow or certain not to."""
        from .brick_manager import BrickManager
        from .enemy import Enemy
        from .modifiers import CHAIN_REACTION_BLAST
        bm = BrickManager.shared()
        brick = bm.current_brick()
        if brick is None:
            return []
        names = self._names_that_can_be_heard(brick)
        if not names:
            return []
        made = []
        turn = float(crand.c_mod(crand.rand(), 360))      # the ring starts somewhere different each time
        for i in range(count):
            angle = ((turn + i * 360.0 / count) * math.pi) / 180.0
            # PORT ADDITION (user request): a ring of different kinds rather than ten of one.  The wave's
            # own kinds are what there is to choose from - see the module docstring - and they are dealt
            # round the ring in turn, so a ring of ten from a wave of three is not three of one standing
            # together but one of each, three times round.
            name = names[i % len(names)]
            z = Enemy(name)
            z.random_additional_spawn_angle = 0.0
            z.parent_brick = brick
            z.init_sounds()                               # the playlist is live: see the module docstring
            z.set_position((radius * math.sin(angle), radius * math.cos(angle)))
            z.update_orientation()
            z.tag = ((brick.tag * 100) | 1) + len(brick.enemies)
            if rigged:
                # its own explosion, so the ring goes up whatever the other cards say
                z.explosion_dictionary = dict(CHAIN_REACTION_BLAST)
            else:
                # and the crowd never does, not even a Farty, and not even with Chain Reaction in hand
                z.explosion_dictionary = None
                z.no_lent_blast = True
            brick.enemies.append(z)
            z.spawn()
            made.append(z)
        log.info('Powder Keg: %d %s at %.1f units, of %s',
                 len(made), 'rigged' if rigged else 'plain', radius, ', '.join(sorted(set(names))))
        return made

    @staticmethod
    def _names_that_can_be_heard(brick) -> list:
        """Every kind of zombie this wave already holds, whose sounds are therefore loaded.

        Empty when the wave has nothing to borrow - between waves, or a wave of only passers-by - and the
        card simply tries again on a later tick.  The order is the wave's own, so a ring is dealt the
        kinds in the order the wave lists them rather than in whatever order a set happens to give.
        """
        names = []
        for e in list(brick.enemies):
            if e.playlist is None or e.is_a_bystander():
                continue
            if str(e.name) not in names:
                names.append(str(e.name))
        return names
