# Working on this port

Audio Defence: Zombie Arena (Somethin' Else / Bitbee, 2015) recovered from the iOS binary and rebuilt in
Python for Windows and the Mac.  There was never any source: everything here was read out of an arm64 app
and written again.  These are the conventions that keeps it honest.  The README says what the game is and
how to build it; `docs/PORTING_NOTES.md` says what was changed and why.

## The port is faithful first

* **Reproduce the original's behaviour, including its bugs.**  A quirk is only worth keeping if it is the
  original's - see the fifteen listed in the notes - and a bug is only worth fixing if somebody asked for it
  to be fixed.
* **Work from the disassembly, not from memory.**  `py tools/query.py digest <regex>` gives the annotated
  pseudo-code of a method, `sel` finds who sends a selector, `callers` who calls what.  Read the method you
  are porting while you port it; the addresses in the comments are how the next person checks your work.
* **Every departure is written down.**  A divergence or a port addition goes in `docs/PORTING_NOTES.md`
  with the address of the original method it departs from, and the count at the top of the README moves
  with it.  If it was asked for, say so: "(user request)".

## The changelog is for players

`changelog.txt` is what a player reads.  New lines go under the `unrelease:` heading at the top of the
file, **at the end of that block** - it reads in the order things were done.

* **Write the line.**  A change a player would notice gets one, and whether the `unrelease:` block is
  empty or already long is not a reason either way.  The reasons not to write a line are being told, for
  that change, that it does not need one, and the rule below.
* **A new feature gets one line, and nothing more until it ships** (user request, 2026-09-28).  When
  something new is added, one line says it has been added.  While it has not been released, a fix to it or
  a change to part of it gets no line of its own: players have not had it yet, so there is nothing for them
  to notice has changed.  Extra is the example - "There is an Extra menu under Play" is its line, and a new
  arena or chapter, a retuned arena or a fix to its menus adds nothing.  Once a feature has shipped, a
  change to it gets its line like anything else.  This is for writing new lines: the lines already in the
  block are the maintainer's to prune.
* One entry per line, no wrapping, no bullets, no "Fixed:", no version numbers, no addresses.
* Plain sentences about what a player notices, not what the code does.
* **Name a screen or a tab in words, not as a path.**  "The Speech tab in Settings", not "Settings,
  Speech": a comma standing for a step only reads as one to somebody who already knows the way, and read
  aloud it is two nouns and a pause.
* **Say what the game can now do, not which example arrived with it.**  "The game can be played in
  another language", not "the game can be played in Russian"; "you can turn with buttons on a controller",
  not the two buttons it shipped with.  A changelog line outlives the thing that prompted it, and a
  player reading it later should learn what the game is capable of.  Name the particular language,
  controller or mode in the README, where the list is kept up to date.

  **A tarot card is an example.**  "The Rusty Weapons card jams your gun three times as often" and "the
  Lucky Shot card makes half your shots critical" both went in and both came out again on 2026-09-27:
  the deck is something a player is meant to discover, and a changelog that lists what each card does
  reads like a patch note for a game with a wiki.  Say that the decks have new cards in them, or that a
  card is worth drawing now, and leave the rest to be found.
* **A sentence or two, and stop.**  Say what is different now; leave out what it used to do, why it did
  that, how it was measured, and every number that is not the point.  The reasoning, the measurements and
  the addresses belong in `docs/PORTING_NOTES.md`, where they can be looked up by whoever wants them - a
  player reading the list wants to know what changed, not to be walked through it.  If an entry needs a
  "which used to" or a semicolon to hold it together, it is two entries or it is too long.  Thirty words
  is long; the whole file is under thirty for every entry, so a new one that runs past it is a rewrite,
  not an exception.
* **A line goes under `unrelease:` and nowhere else.**  The version blocks below it - `26.09.26-1:` and
  every one under that - belong to whoever is writing the game.  Do not add to them, take from them,
  reword them, reorder them or reflow them, and do not move a line between them.  A version that has
  shipped is what its players were told at the time.

  This holds whatever the reason looks like: a line in the wrong place, a fault described in a version that
  has gone out, a phrase that would read better.  Say so and leave it.  Being asked for that change is the
  one thing that opens a released block - not a good reason, not an obvious improvement, and not a tidy-up
  that seems in the same spirit as a past one.  It was set aside once, on 2026-09-24, when the released
  sections were cut down because they had been written the long way, and once by hand when the updater came
  out of the preserved copy - both times because the maintainer asked for exactly that.
* A plain `py compiler.py` files the unreleased lines under the version it builds, so leave them where
  they are until then.

## Commits

* One piece of work per commit, with a subject line and a body that says **why**, not just what.
* Pull before you start and push when you are done: more than one person works on this, and a change left
  uncommitted blocks the others.
* Never commit what the build leaves behind (`build/`, `dist/`, `*.spec` are ignored); the game's own data
  in `game/` *is* committed, so a clone has everything.

## Two things that break quietly

* `audiodefence/platform/updater.py` holds `REPOSITORY`, the repository the game updates itself from.  It
  belongs to the repository the build is made in.  The Android app's `platform/updater_android.py` repeats
  it, since the phone cannot import the desktop's updater: change both together.
* The release zips' names decide which one an older build downloads: `AudioDefence-Win-<version>.zip` must
  sort before `AudioDefenceMac-<version>.zip`, because builds from before the Mac port take the first zip
  they find.  Let the compiler name them.

## Testing

Tests are written for the change at hand and are not kept in the repository.  Use a scratch profile - point
`APPDATA` at a temporary folder - so a test never touches a player's save, and silence the listener
(`engine.al.alListenerf(oal.AL_GAIN, 0.0)`) so a test run is not heard.

**Test a thing once.**  A check that has passed for code nobody has touched since will pass again, and
running it again costs the time it takes and says nothing.  So:

* Test what the change touches, and nothing else.  The shield death sound is not evidence about the speech
  card.
* Do not rebuild a check that has just run to prove the same thing again.  Two passes over one change means
  the first one was not trusted, and the answer to that is a better check, not a second one.
* Run it again only when what it covers has changed underneath it - a refactor across the same path, a fix
  on top of the fix.  Say which change made it worth running again.
* A smoke run of the real game is worth one pass at the end of a piece of work, not one per edit.

**Text the player reads or hears has to be translated too.**  The port can be played in another language
(`localization/`), and `py tools/verify_localization.py` fails when a phrase the player can reach is still
English.  Run it after changing or adding anything a screen says, and put the new phrase in each language
file - on 2026-09-26 it caught four that a week of changes had left behind.

**An arena of the port's own is measured, not judged by eye.**  `py tools/arena_pressure.py` prints, for
each wave of each Extra challenge, how much slack the tightest moment of it leaves.  It exists because this
game has no player health - one enemy reaching you ends the run - so a wave's difficulty is not the life in
it but whether each enemy can be killed before its own clock runs out, and a crowd arriving more slowly than
it can be shot never gets harder however large it is.  Sized by eye on 2026-09-28, one arena could not be
lost and another could not be won, and neither was visible until it was measured.  Run it after changing any
wave, and keep the chapter ordered by what it prints.

Some of its numbers are judgement rather than disassembly and say so where they are defined: `DEAF_COST`,
what a ring in the ears is worth given the game gives tinnitus no mechanical effect at all, `MELEE_COST`,
what having only a wok is worth given it reaches three units and a miss ends the run, and the handful
beside them (`STORM_COST`, `DODGE_COST`, `SHOTGUN_WAIT`).  Change them with a reason, not to make a number
look better.

A weapon that hits more than one thing - a shotgun, a grenade - is priced pack by pack rather than enemy by
enemy, and for those the line under an arena gives the rounds it spent against the rounds it was handed,
since a crowd weapon's round is not worth its damage once.  Keep a cushion between the two: the tool never
misses.

**When an arena uses something the tool has never priced, get a second opinion before trusting it.**  On
2026-09-28 a scratch simulation that played each wave out tick by tick disagreed with it on four arenas,
and each time the reason was a thing the tool did not count - an enemy waiting on another's death, the
ground a Dodge loses when it is hit, a melee weapon that only reaches three units.  Four arenas had been
put in the wrong places on those numbers.  The simulation is not a better measure (what it answers depends
on how well its bot plays), which is why it was not kept; it is a way of finding out what the measure is
missing.

**A line with a gap in it goes to a translator whole.**  Write it as one `%` template - "Tarot card number
%i : %s" - and the tools offer it as it is, for the translator to write their sentence round, in their own
order (`%2$s`) and with their own word forms (`{apple|apples}`).  Until 2026-09-28 the tools dropped every
such line, and the advice here was to translate the phrase inside it on its own and glue the line round the
result - which still works, but ties every language to the English order, so a new line is one template.
An f-string or a `str.format` brace is not seen as one: use `%` for anything a player reads.

**Nothing of one language goes into the code** (user request, 2026-09-28).  Its words, its word forms, how
it counts, whole sentences of it: all of that is its own file under `localization/`, so a translator of any
language has everything the first one had.  The code knows how counting rules work (`PLURAL_RULES`, which is
arithmetic) and no language's words.  About sixty lines of Russian moved out of `localization.py` into
`ru.json` that day, checked to read exactly as before over 5,824 lines.

The same goes for the game's own writing when the port corrects it (`data.TYPOS`, `data.REWORDED`): what
the player is told is the corrected sentence, so that is the sentence a language file needs.  The verifier
offers a translator both forms and takes neither away, since the files already carry what their data
says.

**A rule needs all of them, not a handful.**  Whenever a change turns on a threshold, a flag or a test that
will be applied across a whole set - every sound, every screen, every enemy - measure the whole set before
settling it, and say in the commit how many were looked at.  Twice on 2026-09-25 a rule drawn from the few
files in front of me was wrong across the rest: a 20 ms cap on trimming a loop's tail, picked from ten
recordings, had no gap to sit in once all 915 were measured; and `has_escape`, which means the original
implements an escape, was used as though it meant the screen has somewhere to go, which is false for the
main menu.  The first had to be reverted, the second was found by a player.  Checking the set costs one
command and settles it.
