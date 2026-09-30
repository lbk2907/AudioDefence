# Windows port — status, controls and divergences

The port is written method by method against the disassembly (`py tools/query.py digest|fn …`);
each ported method carries its original address in a comment. This file records what is ported, the
input mapping that replaces touch and motion, and every place the port knowingly differs.

## Running

```
py AudioDefence.py                  # the game: logo, opener (or first control scheme choice), main menu
py AudioDefence.py --endless
py AudioDefence.py --challenge tutorial_1
```

Testing flags: `--mute`, `--no-speech`, `--exit-after SECONDS`, `--free-cards` (the tarot cards that
cannot be changed can be, and cost nothing - for trying one out without playing hands until it turns
up).  These, with `--endless` and `--challenge`, are added to the parser only when `sys.frozen` is not
set, so a build does not have them: they start the game past its own rules, and a release should not
carry the switch that turns those rules off.  `--game` and `--log-level` are in every copy.
The log is written to `%APPDATA%\AudioDefence\audiodefence.log`; saves live in the same folder.

## Ported so far

| area | modules |
|---|---|
| audio engine (S3D on OpenAL Soft, HRTF from the embedded IRCAM set, original Freeverb reverb) | `s3d/` |
| run loop, NSTimer, notifications, NSUserDefaults, C rand | `platform/` |
| speech (NVDA controller client, other screen readers through Prism, SAPI fallback) | `platform/speech.py` |
| parameters, modifiers, inventory, persistent + in-game stats | `game/parameters.py`, `modifiers.py`, `inventory.py`, `persistent_stats.py`, `ingame_stats.py` |
| enemies, passers-by (cows, cars, jukebox, machine), diamonds, power-up containers | `game/enemy.py`, `passerby.py`, `passerby_manager.py` |
| bricks, brick manager, scripted sounds | `game/brick.py`, `brick_manager.py`, `adsound.py` |
| weapons, melee, projectiles, weapon manager | `game/weapon.py`, `projectile.py`, `weapon_manager.py` |
| power-ups (minigun, fireworks, tornado, tesla) and cooldown manager | `game/powerups.py` |
| ambience, player (tinnitus, heartbeat), missions, challenge data | `game/ambient.py`, `player.py`, `missions.py`, `challenge_data.py` |
| gameplay controllers (endless, challenge, opener), revive, pause | `game/gameplay.py` |
| app delegate (launch, menu music, navigation) | `app.py` |
| VoiceOver stand-in, ADNoBarViewController / ADViewController, status bar | `ui/accessibility.py`, `ui/viewcontroller.py` |
| logo, first control scheme choice, main menu, play menu, info pages | `ui/menus.py` |
| tarot (Endless start) | `ui/tarot.py` |
| Endless game over for screen reader users | `ui/gameover.py` |
| world list, challenge selector, challenge overview, challenge completed / failed | `ui/challenges.py` |
| armory: tabs, weapon shop, loadout, power-ups, currency, weapon and power-up detail views | `ui/armory.py` |
| settings, pause, control scheme table | `ui/settings.py` |
| stats portal: Zombiepedia, Statistics, Credits | `ui/statsportal.py`, `ui/credits_text.py` |

Every screen a player can reach with a screen reader is ported, so the port test menu is gone.

Not ported, and unreachable in the original: `ADScenarioRouletteViewController` and `ADStoryViewController`
(`goToRoulette` / `goToStory` have no callers, no nib action and no selector string reaches them),
`ADCheatViewController` (the main menu's cheat button is hidden), `ADEnemyUnlockPopupViewController` and
`ADScoreFeedbackViewController` (never allocated).  The non-accessible (sighted) variants of the ported
screens are not ported either: the port always runs with a screen reader.  A screen that is not ported shows
a placeholder with "Main menu", or "Close" when it was presented.

## Menu controls (VoiceOver stand-in)

Menu screens are built from the iPhone nibs (the 568x320 tag-2781 layout) and read like VoiceOver reads
them: elements top to bottom, then left to right, with their accessibility labels, "button", "dimmed" and
hints.

PORT INPUT: `UIAccessibilityIsVoiceOverRunning()` is always true here (`Speech.screen_reader_running`).
The original's other branch is its sighted game - `ADChallengeSelectorViewController`,
`ADArmoryViewController`, `ADGameOverEndlessViewController` and the rest, none of them ported, since the
port has nothing to look at - and every screen is spoken, by NVDA when it is running, by another screen
reader through Prism when one of those is, and by SAPI 5 when none is.  Asking whether NVDA was running sent a player on SAPI 5 down the sighted path: "... is not ported
yet" on opening a world's challenges and no spoken game view (`AccessibleGameView`).  It also chose the
button mode, which a new profile now picks for itself (see Divergences).

| key | VoiceOver gesture |
|---|---|
| Right / Tab | flick right: next element |
| Left / Shift+Tab | flick left: previous element |
| Ctrl+Right / Ctrl+Left, End / Home | first / last element |
| Enter | double tap: activate (Space did too, until it was taken off) |
| Shift+Enter | a row's second action, where it has one (Settings: the previous value on a row that steps through several - turn sensitivity, tutorial text, vibration, trigger feel) |
| Escape / Backspace | two-finger scrub: `accessibilityPerformEscape` (the Back button on screens with a status bar) |
| Ctrl+Tab / Ctrl+Shift+Tab | last / first element, as End / Home do |
| Down / Up (the unused pair) | next / previous tab or category, where the screen has them |
| Ctrl+Down / Ctrl+Up (the unused pair) | last / first tab or category |
| Page Up / Page Down | no gesture: the menu music volume, up / down (a port addition, see Divergences) |

PORT ADDITION: which pair of arrows moves the cursor is a setting - Left and Right by default, Up and Down
instead if Settings -> Miscellaneous -> Menu layout is switched (`GameParameters.menu_axis`, defaults key
`menuAxis`).  The unused pair does nothing in a menu; Tab, Shift+Tab, Home and End are not affected.  A
swipe has no direction to choose, so none of this comes from the original.

PORT ADDITION: holding a key that steps one element repeats it (`ScreenManager._hold_navigation_key`,
0.4 s then every 0.09 s).  Only 'next' and 'previous' repeat, and only while a menu screen is on top, so
the ends, Enter and every gameplay key are left alone.  VoiceOver's own repeat comes from the swipe being
repeated, so there is nothing in the original to copy here.

PORT UI: Settings holds seven categories - the original's Aiming, Controls and Sound, then Speech, Keyboard,
Joystick and Miscellaneous.  Speech carries who speaks the game and SAPI 5's own voice; Keyboard the key
bindings and Joystick a controller's buttons, each on its own so neither moves the other; Miscellaneous the
rest, from how the cursor moves through a screen to how a controller vibrates.  Keyboard and Joystick
restore their own defaults, and Miscellaneous holds the one button that resets every setting.

PORT ADDITION: the pair that does not move the cursor changes tab (`cross_axis_key`), so the two are always
different keys.  The armory steps through its four tab buttons (`ArmoryScreen.move_tab`, skipping Loadout
when it is not enabled, since its button only raises the EQUIP alert) and the settings panel steps through
its categories (`ControlSchemePanel.move_category`), which is the only way to reach one: the settings
screen opens inside Aiming with that category's heading as its first row, so there is no list of categories
and Escape always leaves the screen.  Both name what they opened before reading the element they land on
(`post_screen_changed(element, prefix)`), and both hold at the ends.  The original has neither:
its tab bar is tapped directly, and its nib label says so - "Change tabs at the bottom of the screen to
navigate the armory", which the port replaces with the keys that do it here.

## Gameplay controls (port input mapping)

The original is played by touch plus device motion; with VoiceOver running it replaces the touch views with
`ADAccessibleGameView`. The port does the same when NVDA runs, sending keys as touches in the matching
screen quadrant of the button-mode layout.

These are the defaults; every gameplay key can be rebound in Settings -> Keyboard, and "Restore default
keys" puts them back.

Next weapon and Reload are bound per control scheme (`KeyMap.BY_MODE`, stored as
`{"button": [...], "gesture": [...]}` under the `keymap` default).  Under Gesture the key stands for a
swipe, so the arrows keep the swipe's direction; under Button it stands for a corner button, where nothing
is directional, so the defaults are W and R.  Rebinding one scheme leaves the other alone, and a key bound
in one scheme does nothing in the other.  Every other action is a single binding shared by both.

| key | gesture mode | button mode |
|---|---|---|
| Space tap / hold | tap = single shot, hold over 0.2 s = continuous fire | top-right corner: tap = fire, hold = continuous |
| Left / Right Ctrl | triple tap: melee | top-left corner: melee |
| Up arrow / **W** | swipe up: next weapon | bottom-left corner: next weapon |
| Down arrow / **R** | swipe down: reload | bottom-right corner: reload |
| Left / Right | turn (see control schemes) | same |
| Escape | Pause button | same |
| Enter | Skip button (challenge narration; opener) | same |
| T | read the challenge timer label | same |

The revive screen after a death is read like the menus (VoiceOver starts on the tip, then Revive and Game
over).

PORT ADDITION: a game controller (`platform/pad.py`, through SDL's game controller layer, so the buttons are
laid out alike on every pad and only their spoken names change).  In play its buttons press the same
actions as the keys (`PadMap`, stored under `padmap` in keys.json beside `keymap`); in the menus
`ScreenManager._pad_menu_key` turns them into the keys the menus already take.

| controller | gesture mode | button mode |
|---|---|---|
| R2 (a trigger counts as pressed past half way) | as Space | as Space |
| R1 | as Ctrl: melee | as Ctrl: melee |
| a stick flicked up / L1 | stick: swipe up, next weapon | L1: next weapon |
| a stick flicked down / L2 | stick: swipe down, reload | L2: reload |
| either stick, sideways | turn at the speed it is pushed | same |
| Options | Pause button (and on the pause screen, Resume) | same |
| Cross | Skip button | same |
| Square | read the challenge timer label | same |

A stick counts as flicked past 60% and let go below 30%, in the direction of its larger axis, so a turn does
not switch weapons.  Turning ignores the first 18% of a stick's travel and grows in proportion past it, up
to the arrow keys' full speed; the three schemes above take that fraction as it is (the yaw rate, the drag
speed or the tilt angle), and a held turn key overrides the stick.

Control schemes (the original's `controlScheme`):

* 1 gyro: holding an arrow rotates the virtual device yaw at 2 rad/s (port choice, `KeyboardMotion.yaw_rate`).
* 2 swipe: holding an arrow drags at 600 points/s (port choice, `SWIPE_POINTS_PER_SECOND`).
* 3 tilt: holding an arrow tilts the virtual device by 0.5 rad (port choice, `KeyboardMotion.tilt`).

The heading itself goes through the original scroll-view model: a 430-point `line.png` strip
(`line@2x.png`, iPhone nib), `(int)offset % (int)width`, and the 5.68889 points-per-degree swipe scale.

## Divergences

* `-[ADWeapon playSingleShootSound]` spins on the main thread until it picks a `_fire_` sound that is not
  playing; with no such sound it would hang forever (the port returns instead).  The weapons' fire sounds last
  1 to 1.7 s while the Tactical Rifle fires every 0.25 s and the Micro SMG every 0.2 s, so after a few quick
  shots every fire sound is still playing and the original waits - the whole game froze for up to a second,
  after the hit sounds had already started.  When every fire sound is still playing the port gives the shot a
  source of its own (`S3DEngine.play_copy_of`) so the shots overlap: an S3DSound owns one OpenAL source, and
  playing it again restarts it, which is heard as the last shot being cut off.  Measured over 20 shots: the
  Tactical Rifle cut 17 of them before this, none after; the Hunting Rifle (0.6 s) never needed it.
* Every enemy plays its own copy of its sounds (`ADEnemy.voice_of`, `S3DSound.copy`).  In the original the
  enemies of one type share a playlist (`playListWithName:atBundlePath:` 0x1000fc050 caches it by name) and
  the playlist holds one sound per file (`-[S3DPlayList each:]` 0x1000ffeb8 caches the agent by key), so
  two zombies of a type share a sound whenever they pick the same file.  Playing a sound that is already
  playing restarts it once, without its loop (`play:fadein:` 0x100105eb8 sets `restart`; the cleanup block
  sends `play`, which is `play:0`); a sound keeps only the last end callback it was given
  (`add3DSoundMonitor:forSound:` 0x100109c7c empties the set first); and the first zombie to be hit or change
  step stops the sound under the other, which then walks on in silence.  Two Shield zombies walking side by
  side for 40 s: one was silent for 13.8 s of it before this, neither for any of it after.  The same sharing
  silenced a second death: the waves of a run all stay in `bricks` (nothing removes one), so the zombie that
  killed you before a revive still holds its attack sound, and when the next zombie of its type kills you,
  `stopAllEnemiesAfterPlayerDeathByEnemyWithName:` 0x1000c71b4 sends the old one
  `stopAfterPlayerWasKilled` 0x100060a58 - it is no longer attacking, so it stops that sound at once.  The
  Shield zombie has one attack sound, so its second kill in a run was always silent.  The file is still
  chosen by the playlist with the same random draws; a copy has its own source, position and end callback
  on the same buffer, and the playlist stops and unloads the copies with its own sounds.
* A passer-by that is finished - walked off, its death heard out, or the game over - stops its own voices,
  and deactivates the playlist it shares with the others of its kind only when none of them still needs it
  (`PasserBy.deactivate_playlist`).  `-[ADPasserBy update:]` 0x10000b770 and the manager's `clean` 0x1000d59bc
  deactivate the playlist and nothing else, which in the original silenced the one sound a kind has.  With a
  copy each (above) it did not: the playlist of a kind is shared by every cow of that kind, so the first to
  walk off deactivated it under the next - a cow still to come walked in unheard, and one already walking had
  its sound cut and its walking loop (`play_any_sound_containing`'s end callback) start it again on a
  playlist nothing would deactivate a second time.  That cow was heard walking long after it had gone,
  beyond the end of the game and into every game after it, and could not be shot (user report, 2026-09-30,
  from Cattle Call).  Measured in a headless play of Cattle Call to its end: one to three cows' walking
  loops still playing after the game's clean-up before this, none after, and every cow still walking at
  the end heard - one of them, the second of its kind in the arena, had been silent.  Only the Extra
  arenas bring a kind of cow back in a later wave; Endless never has two of a kind at once.
* A critical kill of an enemy with no critical death sound falls back on its ordinary death.
  `playDeathSound` 0x100063688 looks for `death_crit`, then `_diecrit_` on a critical kill and for nothing
  else, having first stopped the enemy's hit sound (0x1000637a4); Shield, WeakZombieD, ZombieC and the
  passers-by and pickups have no critical death, so a critical kill cut their hit sound off and played
  nothing.  Melee weapons are critical 5 to 25% of the time, so meleeing a Shield did it often.
* A playlist whose enemy is still being heard is not unloaded yet.  When a dying enemy's last sound ends,
  -[ADEnemy update:] 0x10005eb94 sends `checkPlaylistDeactivation` 0x1000c2da8, which unloads `anyObject`
  of the playlists the waves since stopped using, and its deactivate: completion (0x1000c2f24) sends it
  again until the list is empty.  A wave is cleared the moment its last enemy starts to die, so when two
  died close together the first to fall silent unloaded the other's playlist and stopped its death sound
  half way.  Such a playlist now waits for a later call, which the enemy's own end makes.  (The port had
  dropped the completion's chain and unloaded one playlist per death; it is back.)
* Sound files are decoded ahead of time on a background thread when their playlist is activated, and streamed
  sounds (music, ambience) load in the background like the original's engine-queue loading, so first plays do
  not stall the game (the port used to decode on the main thread: 3-70 ms per new sound, 0.3-0.5 s for an
  ambience at the start of a game).
* `-[ADAppDelegate pauseGame]` presents the pause screen even over an already paused game (or the revive
  view). The port ignores focus loss while paused so screens cannot stack.
* The stats screen's "Money earned" and "Diamonds collected" rows are dead in the original: nothing writes
  those keys (`saveCoinsData:` 0x1000869f4 and `saveDiamondsData:` 0x100086c2c only ever add to
  "Total Money Spent" and "Total Diamonds Spent", which no screen shows), so both read 0 for ever.  The
  port credits them as a run's rewards are paid out (`save_coins_earned`, `save_diamonds_earned`) and adds
  a "Money spent" and a "Diamonds spent" row beside them, reading the totals the original already keeps.
  The crediting is done by `-[ADInventory setCoins:]` 0x10000dfd8 and `setDiamonds:` 0x10000e0d4, which
  already record the other direction when the balance falls: a rise records what was earned, unless the
  save is being restored, since putting a balance back is not earning it.  (Until 2026-09-21 the two
  functions existed and nothing called them, so the rows still read 0 - the fault this note described in
  the original, reproduced by accident.)
* `-[ADAppDelegate pauseGame]` tests `isKindOfClass:[ADGameplayViewController class]`, and
  `ADOpenerGameplayViewController` is one, so the original pauses the opener as well when the app resigns
  active.  On a phone that is a phone call or the home button; on Windows it is every alt-tab, so the port
  pauses real gameplay only (`App.pause_game`).  The logo and the menus never paused in either.
* The settings rows play `click_button` when pressed.  The original's accessible table is silent, but its
  sighted twin's rows are `ADButtonWithFont`s, which click (`-[ADButtonWithFont playSound]` 0x100073578) -
  and the port's categories are pressed like buttons, so they click like them.
* Escape and Circle click, as pressing Back does (user request).  They already run the same method the
  Back button runs - `-[ADViewController accessibilityPerformEscape]` 0x1000728e4 calls
  `backButtonPressed` - but the click lives on `ADButtonWithFont`, not on what the button does, so leaving
  a screen by key was silent and leaving it by button was not.  Rather than a click at each place that
  goes back, `accessibility_perform_escape` now answers whether it went anywhere and the key site makes
  the sound once; a screen that takes Escape for something of its own (the armory closing a weapon page,
  Settings closing an open list) answers True for that, and one that is busy (the tarot screen while the
  cards are dealt) answers False and stays silent.  `MenuScreen` clicks behind its own guard, which is the
  same question asked of a screen that has no nib.  Silence means nothing happened.

  `has_escape` alone was not that question: `-[ADNoBarViewController backButtonPressed]` 0x1000195e8 only
  writes a line to the log, and a screen that never replaced it answers Escape by doing nothing.  The main
  menu is one, and it clicked on a key that did nothing at all.  `AccessibleScreen.goes_back` asks whether
  the screen has a back of its own; the escape is still sent either way, as the original sends it.  Of the
  game's screens the main menu is the only one this quietens.

* A Berserk charging the player keeps its growl when it is hit (user request).  A hit stops the enemy's
  own loop so the pain sound can be heard and asks for it back when that sound ends
  (`-[ADEnemy playHitSoundForDamages:]` 0x100062db8), through `walkOrAgressive` 0x10005fe54 - which answers
  for state 2 and state 3 and nothing else.  A woken Berserk charges in state 8, so the first shot that
  landed on it silenced it for good: it ran the player down without a sound, while its hit sounds went on
  playing, which is what made it look like the sound had been lost rather than stopped.  State 8 now starts
  the "_aggressive" loop again.  `berserk` 0x100060824 cannot be used for that - it returns at once when
  the state is already 8, being the method that sets it.

* An alert's buttons click too (user request).  `UIAlertView`'s buttons are the system's, not
  `ADButtonWithFont`s, so the original's "Not enough Coins!" closes in silence; in the port the alert is a
  screen of its own and its OK is the only thing on it, so pressing it sounds like pressing a button.  The
  click comes after the button's action, where `-[ADButtonWithFont awakeFromNib]` 0x100072f7c puts it.
* `-[ADAppDelegate startMenuMusic:]`'s sound monitor returns an undefined BOOL (a tail call into
  `objc_release`); the port keeps monitoring.
* ARC deallocation side effects (`-[ADWeapon dealloc]` deactivating the weapon playlist, `-[ADPlayer dealloc]`)
  run where the owning reference is dropped.
* Analytics (`ADTracker`, Google Analytics) only log locally.
* `-[ADBrickManager runSanityCheck]` (log-only) is not ported; its `loadBrickChancePlist:` side effects are.
* `-[ADTarotCardViewController flipCard:]` 0x1000a5e50 returns at once while VoiceOver runs, and the flip
  sound is played at the end of the animation it skips, so a VoiceOver player hears nothing at all while the
  cards are dealt.  The port keeps the animation skipped and plays the sound, one card at a time (a second
  apart, the last of them three seconds in), so the deal is audible.
* `-[ADStatusBarViewController deactivateButtons]` 0x10001cee4 fades the Back and Armory buttons to alpha 0
  while a screen animates in - on the tarot screen, the seconds of the deal - which takes them out of the
  reading order for those seconds: long enough to arrow past where the Armory button is about to appear and
  think it is missing.  The port keeps the lock-out but dims them instead of hiding them, so the screen has
  the same shape throughout and the buttons say why they cannot be pressed yet.
* `-[ADTarotViewController viewDidLoad]` 0x10003461c makes Play visible and usable at once while VoiceOver
  runs - the sighted path leaves it off until the deal's block (`viewDidLoad_block_invoke` 0x100034e84,
  2.3 s later) - while `deactivateButtons` locks Back and Armory for those seconds, so Play was the one
  button on the screen that worked during the deal.  The port dims Play with them, and the block brings it
  back when the cards are dealt, as it does for a sighted player.
* The armory's nib label (#2) is an element VoiceOver reads; the port says its line when the armory opens -
  after the tab it opens on, "Weapons. Up and Down change tab..." - and leaves it out of the reading order.
  The four tab buttons (#38, #6, #76, #10) are left out too: the arrows change tab and name what they land
  on, so the buttons are only the controllers' own state now.  Their "This tab is currently selected" hint
  goes with them; the opening line says which tab you are in instead.
* Four of the game's strings are written in capitals for the screen - TAROT_NO_RELOAD, CHALLENGE_INFO_TITLE,
  FACEBOOK_LIKE, TWITTER_FOLLOW.  What is spoken is sentence case, with the label's line breaks collapsed
  (`data.spoken_text`); the text on screen is unchanged.
* `Accessible_ADGameOverEndlessViewController viewDidLoad` 0x100099f50 does not call `[super viewDidLoad]`,
  which is where `startMenuMusic:@"game_over_theme"` lives (0x1000d37cc), so the Endless game over screen is
  silent - kept, because that screen is the run you just lost rather than a menu.  What the port adds is the
  theme on the card screen it leads to, which the original leaves silent as well.
* `-[ADAmbientManager checkAmbiant]` 0x100099444 refuses to start an ambience only when the player is
  dead.  Ending a game from the pause screen is not a death, and `killGameplay`'s clean-up 0.1 s later
  reports every enemy as gone, which calls `checkAmbiant` again - with a Chainsaw still in the brick that
  starts `Chainsaw_ambiant` over, after the game has finished, with nothing left to stop it: it plays on
  over the menus until the next game.  The port also refuses once `killGameplay` has cleared the gameplay
  controller, which is what "there is no game any more" looks like.
* `-[S3DSound resume]` 0x100105694 is one line, `[self setPlayRate:1]`, because the original's engine
  pauses by play rate; the port pauses the OpenAL source instead, and a stopped source still carried its
  paused flag - so a later resume (the next pause, or any `AmbientManager.resume`) called alSourcePlay on
  it and started it again from the beginning.  An enemy's ambience - the Chainsaw's is the audible one -
  could come back over the menus after the game had ended.  Stopping a sound now clears the flag, and
  resume only resumes a source that OpenAL still reports as paused.
* `-[ADInfiniteScrollView awakeFromNib]` 0x10009c4b0 sets the starting content offset (half the content
  width) *before* it sets itself as the delegate, so `scrollViewDidScroll:` never runs for it and the
  engine's head orientation stays 0 while the heading is really pi.  On a phone the gyro pushes the real
  heading within milliseconds; with keys nothing moves until a turn key is pressed, so the first enemies
  are heard half a turn from where they are - behind sounds in front, right sounds left.  The port sends
  the starting heading once, at the end of the same setup.
* The original starts the menu theme on three screens - the main menu, the play menu and the world list -
  and lets it run on from there (`goToChallengeSelector` 0x1000816e0, `goToTarot`, the challenge overview
  and the info pages start nothing), so any menu reached straight out of a game is silent.  The port starts
  it on every menu.  The screens that have a sound of their own keep it: the pause screen, the revive
  screen, the challenge failed screen (its `gameover_N` jingle) and the two game over screens
  ("game_over_theme").
* `-[ADArmoryViewController backButtonPressed]` 0x100076080 dismisses the armory even when a detail view
  has taken the back button, so Escape inside a weapon or a power-up left the armory altogether.  In the
  port Escape closes the detail first, exactly as the detail's own Back button does, and closing a detail
  returns the cursor to the row it was opened from instead of the top of the screen.
* `-[ADAccessibleGameView solveButtonPress]` 0x10008a914 starts continuous fire when the fire quadrant is
  tapped in Button mode, however short the press was.  Continuous fire is a looping "_conti" sound, so the
  release stops it milliseconds later: tapping fire spends bullets almost silently, and because the empty
  click and the reload call-out are only reached from the continuous update, an empty clip is silent too
  unless the key is held.  The button that quadrant stands for does the opposite - `ADButtonWithSwipe`
  fires a single shot when the press is under 0.28 s - and so does Gesture mode, so the port fires a single
  shot for a tap here as well.  Holding still starts continuous fire, from `update()`, untouched.
* The power-up upgrader's button is titled "Upgrade for %i" and the currency is a coin image drawn beside
  it (`setCoins:` then `centerButtonTextWithCoinsImage`, 0x10004da74), which VoiceOver cannot read.  The port
  keeps the title and speaks "Upgrade for N coins".
* The Zombiepedia's sound button (nib #170) is an image view with a tap recogniser and no accessibility
  label - the nib names the two arrows, `applyAccessibility` names the text labels, nothing names this one,
  so VoiceOver reads its image file as "button audio large".  The port calls it "Preview sound", since it is
  the only way to hear the zombie at all.  The two arrows are labelled "Previous button" and "Next button" in
  the nib, which reads as "Next button, button" once the trait is added, so the port calls them "Previous"
  and "Next" and shortens their hints ("Click to view the next enemy's description. This button will be
  unavailable if you are at the end of the list" becomes "Click to view the next enemy").
* The revive screen waits for the killing enemy's `_attack` sound to finish: `-[ADEnemy attack]` 0x100060304
  registers `add3DSoundEndCallback` -> `afterAttackSound` -> `showReviveView`.  Those sounds run from about a
  second to 8.7 s (WeakZombieC, WeakZombieD; Chainsaw 8.2 s) and `Jim_attack.m4a` is 71 s, long enough to
  look like a hang.  The port waits for the sound as the original does but no more than `ADEnemy.REVIVE_AFTER`
  (5 s); the sound is left to finish underneath.
* `ADChallengeFailedViewController`'s two buttons (nib #103 and #84) hold an image and nothing else - no
  title, no accessibility label in the nib or in `viewDidLoad`, and the screen has no `Accessible_` nib - so
  VoiceOver reads them by their image file name ("menu try again single").  The port labels them "Try again"
  and "Challenge selection", after the actions they are wired to.
* Spoken texts that name a touch gesture name the port's key instead: the opener's "Triple tap to skip intro"
  says "Press Enter to skip intro", a tarot card's "(double tap to change for N diamonds)" says "(press Enter
  to change for N diamonds)", and the same for the challenge selector's two hints, the armory's tab hints and
  power-up rows, and the control scheme's "double tap to select" / "Double tap to toggle in-game
  announcements" / "Double tap to test your headphones".  The Aiming rows also replace the original's device
  descriptions ("Holding the device in front of you, turn to face the zombie") with one short line each about
  the turn keys, and the Controls rows say what Button and Gesture change for a keyboard player instead of
  where to tap and swipe.
* A button that only carries an image is read by its image file name ("menu try again single"), which is what
  VoiceOver does with an unlabelled image button; a selected table row is read as "Selected, <row>".
* Most float ivars are Python doubles. Float32 rounding is reproduced only in the touch hold timers
  (0.2 s / 0.28 s thresholds, where it moves continuous fire by one 50 ms tick) and in the heading model;
  other accumulated timers may cross their thresholds one tick differently.
* With nothing stored, `-[ADGameParameters lastControlScheme]` answers -1 and the first launch goes to the
  first control scheme screen - whose Gyro button is hidden while a screen reader runs, so Gyro could never
  be chosen there.  The port starts on **Gyro (scheme 1)** instead, so that screen is skipped; Settings ->
  Aiming still offers Gyro, Swipe and Tilt.
* `-[ADGameParameters isHeadsetPluggedIn]` always answers YES (Windows cannot reliably tell headphones from
  speakers), so the main menu's "Wear headphones" alert is not shown.
* Game Center is removed entirely (user request): the main menu has no Game Center button, and neither the
  main menu's player authentication nor the game over score report exists.
* The stats portal's "More games" button (ADMoreGamesViewController) is left out (user request);
  Zombiepedia, Stats and Credits are there.
* The armory's currency tab is an empty table: its row count comes from a `products` array that nothing in
  the binary ever sets, so the four "free coins" actions it can build (Facebook, Twitter, more games, App
  Store - all of them open web pages) are unreachable in the shipped game and none of them is ported.
* The armory's 1 ms browsing timer only feeds the analytics tracker, so the port does not run it.
* The Zombiepedia's detail pages live side by side in a scroll view; the port only lets the screen reader
  into the page being shown (iOS clips the others).
* A modal view (`accessibilityViewIsModal`) hides its siblings from the screen reader, as UIKit documents:
  the armory's weapon description leaves the tab buttons and the status bar reachable, while the power-up
  upgrader - a child of the armory's own view - hides them (it has its own Back button).
* The game over screen's "Share on twitter" button is removed (user request).
* The three results screens read one row per result, exactly as Copy results pastes it, and Copy results
  comes straight after them, before the screen's own buttons (user request).  The Endless game over
  table has two sections under the headers "Rewards" and "Statistics" (numberOfSectionsInTableView:
  0x10009a89c, tableView:viewForHeaderInSection: 0x10009a690) and reads its rewards as sentences - "Coins,
  You earned 87 coins for killing zombies" (cellForRewardsAtIndex: 0x10009aa80); the challenge completed
  table adds a "Stars" section (0x1000672f8) and inherits the sentences.  Here there are no header rows and
  each value is one line ("Coins Earned: 87", "Score: 1200", the statistics as cellForStatsAtIndex:
  0x10009b7cc and 0x100067c0c word them).  The Endless screen's first row is the run's tarot cards -
  "Tarot cards: More Power Ups! and Glue Barrels" - which the original never shows; a challenge screen
  starts with the challenge's name and "Result: Completed" or "Result: Failed".  The failed screen, which
  shows no figures in the original, reads its rows first and its tip after them.  Copy results reads the
  same rows, adding only its heading.
* The challenge completed screen reads Retry first, then Challenge selection and Next challenge (user
  request).  The nib lays them across one row - Challenge selection at x 5, Next challenge at 189,
  Retry at 364 (#70, #32, #3) - and the reading order follows the frames, so the three were read in
  that order; the port puts Retry's frame first in the row instead, as Try again already comes before
  Challenge selection on the failed screen.  Nothing here is looked at, so the row is only an order.
* What the original typed wrong is put right as its text is read in (user request, `data.TYPOS`, applied in
  `data._load` and `data.localized`, so every screen that shows a piece of the game's writing gets it
  right).  Six misspelled words: the Farty's page says its zombies are "inflated like ballons" and that
  there is no way to "keep al the gas inside"; a training-grounds tip has zombies "more aggresive"; a tarot
  card has "anticlimatic" music; the storm challenge has a "thunderstom"; The Mixed Bag says "remeber".  A
  word typed twice: "In the the Mayan Ruin Arena".  And five capitals in the wrong place: a loading tip
  opening "if you think a Zombie", the Machine Gun's "but careful, It takes ages", the Fireworks' "Each
  Upgrade" where the other four power-ups say "Each upgrade", "Unlocked After beating" on Endless, and
  "Defeat All level 1 Bricks".  A word missing: the Generator Malfunction tarot card says "Shoot it stop it
  for a while".  And a word too many: Meet The Farty's tip warns of being deafened "for a few seconds you
  if they blow up", where tutorial_8's tip already says the same thing correctly.  The game's own files are
  left as they are, so a copy of the app given with --game is corrected too.  How the original writes is
  otherwise its own: its British and American spellings side by side, Dr Bastard with and without his dot,
  the nouns it capitalises on purpose (Zombie, Melee, the Loadout Tab) and its title-case titles are left
  alone.
* The Endless game over screen's PLAY AGAIN button (nib #47) is called Close (user request).  It still does
  what playAgainButtonPressed: 0x10009bf54 does - leave for the Endless card screen - and its hint says so.
* PORT UI: Settings (and the settings part of the pause screen) opens its options as categories - Aiming,
  Controls, Sound, Keyboard - instead of the accessible table's one list under headings; Enter opens a
  category, Escape leaves it.  The original's sighted control scheme screen has the same three as tabs.
  Every change is spoken ("Tilt selected", "Announcer ON", "Turn sensitivity 2").
* PORT ADDITION: the Aiming category can set the turn sensitivity (0.5 to 3, default 1.5, Enter for the next
  value and Shift+Enter for the previous, wrapping round) and restore the aiming defaults.  The original only has that slider on its sighted screen, and stores the value with
  `setInteger:` so 1.5 comes back as 1; the port stores a float.  Sensitivity scales the port's gyro and
  swipe turn rates the way it scales the original's tilt formula.
* PORT ADDITION: `platform/keymap.py` holds the key bindings (the original is touch driven, so it has none).
  Settings -> Keyboard rebinds any gameplay action - press Enter on a row, then the new key, or Escape to
  keep the old one - and "Restore default keys" resets them.  Melee defaults to Left or Right Ctrl.
* PORT ADDITION: the main menu has a Quit button, read last, which shuts the engine down and ends the run
  loop; iOS apps have no Quit.
* View controller presentations and UIView animations are not animated: a screen appears at once, and
  animation completions run after the animation's duration.
* VoiceOver's reading order is approximated from the nib frames (see `ui/accessibility.py`), and no
  screen wraps: moving past the last element (or before the first) stays there, alerts included.
* The original reverb (csl::Stereoverb: two Freeverbs, 6 combs and 3 allpasses each) runs in the port
  itself (`s3d/reverb.py`, checked against the per-sample model in `tools/reverb_calibrate.py`).  Sounds that
  send to it play on a second OpenAL Soft device (loopback, same HRTF) whose render is mixed with the reverb
  into the output through a callback source: about 0.5 ms later than sounds on the output device.  Only
  dryGain = wetGain = 1 is supported, the only values the game uses.
* The per-sound hard clip of the binaural panner (`vDSP_vclip ±1`) is not reproduced.
* Dying in a challenge starts no music.  `-[ADChallengeGameplayViewController showDeathOverlay]` 0x1000db788
  calls `startMenuMusic:@"game_over_theme"` at 0x0db7f0 with nothing guarding it, yet in a recording of the
  real game no theme is heard when you die in a challenge, nor on the retry screen that follows.  What plays
  there is that screen's own sting, a random `gameover_1..3` started by `-[ADChallengeFailedViewController
  viewDidLoad]` 0x100071718 at 0x071c90, and the theme returns only at the challenge selector.  Checked and
  ruled out as the cause: `startMenuMusic:` 0x100082ca0 and its two early exits, `killGameplay` 0x10005c170
  and its 0.1 s block, `playListWithName:` 0x1000fc050 (cached, still returns the playlist once deactivated),
  `activate:` 0x1000fe9c0 (it only skips while already activating), the retry screen's own `viewDidLoad`, and
  all three callers of `stopMenuMusic`.  The mechanism is unidentified - most likely something in S3D's
  asynchronous activation on the device - so this one item follows the ear rather than the line.  Pressing
  End Challenge never reaches here at all, which is why that path was already silent.
* A wave is not reported cleared before its sounds exist.  `-[ADBrick initSounds]` 0x10009f274 builds a
  wave's `ADSound`s inside the playlist's activation callback (the block at 0x10009f4c0), so for a short
  window after the wave loads its `sounds` array is empty although the wave has some, and `brickIsCleared`
  0x1000a1658 walks the enemies and then that empty array and answers "yes".  A wave whose only content is a
  cutscene - tutorial_7_brick_4, the closing line of "Meet The Farty", has no enemies at all - therefore
  looked finished the instant it loaded, and the challenge ended before its sound existed.  On the phone the
  callback lands before anything can ask; here the question arrives first, because a kill produces a second
  deactivation right behind the one that advanced the wave.  A wave that is supposed to have sounds is not
  cleared until it has them - unless its playlist is missing altogether, in which case the sounds can never
  be built and waiting for them would never end.
* Escape on the challenge-completed screen returns to the challenge list (user request).
  `-[ADChallengeCompletedViewController backButtonPressed]` 0x100048728 stops the screen's animations and
  calls `goToMainMenu` at 0x100048804, which on the phone is a one-finger scrub back out of the whole
  challenge flow: the next challenge was then three screens away again, through Play, the world and the
  list.  Escape now calls what the screen's own Select challenge button calls, `missionSelectButtonPressed`
  0x100068f64, so it returns to the list the challenge was started from, and the main menu is one Escape
  further through the world selector.  The button itself is unchanged, and the challenge-failed screen
  (`backButtonPressed` 0x100072004) still goes to the main menu as the original does.
* Returning to the menus does not replay the opening sting (user request).  When a fade ends,
  `reduceMainMenuThemeVolume` 0x100083460 restarts the music through the whole of `startMenuMusic:`
  0x100082ca0, which plays `main_menu_open` - a 13.2 s sting that the theme only joins at 70 per cent of it
  (the monitor block at 0x100083178).  That is right for menus opened fresh, but this call is a *return* to
  the menus, so leaving a finished challenge for the challenge list played the whole intro again before the
  music came back.  The theme starts directly on that path; launching the game, the main menu and every
  other path still play the sting.
* `game_over_theme` and `main_menu_theme` are treated as one track, because they are one file.  Both are
  2,121,278 bytes with the same SHA-256: a single 129-second piece of music shipped under two names.  The
  original treats them as different tracks, so `startMenuMusic:` 0x100082ca0 finds "the track you asked for
  is not playing", calls `stopMenuMusic` at 0x082dc4 and restarts the same music from the beginning - you
  hear it fade out and start again for no audible reason every time you leave a finished challenge for the
  challenge list, or arrive at the completed screen.  The opening sting counts as that music too, being its
  front.  Asking for either name while either is playing now leaves it alone, so the music runs continuously
  from a challenge's closing line through the completed screen and back into the menus.
* PORT ADDITION removed: the gameplay screen used to speak "Skip" when the skip button appeared.  The
  original posts `UIAccessibilityLayoutChangedNotification` with a nil argument (0x1000da8c4), which tells
  VoiceOver the screen changed without speaking or moving the cursor, so every dialog in a challenge was
  being interrupted to announce a button that the key bindings already cover.
* A menu-music request made during a fade is no longer lost.  `startMenuMusic:` 0x100082ca0 returns at
  0x082db0 whenever the theme being asked for is playing, taking that to mean "already playing, nothing to
  do".  While a fade is running that theme is on its way out, not staying, so the request was dropped and
  `startThemeAfterFade` never set: the fade finished, stopped everything, and nothing started it again -
  which left a whole round silent after a quick Try again.  A dying theme no longer counts as playing.
* A playlist can no longer be wedged into never activating again.  `-[S3DPlayList activate:]_block_invoke`
  0x1000fed40 clears `activating` only on the no-completion path (loc_1000ff1c0, the store at 0x0ff1c8).
  Asked to activate a playlist that is already active *with* a completion, it dispatches the completion and
  branches to the epilogue at loc_1000ff198 without clearing the flag, so `activating` stays 1 for good and
  every later `activate:` returns at the guard in 0x1000fe9c0 with its completion never run.  For `main_menu`
  that is silence until the game is restarted, which is what it sounded like: the music stops and no menu or
  replay brings it back.  The flag is cleared on both paths here; the completion still runs either way.
  0x1000fed40 clears `activating` only on the no-completion path - the store at 0x0ff1c8, under
  loc_1000ff1c0.  Asked to activate a playlist that is *already* active and given a completion, it logs
  "ALREADY active, skipping", dispatches the completion, and branches to the epilogue at loc_1000ff198
  without clearing the flag.  `activating` then stays 1 for the rest of the run, and every later
  `activate:` returns at the guard in 0x1000fe9c0 with its completion never run.  For `main_menu` that is
  silence no menu, replay or new challenge can undo - the shape of "the music stopped and never came back".
  The flag is cleared on both paths here; the completion still runs exactly as before.
* PORT ADDITION: the cursor lands on the screen's own first element, not on the status bar.  VoiceOver
  starts at the first element of a screen, which on every screen with a status bar is its Back button, then
  the coins and the diamonds - three pieces of chrome to walk past before reaching what the screen is for.
  `AccessibleScreen.first_content_element` skips the status bar's subtree (view #87, which owns Back, the
  currencies and Armory) when nothing else has decided where to go.  They are all still there, one step
  back.
* PORT ADDITION: Settings -> Miscellaneous -> Remember cursor position, **off by default**.  When it is on,
  leaving a screen records the label the cursor was on and returning puts it back there - matching by label,
  since the rows are new objects after the rebuild.  Off, a screen opens at its first element the way the
  original always does.
* PORT ADDITION: a menu music volume, changed with Page Up and Page Down on any menu screen
  (`screens.menu_music_volume_key`) and kept in settings (`GameParameters.menu_music_volume`, defaults key
  `menuMusicVolume`), 0 to 100% in steps of 10, 100% by default; Reset all settings puts it back.  The keys
  do nothing while the screen underneath is the gameplay, so the pause and revive screens leave them alone
  too, and a key being captured for a binding in Settings -> Keyboard takes Page Up like any other.  It
  applies to the three sounds of the `main_menu` playlist - `main_menu_open`, `main_menu_theme` and
  `game_over_theme`, which is all that playlist holds - through `S3DSound.volume`, a factor on top of the
  gain the game sets (0.4 on the sting and on the theme, `startMenuMusic:` blocks 0x100082f74, 0x10008308c,
  0x10008324c).  100% is that gain unchanged, so the music is never louder than the
  original's.  The volume is kept apart from `gain` because `reduceMainMenuThemeVolume` 0x100083460 fades by
  taking 0.01 off the gain every 0.05 s until it reaches 0: scaling the gain would change how long the fade
  lasts.  The percentage is squared into a gain so the steps sound even.  The ends hold rather than wrap.
* PORT ADDITION: game controllers - see *Gameplay controls* for the bindings and the turning.  A controller
  connecting or going is announced; a button held when it goes is let go.  In the menus a controller button
  stands for a key (the D-pad and sticks for the arrows, Cross Enter, Circle Escape, Square Shift+Enter,
  Triangle Delete, L1/R1 the tab arrows, L2/R2 Page Down/Up), and those key presses carry `pad`, so a key
  being captured in Settings -> Keyboard is cancelled by a controller button instead of taking the key it
  stands for.  SDL is asked (before pygame.init) to let PlayStation pads rumble over Bluetooth.
* A wind-down does not cut the last one off (user request).  A weapon has one sound per file, so playing
  its "_tail" again while the last one is still sounding restarts it (`S3DSound.play`: active -> stop, then
  `_restart_play`).  The Machine Gun's tail runs 1.8 seconds and a burst can be a tenth of that, so tapping
  the trigger cut the wind-down off and started it again at every tap.  The second one is given a voice of
  its own instead (`S3DEngine.play_copy_of`), the way an overlapping shot already is in
  `-[ADWeapon playSingleShootSound]`.

* The low-ammo loop lives with the clip, not with the trigger (user request).  `-[ADWeapon
  continuousStart]` 0x1000154a4 resolves the shot that starts the burst and then builds the "_warningloop"
  and sets its gain to 0, whatever the clip holds; `resolveShoot` 0x100015a1c does set that gain by what is
  left, but it ran before the loop was built, so its setting lands on the loop from the burst before and is
  overwritten with 0.  Only the burst's *second* shot could raise it, and that one is a whole fire rate
  away, so the Tactical Rifle (0.25 s) fired in taps never warned however little was left.  Starting it at
  the right level was not enough on its own: `continuousStop` 0x1000157f8 stops it with the burst, so it
  can only ever sound *underneath* the gun, and measured over a burst it is 12 dB below the gun's own
  "_conti" loop.  Held down that still works - the beeps keep coming and the ear picks the rhythm out of
  the noise - but a tap is one beep under one shot, and it is not heard at all.

  The fix is the level, not the timing (`Weapon.update_low_ammo_warning`, called from `update:`).  It
  sounds while the gun is firing and stops with it, which is the original's own `continuousStart` /
  `continuousStop` pairing - but it is built at a level that can be heard, where the original's could not
  be.  It starts when the clip is down to its last fifth, `resolveShoot`'s own test pulled out as
  `Weapon.running_low`, and `resolveShoot`'s gain line goes: the loop being there is the warning now.

  It beeped between bursts as well for a day, and that came out again (user request).  A warning that
  never stops is a warning nobody hears, and on a gun held low through half a wave it was the loudest
  thing in the arena.

* DIVERGENCE: the pause menu holds every sound where it is, and the arena keeps its ambience (user
  request).  Three faults, all of them the same shape - the original pauses by **play rate**, so `play`
  on a paused sound carries on and a stopped one is simply gone, while this port pauses the OpenAL source,
  where `play` starts again from the beginning.

  `-[ADEnemy resume]` 0x100063d34 is `[sound play]`, ported as written, so every zombie came back from the
  pause menu with a **fresh** growl instead of the one it was halfway through - which is what a player
  heard.  It is `resume` now, the engine having one for exactly this.  And `pause` 0x100063c64 holds
  `sound` and *stops* `painSound`, which costs the original nothing and costs this port a pain sound that
  restarts; both are paused here, along with every other voice an enemy can have going.  The original has
  one sound and one pain sound to think about, where the port gives each enemy its own copy of every file
  (`voice_of`), a few for the ones that overlap (`overlapping_voice_of`) and one for an explosion -
  `Enemy.all_voices` is the list, and a growl heard from the pause menu was one nothing had thought of.

  `pauseGame` 0x10005b5fc says nothing about the player, so the tinnitus rang on through the pause - and
  it loops now, so it rang on for as long as the game sat there.  `Player.pause` holds it; its timer does
  not advance meanwhile, the timers being what `pauseGame` stops, so it comes back with exactly as long
  left as it had.

  The ambience is the one thing that does **not** pause.  `ADAmbiantManager.pause` 0x100099928 pauses the
  base sound, the storm and the enemy ambience; the first two are the room a player is standing in, and a
  room that falls silent when a menu opens is a room that has gone away.  The enemy ambience - a Chainsaw
  revving - is a zombie making a noise rather than the room, so it pauses with everything else the
  zombies are doing.

* Running the clip out with the trigger held is answered (user request).  Two things were in the way.
  `-[ADWeapon update:]` 0x100014c8c plays the click first and stops the gun after it, so the "Reload"
  call-out began underneath the gun still firing; the gun is stopped first here.  And `playClickSound`
  0x100015f0c says nothing if the announcer spoke in the last five seconds, which in a fight is most of the
  time - so the shot that ran the clip out often got no call-out at all, and one arrived later, which is
  what it sounded like when the trigger was let go.  That shot now asks for the call-out whatever the gate
  says (`play_click_sound(announce=True)`); the clicks that follow are still gated, so it is said once.
  A gun with no "_empty" recording answers with its own short warning instead (user request): once for a
  press, and looping while the trigger is held, until it is let go, reloaded or put away
  (`Weapon.empty_warning`, `start_empty_loop`).  The loop is a copy of that sound (`S3DSound.copy`), since
  the press plays the same recording and playing a sound that is already sounding restarts it - they would
  cut each other, and a restart left pending when the trigger was let go started the warning again after it
  had been stopped.  Its own "_warningloop" is deliberately not used for this: that is the low-ammo loop
  under continuous fire, and running low and running out would sound the same.  The Machine Gun, the Claymore and the melee weapons have no empty click in
  `game/sounds/_weapons`, so an empty trigger on them made no sound at all; the Micro SMG, the Pistol and
  nine others do have one and are untouched.  Nothing is taken from anywhere else: the short warning is
  never played by the game as it stands, since `anySoundWihSuffix:@"_warning"` 0x100015dec asks for a name
  ending in "_warning" and the file is "_warning_b", so it does not match in the original either.  The
  looping one does have a job - it is the low-ammo loop under continuous fire - and it is the same sound
  here, told apart by there being no gunfire under it.

* A gun stops firing when it is put away (user request).  `-[ADWeaponManager selectNextWeapon]`
  0x1000a9e04 interrupts a reload on the outgoing weapon and leaves everything else as it is, and only the
  current weapon is updated (`update:` 0x1000a8c38): a gun switched away from mid-burst was left in state 3
  - Continuous - with its "_conti" loop playing and nobody to stop it, which is what was heard as a gun that
  would not stop.  No reload was called out with it either, since the gun the player was then holding had
  never been started and so never ran dry.  `Weapon.stop_firing_now` stops the loop, plays the tail the
  state machine would have played and puts the weapon back to Idle; `continuous_stop` is unchanged for the
  ordinary release, where handing over to state 4 is right because the weapon is still being updated.

  It runs *after* 0x1000a9e04's own reload check, and must: it ends by putting the weapon back to Idle, so
  asked afterwards whether the outgoing gun was reloading the answer was always no, and the interrupt the
  original does never ran.  The reload went on sounding on a gun that was no longer in hand, where nothing
  could reach it - not even melee, which interrupts the reload of `currentWeapon` only.  (Until
  2026-09-25 it ran first, and that is what it cost.)

* A power-up in hand stops when the player dies (user request).  `stopAllEnemiesAfterPlayerDeathByEnemy
  Name:` 0x1000c71b4 stops the enemies, the diamonds and the passers-by, and leaves the power-up running:
  the Minigun fires on into the death overlay, and the wind and the coil go on with it, until the run is
  cleaned up 0.1 s after killGameplay - which is a good while later, with the revive screen in between.
  `PowerUp.stop_after_player_was_killed` ends it where it is, and the death handler calls it as it calls
  the others - along with `WeaponManager.stop_firing_after_player_was_killed` for the gun, since the trigger
  is still down, no release is coming, and the gun fired on into the death overlay (user request).  It matters more since the gun loops (above): played once through it fell quiet by itself.

* The Minigun power-up's gun is heard for as long as it fires (user request).  `-[ADMinigunPowerUp use]`
  0x1000b2850 plays `minigun_fire` with `play:0`, once through, and the recording is 10 seconds
  (`minigun_fire_a` 10.03, `_b` 9.98) against a duration of 5, 7.5, 10 or 12.5 seconds by upgrade (Weapons
  .plist, PowerUps, Minigun).  Fully upgraded the gun therefore falls silent two and a half seconds before
  it stops firing - the bullets still land, the gun is not heard - and `minigun_tail` comes out of that
  silence.  The port loops it; `update:` 0x1000b2934 stops it where it always did, and the recording is
  gunfire end to end, with no silence at either edge to be heard as a seam.

* A weapon's sounds start where the sound does, not where the file does (user request).  Some of the game's own
  recordings open with a moment of nothing - the Machine Gun's `_fire_a` has 133 ms of it, the Grenade
  Launcher's 109, the Bazooka's 62 - and `-[ADWeapon playSingleShootSound]` plays them from the top, so
  every press of the trigger waits that out before it is heard.  Tapping the Machine Gun, which is how it is
  fired, that silence is the gap between the shots.  The files are left as they are: `decoder.lead_in`
  measures the silence once from what the decoder already holds, and `S3DSound.skip_to` starts the source
  past it (`AL_SEC_OFFSET` before the play, in `_play_as_is`, in `copy` and in `play_copy_of`, so an
  overlapping shot starts there too).  It is not only the shot: the Machine Gun's tail opens with the same
  133 ms and its deploy with 145, so letting go after a burst left a gap before the gun wound down, which
  is what it sounded like.  Every sound a weapon takes from its playlist goes through `weapon._at_the_sound`
  - shot, tail, continuous loop, warning, empty click, reload, deploy, voice, and the melee hit and miss -
  and only the silence is skipped: a recording that starts at once, like the Pistol's, is untouched, and a
  file that is quiet for more than a quarter of a second is left alone in case the quiet is the sound
  itself.

* Escape does nothing on the Endless screen while the cards are being dealt (user request).  The Back
  button is dimmed for those two seconds (`deactivate_buttons`), and so is Play in this port, but
  `-[ADViewController accessibilityPerformEscape]` 0x1000728e4 goes straight to `backButtonPressed` without
  asking whether the button it stands for can be pressed - so the original leaves the screen mid-deal, and
  the port did too, by Escape or by the controller's Circle, which stands for it.  `TarotScreen.dealing` is
  on from the deal until `_cards_dealt`, and while it is on the screen holds rather than leaving.  It said
  "The cards are still being dealt" at first and that was taken off again (user request): the deal is two
  seconds, the cards speak for themselves at the end of it, and a sentence in the way of them is one more
  thing to sit through.  `back_button_pressed` holds as well, for anything else that might reach it.

* PORT ADDITION: SAPI 5 is spoken on a thread of its own, and the game plays it rather than Windows
  (`platform/speech_audio.py`, `speech._SapiThread`; Settings -> Speech -> **Use modern output**, on by
  default, `sapiModernAudio`).  Two things were measured on the user's machine and both are fixed here.
  Every SAPI call costs the thread that makes it - 10 ms to hand over a line, 26 to 30 ms when it cuts off
  the one before, up to 50 ms to stop - which on the main thread is a stutter in the arena each time a row
  is read; the calls are made on `_SapiThread` now, and handing over a line costs the game 1.3 ms.  And
  SAPI hands its audio to Windows, which buffers it: asked to stop, the voice keeps talking for what is
  already on its way to the card - 29 ms after 50 ms of speech, 59 after 200, **100 after 500**, growing
  the longer it has been talking - which for a player who interrupts at every row is most of what makes a
  voice feel slow.  With the row on, SAPI is given a stream of the game's own as its sound card
  (`platform/speech_stream.py`, an `ISpAudio` handed to `ISpVoice::SetOutput`) and writes the voice into it
  as it is synthesised, in pieces of about a tenth of a second, at the card's own rate and shape (44.1 kHz,
  mono, 16 bit - a voice is mono, and stereo doubled every byte for a copy of itself); `SpeechAudio` plays
  what arrives through an SDL audio device the speech opens for itself, as `haptic_audio` does for a
  DualSense.  Where that cannot be done - an older comtypes, a SAPI that will not take the stream - the
  line is rendered into an `SpMemoryStream` instead and handed over when it is made (`_render`), which is
  how this was built first and is 9 to 100 ms slower depending on the line's length; and where the card
  itself cannot be had, Windows speaks as it always did.  It is a device of its own on purpose: the engine is OpenAL, whose
  current context belongs to the thread that set it and which the reverb bus moves between two devices as
  it renders, so speech arriving from its own thread and touching any of that stops the game's sound dead -
  which is what it did, the first time this was built on an engine source.  Two more things were measured
  and fixed the same way.  A rendered line is rendered in pieces (`_SapiThread.pieces`, the first short), so
  the first sound comes 30 ms after the key rather than at the end of the whole line; a streamed one needs
  no pieces at all, since the sound leaves SAPI as it is made - measured from the key to the first sound,
  6 ms for a word, 14 ms for a settings row and 23 ms for a paragraph, against 25, 25 and 37 ms rendered,
  and 121 ms rendered for a piece of the length the splitter allows.  Two ways of killing Python 3.14 were
  found while building the stream, both avoided and both written up in `speech_stream.py`: a ctypes call
  that lets the interpreter go, made from inside one of SAPI's callbacks, and letting the stream go while
  SAPI still holds it (which is why `_to_windows` runs before the thread quits, and why `_Sapi.shutdown`
  waits a moment for the thread when a stream is out).  SAPI lets the stream go when it takes its card
  back, and one it has let go of cannot be handed over again, so each install makes a new one.  Whichever
  way the setting is changed, the row tells the thread about it (`modern_audio_changed`) rather than
  leaving it to be noticed when the next line is spoken: the line that says it has been turned off is
  itself interrupted often enough - by the sample line after it, or by the next key - that the hand-back
  could wait for a line that never came, and the game was still playing SAPI itself in the meantime.  Which
  way the voice is going out is in the log either way, one line each way round.  Whichever
  way the setting is changed, what is being said when it changes is cut first: turning it on while Windows
  was speaking left Windows playing 0.2 s of the old line over the top of the new one, out of its own
  buffer, which the switch cannot reach once the voice is pointed elsewhere.  And the
  bytes are read
  out of the stream with `IStream.RemoteRead` rather than asked for with `GetData`, which hands a million
  samples over one COM element at a time with the interpreter held: 61 ms against 1 ms for a page of the
  encyclopedia, and since the game mixes its own sound in Python on the audio thread (the reverb bus), 61 ms
  of held interpreter is a gap in the arena.  With both, the longest the main thread waits while a page is
  spoken is 2.4 ms.  SAPI puts silence in front of every utterance it makes - measured on the user's voice,
  96 ms at rate 0, 56 ms at rate 5, 22 ms with the rate boost - and Windows plays that silence too, which is
  half of what a line costs before it is heard; a line the game plays itself is bytes in a list, so the
  silence comes off the front of it (`without_the_lead_in`, ten milliseconds left so the voice is not cut
  into, and only the front of the first piece: the quiet between sentences is the voice's own timing).
  Rendering takes the voice's output away from Windows, so the Windows path asks for it
  back (`_to_windows`, the card kept from before the first render): without that, turning Modern audio
  output off left the voice speaking into memory nobody played, which is silence until the game restarts.
  The card is watched for going away: a sound device can be unplugged, a controller with a speaker in it can
  drop off, Windows can move to another one, and SDL says nothing about any of it - it stops asking for
  sound, and with nothing watching, the speech is silent for the rest of the game.  Before each line the
  card is asked what it is doing (`still_there`, `SDL_GetAudioDeviceStatus`), and failing that whether it
  has asked for anything in the last quarter second while something was waiting for it; a card that has
  gone is dropped and another opened at once, and with none to be had, Windows speaks until there is one.
  NVDA's own player copes with the same thing, and none of its code is here.
  `Speech.shutdown`, called before the engine's, stops the voice and closes the card, so a line still
  waiting is not heard carrying on after the game has fallen silent.  Closing it goes through SDL itself
  (`SDL_PauseAudioDevice` by ctypes) rather than through pygame: SDL waits for the audio callback to return
  before it pauses, that callback is Python and wants the interpreter, and pygame's `pause` holds the
  interpreter while it waits - so the game hung on the way out about two closes in three, with the reverb
  bus (Python on an audio thread as well) holding the interpreter in the meantime.  ctypes lets the
  interpreter go while it calls, which lets the callback finish.  The fade is played out first, about the
  card's own buffer's worth, so the card is not cut off mid-waveform: that was the click heard as the game
  closed.  Closing the game is all Python work -
  measured: the engine's own stop 63 ms, the speech card 27, `pygame.quit()` 43 - and the arena is mixed by
  Python on the audio thread, so with the music still playing it stuttered between the steps: the listener's
  gain goes to zero first (one call), and the rest happens in silence.  The last line of the log says how long the closing took (`closed in N ms`, counted from the `shutting
  down` line), so a report of a slow close can be answered from a log rather than a stopwatch; what happens
  after it is the interpreter's own teardown.  Shutdown touches only what was used:
  `Speech.readers` builds Prism on being asked for, and building it to tell it to stop took 80 ms.  Control stops the speech wherever it
  is pressed (`ScreenManager.handle_event`, user request), as it does in a screen reader; the key still
  reaches the screen, since it is also the melee key and the menus' first-and-last modifier.  In the menus
  every key cuts what SAPI 5 is saying (`Speech.interrupt_sapi`, user request): a key means the player has
  moved on, and `stop` alone asks whoever speaks *now*, which is the wrong question while a line is in the
  air - changing Speech output from SAPI 5 to Automatic left SAPI's line playing to the end, since by then
  Automatic was NVDA and NVDA was saying nothing.  Not in a game, where a key is firing or turning and an
  announcement is not what the player meant to stop.  NVDA's own
  driver holds its first 50 ms of audio back before playing any (`_FIRST_AUDIO_CHUNK_MIN_DURATION_MS`), so
  the first sound here - 30 ms after the key, 40 for a page of the encyclopedia - is the same trade made
  the same way.  Stopping is then dropping what has not been played, which is instant (measured: a line
  with 512,808 samples still to play is down to the 352 of its fade the moment the next line is asked for),
  with 4 ms of ramp so the cut is not a click.  A `generation` counter carries the interruption to the
  thread: a line whose generation has passed is dropped rather than spoken.  With the row off - or with no
  engine to play through, or if a render fails - SAPI speaks to Windows as it always did, and that path
  stops better too: `ISpeechAudio.SetState(STOP)` before the purge, which halves the tail (100 ms to 45).
  NVDA solves the same problem the same way and calls it the same thing, so its players know the name; none
  of its code is here (it is GPL), and the two are not alike inside - NVDA streams through an `ISpAudio`
  object of its own into its WASAPI player, where this renders to memory through SAPI's documented stream
  and plays it through the engine the game already has.
* PORT ADDITION: what a controller makes you feel (`platform/haptics.py`).  The original never vibrates.
  The proximity heartbeat (`ADPlayer`, player.py) pulses the heavy motor on each beat, scaled as the sound
  is (closeness squared * 0.7 + 0.3).  The rest is felt where it happens to a zombie, so a bullet, a melee
  blow, a projectile and a power-up are all caught the same way: `hitByWeapon:` 0x100060b30 and
  `hitByExplosionAtPosition:...powerupname:` 0x100061284 (which `hitByProjectile:` 0x100061098 calls) pulse
  by the damage the zombie actually lost (0.6 + 0.4 * (damage / 80) ^ 0.6 of full strength, the floor raised from 0.5, which left a small gun faint, so a Micro SMG
  hit is felt and a Bazooka's is felt more), melee as a longer, heavier thud; a shot the shield takes
  (state 6 in `hitByWeapon:`) is a light knock; `die` 0x100061ac8 is a kill; `attack` 0x100060304, the blow
  that kills you, a second of heavy rumble.  `solveExplosionWithDictionary:...` 0x1000c5c40 - a projectile,
  a Farty going off (`explode` 0x100061e6c), the fireworks power-ups - is a rumble by its distance from you
  (full within a metre or so, never under a half), and `blowEnemiesAway:` 0x1000c3e88 (the tornado) a soft
  gust when it pushes anything.  A diamond and a power-up container die like anything else, so `die` hands
  what it is felt as to `Enemy.felt_death`, which `ADDiamondDropper` and `ADPowerUpContainer` override
  (passerby.py): two bright ticks for the diamond, a crack for the crate, neither a kill's low thump.  The
  power-up itself is felt when it takes effect rather than when the crate opens - `-[ADPowerUp activate]`
  0x10001db08 reads the announcement first and `activate:_block_invoke` 0x10001dc6c uses the power-up when
  it has been read, so the swell goes there, behind the `use` the block already made.  It starts with the
  power-up's own sound rather than with the block (user request): `PowerUp.felt_sound` is the deploy the
  `use` has just played - the Tesla's, the Tornado's and the Fireworks' launch, the Minigun's fire loop -
  and `felt_when_it_starts` waits a run-loop pass at a time until that sound is playing, since a sound not
  yet on the card is loaded by being played and starts a moment after `play:`.  After a second of passes it
  is felt anyway.  It then runs as long as that sound does, waveform and motor pulse alike (`felt_start`),
  and for the Minigun, which plays no launch sound at all - `minigun_launch_a/b` are in the playlist but
  `use` 0x1000b2850 only ever plays `minigun_fire` - the 1.5 s `update:` 0x1000b2934 holds its fire for
  while it spins up.  A launch sound has no duration when it is asked for, so the length comes from the
  decoded file the playlist prewarmed, and anything still undecoded falls back to 0.6 s rather than making
  the game wait.  `FELT_START_MAX` caps it at 3 s: the Tornado's launch is 5.7 s and the Fireworks' 5.6,
  which is the whole thing coming in rather than a start, and a rumble that long reads as a pad fault; the
  Tesla's 2.74 s deploy is under the cap and is felt whole.  Two of the four are then felt while they work
  (user request): `-[ADMinigunPowerUp update:]` 0x1000b2934 asks for the gun's own buzz every
  `Haptics.SUSTAIN` (0.12 s) once it is past the spin-up, which goes through the pass's pulse like anything
  else - so a hit it lands is felt *over* the gun rather than instead of it, the motors taking the stronger
  of the two and the grips playing both - and `-[ADTeslaPowerUp update:]` 0x1000d786c cracks when the coil
  takes a zombie, over the kill `setLife:` has just made: high where the kill is low, so the two read as
  one thing.  Neither reaches a DualSense's motors, which the grips carry better.  The menus
  are felt too, and at a strength the hand notices (user request): `ui/accessibility.menu_tick` for the
  cursor moving (`_move`, `_jump`, `MenuScreen.move` and the category and tab keys), 60 ms on both motors,
  as firm as the pulse Settings plays when a strength is stepped; `menu_toggle` for anything activated
  (`View.activate` and `MenuScreen.activate`, so every setting stepped or toggled and every button
  pressed), firmer and longer; and `ScreenManager._felt_screen_change` for a screen, two knocks low to high
  going in (`push_overlay`, `load_view_controller`) and high to low coming back out (`pop_overlay`, only
  where it refocuses - the pops that clear the stack are not a way back), so which way you went is felt as
  well as heard.  None of these reach a DualSense's motors: the grips carry them, and the motors would
  drone through a menu.  What happens in one pass of the run loop is felt once: each kind at its
  strongest, a little firmer for each more of it, the motors at the strongest kind.  A DualSense on USB is
  a four-channel sound card to Windows as well, whose third and fourth channels drive its two haptic
  actuators; `platform/haptic_audio.py` opens it through SDL's audio (pygame._sdl2.audio, 48 kHz float) and
  plays the heartbeat recording the game has just played, low-passed to the actuators' range, and short
  sine knocks, thuds and filtered-noise rumbles for the rest, saturated (`haptic_audio.fat`) so each
  carries as much as it can under a peak of 1, which is what those actuators answer to.  An
  explosion, a death and a kill go to that pad's motors as well (`RUMBLE_AS_WELL`), the fine haptics
  having no weight for the big low things; a bullet's hit and the rest are the fine haptics alone,
  which do not drown the game's sound.  Settings -> Miscellaneous -> Fine haptics (`fineHaptics`, on by
  default) turns the grips off, so such a pad is felt through its motors like any other - for hearing what
  everyone else feels, and for a pad whose fine haptics are not wanted.  Vibration scales every pulse
  (0.4, 0.7, 1), and Strong is
  the pad at full, so anything more has to come from the pulses themselves.  The three were 0.6, 0.85 and 1,
  where Medium and Strong felt alike - a waveform is felt by its height the way a sound is heard by it, and
  0.85 of full is under a decibel and a half down - so they were set well apart and then lifted a little
  (both user requests).  Over
  Bluetooth there is no such card and it rumbles.  Shaking a pad that has an accelerometer (SDL's sensor,
  reached through pygame's own SDL2.dll) calls `motionEnded:withEvent:` 0x10005a108 as the phone's shake
  does, so it swings the melee weapon under Gesture and does nothing under Button; the threshold is 25 m/s2
  against gravity's 9.8, once per half second.  A DualSense's adaptive triggers get the pad's simple
  effects through `SDL_GameControllerSendEffect` - R2 is the pad's weapon effect, shaped like a pistol's:
  take-up to 55% of the travel with nothing in it, the wall from there to 72%, and the break at 72% is the
  shot (`Pads.trigger_points`: R2 with that feel on it presses through the wall at GUN_DOWN and resets at
  GUN_UP, just under the wall, as a pistol does; every other trigger keeps the plain half-way TRIGGER_DOWN,
  having no wall to press through); L2 (reload under Button) is a light spring - only while the game is in
  front;
  a pause, the menus and closing the game set them plain.  Settings -> Miscellaneous -> Joystick vibration
  and Trigger feel set how strong both are - Off, Light, Medium or Strong (`vibration` and `triggerEffects`
  in settings.json; Medium by default, and reset by Reset all settings; a stored true or false from before
  is read as Medium or Off), and the Trigger feel's hint says that only a DualSense has
  one.  Vibration scales every pulse (0.4, 0.7, full); the trigger levels are the effect's strength
  byte (R2 0x14 / 0x28 / 0x50, L2 0x0C / 0x18 / 0x30).  The scale was softened a step after playing with
  it: 0xC0 was too stiff to fire with, and at 0x28 / 0x50 / 0x90 Medium was still hard, so what was Light is
  Medium now and Light is softer than anything there was.  Stepping the row gives a connected DualSense that
  feel for eight seconds (`ControlSchemePanel.sample_triggers`), since the triggers are a game's feel and no
  game is running while you choose it; leaving Settings makes them plain again.  Settings -> Miscellaneous -> Names in hints and tutorial (`keyNames`: Keyboard keys by
  default, or Controller buttons) names a connected pad's buttons, in its family's names (`pad.family`,
  from the name SDL gives it): every row's hint turns the keys a menu button stands for into that button
  (`pad.menu_words`: Shift+Enter, Enter, Delete and Escape become Square, Cross, Triangle and Circle, or X,
  A, Y and B), as do the three labels of the port's that name Enter (a power-up's "press Enter to upgrade",
  a tarot card's "press Enter to change", a challenge's "press Enter to go to armory";
  `View.label_key_words`, worked out as they are spoken, so a pad coming or going is followed at once), and
  the tutorial text, the skip-intro line, `cross_axis_text` ("L1 and R1 change tab, D-pad left and right
  move through it") and the Button / Gesture rows name its game buttons.  With several kinds connected,
  Controller for names (`keyNamesController`) chooses which; otherwise it is the one connected last.  With
  none connected the row is dimmed (a dimmed cell says so, as a dimmed button does), and starting the game
  with none, or the last one going wherever the player is, sets `keyNames` back to Keyboard keys and saves
  it (`Pads._keys_when_none`).  A pad coming or going tells the host (`Pads.changed` ->
  `ScreenManager.pads_changed`), so Settings -> Joystick and Miscellaneous lay themselves out again and a
  button being set for a pad that has gone is given up.  Each kind of pad has its own bindings
  (`PadMap.for_model`, `padmaps` in keys.json, keyed by that name), made from the defaults and saved the
  first time it connects; the one set there was before (`padmap`) is taken over by the first kind connected
  after.  In play each pad's buttons go through its own (`Pads.padmap_for`), and each DualSense's trigger
  feel follows its own Fire and Reload.  Settings -> Joystick rebinds the buttons of the pad its Controller
  row names (with several kinds connected, Enter and Shift+Enter step through them) as Keyboard does keys
  (`PadMap.add` / `set` / `remove_last`, per scheme for Next weapon and Reload), and lists none with no pad
  connected; while a button is being set the host hands the screen the pad's presses as they are
  (`takes_pad_input`).  A stick pushed sideways and the guide button cannot be bound.  Turning is both:
  either stick turns as far as it is pushed and is the pad's own, while `turn_left` and `turn_right` are
  bound to the D-pad to begin with and can be set to any button (user request; `PAD_LABELS` names their
  rows Alternate turn left and Alternate turn right, under the Turn row that says what the sticks do).  A
  button turns at the keyboard's speed, being down or up with nothing in between, and goes through the
  same `GameplayScreen.press` the turn keys do; while one is held it decides, and the sticks have it back
  as soon as it is let go.  `_turn_keys` maps what is held - a key code, or a pad button's source - to the
  action it pressed, so the last one pressed decides whichever it came from.  A press the game takes is
  finished in the game, whatever is on the screen by the time it is let go (`ScreenManager._pad_in_game`):
  Cross is Enter on the way up, since held it is the menus' Control, and skipping the intro with it put a
  menu there before the way up arrived - so one press skipped the intro and then pressed Play, starting a
  game.  Under Gesture the D-pad's
  other two directions switch weapon and reload (user request), beside the stick flicks that already did -
  `PAD_DEFAULTS` gesture lists for `next_weapon` and `reload`.  Bindings that grow like that do not reach a
  profile already written to keys.json, since a stored list replaces the default outright, so a stored list
  that is still exactly what the default used to be is taken as untouched and given the new one
  (`PAD_WAS`); a list the player has changed is left as they left it.  Button mode is not touched: there
  the shoulder and the trigger do both, and the request was for Gesture.
* A fresh profile plays in **Gesture** (user request).  `-[ADGameParameters lastButtonMode]` 0x1000a3aec
  answers `UIAccessibilityIsVoiceOverRunning()` when `buttonMode` is not stored, which in the port is
  always true and so put every new player in Button mode; `GameParameters.DEFAULT_BUTTON_MODE` is False
  instead.  Only a profile with nothing stored is affected: `__init__` writes the mode the first time the
  game runs, so anyone who has played keeps what they had, whether they chose it or the original chose it
  for them.  Settings -> Controls still steps between the two.
* PORT ADDITION: Settings -> Miscellaneous -> Reset all settings (`ControlSchemePanel.reset_all_settings`)
  puts every setting back to what its getter answers when nothing is stored - control scheme 1 (Gyro), the
  turn sensitivity, the button mode (Gesture, as a new profile is), the announcer on, tutorial text,
  menu arrows, cursor memory, the update check, the menu music volume, the vibration and the trigger feel,
  the names in hints and tutorial, and the speech output - through the same setters the rows use.  The key
  bindings are left alone (Settings -> Keyboard has its own Restore default keys), and so are the
  controllers' buttons (Settings -> Joystick -> Restore default buttons).  The original has no reset; this
  one replaced the port's own Restore aiming defaults and Restore menu defaults rows.
* PORT ADDITION: Settings -> Speech -> Speech output (`speechOutput` in settings.json,
  `Speech.choice`, `platform/speech.py OUTPUTS`): Automatic by default - NVDA through its controller
  client, else another screen reader through Prism, else SAPI 5 (`Speech.speak_automatic`) - or one of
  NVDA, JAWS, ZDSR, Narrator, ZoomText, System Access, Window-Eyes, PC-Talker, Boy PC Reader, Sense Reader
  and SAPI 5 only (the Prism ones through `_Readers.current(only)`), with nothing spoken while that one
  cannot speak.  Automatic tries the Prism ones in that same order, not Prism's own (which puts PC-Talker,
  ZDSR and Boy PC Reader before JAWS, and Narrator last).  Enter opens them as a list of their own
  (`ControlSchemePanel.open_choices`, user request): the panel shows the choices instead of the category's
  rows, the one in use is where the cursor lands and is read as selected, Enter takes the one under the
  cursor and Escape or Back leaves the setting as it was - both close the list rather than the screen, the
  way the armory's Escape closes an open weapon page.  The screen's own OK button is hidden while a list is
  open (`ControlSchemePanel._show_ok`, user request): OK finishes the settings screen, and inside a list
  there is nothing for it to finish - Enter takes a choice and Back leaves - so pressing it threw the
  player out of the settings altogether.  They used to step one press at a time, which says
  every choice on the way past: twelve here, and as many voices as the machine has on the voice row below -
  two hundred and fifty on the machine this was written for.  The row says what was taken, through the new
  choice or, when that one cannot speak (`Speech.can_speak`),
  through the automatic one with the reason ("JAWS is not running, so the game will be silent until it is",
  or that Prism is not installed): said through the choice itself, it would not be heard, and a player
  stepping through would not know where they had landed.  The game reads the choice as it starts
  (`__main__`), and the log says when the chosen one stops being able to speak and when it can again.
  While SAPI 5 is what speaks - chosen, or Automatic with nothing else running
  (`ControlSchemePanel.sapi_speaking`, looked at once a second while the category is open, so the rows come
  and go as a screen reader starts or closes) - rows for SAPI 5 itself follow (`_Sapi`, `sapiVoice` / `sapiRate` /
  `sapiRateBoost` / `sapiPitch` / `sapiVolume`): the voice - Control Panel's, as a new SpVoice starts on,
  then every installed token - the rate (-10 to 10) and the volume (0 to 100 in tens), which are SpVoice's
  own properties and start at Control Panel's, and the pitch (-10 to 10), which SAPI has only as XML,
  `<pitch absmiddle>`.  The rate boost is `<rate speed="10">` on top of the rate; some voices go faster
  that way than rate 10 allows and some do not (here Zira did, US Paul and BestSpeech Fred did not), so
  each voice is tried once a session, speaking a line into memory both ways (`boost_supported`), and the
  row is offered only where it helps.  NVDA's own SAPI 5 rate boost is another thing: it speeds the voice's
  audio up with the Sonic library, which the port does not have.  The XML is sent only while the pitch or
  the boost is in use, since a voice may take XML oddly; otherwise the text goes as plain text
  (SVSFIsNotXML), never parsed.  Each change is said in SAPI 5 at the new setting, whatever else is
  speaking.
* DIVERGENCE: a dead player can no longer fire, melee, reload or switch weapons.  `showDeathOverlay` brings
  the death overlay to the front of the gameplay view and gives it `userInteractionEnabled` (0x10005b9e4 and
  0x10005ba20; the challenge controller's own at 0x1000db814), so on a phone it swallows every touch and the
  weapon views beneath it stop responding.  Endless also sets `paused`, which the port already honoured; the
  challenge controller does not, so a dead player kept firing until the failed screen loaded.  Keys are not
  routed through the view hierarchy here, so the overlay is honoured explicitly in `GameplayScreen.key_down`.
  Pause, skip and the timer are handled before that gate and still work, and `key_up` is left ungated so a
  key held at the moment of death still releases cleanly.
* The Swipe aim scheme applied the turn sensitivity twice.  `touchesMoveDetected` 0x10005a3e0 multiplies the
  drag by the sensitivity, as the original does; the port's own key-to-drag generator scaled the drag rate
  by it as well, so Swipe turned with the *square* of the setting while Gyro and Tilt were linear -
  26 degrees a second at 0.5 and 634 at 3.0, against Gyro's 38 and 224.  The port's generator now runs at a
  fixed rate and leaves the scaling to the original's own line.  Measured after: 53.6 / 105.5 / 158.2 /
  211.0 / 316.5 degrees a second at sensitivity 0.5 / 1.0 / 1.5 / 2.0 / 3.0 - linear, like the other two.
* PORT INPUT: the three aim schemes describe themselves by speed.  On a phone Gyro, Swipe and Tilt are three
  different devices; on a keyboard all three are the turn keys held down, and what actually separates them
  is the rate each code path turns at - about 110, 160 and 190 degrees a second at the default sensitivity,
  all scaling in proportion to it.  The rows say so, in place of the original's GYRO_DESCRIPTION,
  SWIPE_DESCRIPTION and TILT_DESCRIPTION, which tell the player to move the handset.
  it was last focused on (`_LAST_FOCUS` in `ui/accessibility.py`) and restores it when it is entered again,
  matching by label because the rows are new objects after the rebuild.  The original rebuilds the screen
  and VoiceOver starts at the first element every time, so leaving a challenge, the armory or the settings
  meant walking back down the list.  A screen seen for the first time opens where it always did.
  0x082db0 whenever `main_menu_theme` is playing, reading that as "already playing, nothing to do".  During
  the 2 s fade `stopMenuMusic` runs (0x100083460, 0.01 of gain every 0.05 s from 0.4) that theme is on its
  way out, so the request is dropped *and* `startThemeAfterFade` is never set; the fade then stops
  everything and nothing starts it again.  Every challenge-ending dialog carries `startMusicBeforeEnd`
  (3 seconds, 5 in tutorial 3), so pressing Try again quickly enough put the next round's request inside
  that fade and left the whole round silent - which is why it would not reproduce to order.  A theme that is
  fading no longer counts as playing, so the request falls through to `startThemeAfterFade`, which
  `reduceMainMenuThemeVolume` already honours when the fade ends.  Scoped to `main_menu_theme`, the only
  track that flag restarts, so the game-over paths are untouched.
* The armory's Back button takes one step, not two.  `backButtonPressed` 0x100076080 hands the press to the
  open detail view (`handleBackActionFromStatusBar` at 0x076120), clears the delegate, and then dismisses
  the armory anyway in the tail call at 0x0761b8 - so one press closed the weapon page *and* threw you out
  of the armory, skipping the list.  Back now matches Escape (`accessibility_perform_escape`): it closes the
  detail and leaves the cursor on the row it was opened from, and a second press leaves the armory.
* A power-up in hand is held while the game is paused (user request).  `pauseGame` 0x10005b5fc stops the
  timers and pauses the bricks and the ambience, and says nothing about a power-up, as it says nothing about
  the weapon (`Weapon.pause`, the same divergence).  The Minigun's fire loops, so it went on firing through
  the pause menu and only stopped when the game came back and its time ran out.  `PowerUp.pause` holds
  whatever the power-up is playing and `resume` lets go of exactly those, so a second pause cannot forget
  what the first is holding.
* Being killed by a Berserk counts (user request).  `-[ADEnemy update:]`'s case 3 posts `PLAYER_DIED` at
  0x10005f16c and then attacks; case 8, the berserk charge, goes straight to `attack` at 0x10005f468 with no
  notification.  `ADInGameStats` learns of a death only from that notification, so the Berserk - the one
  enemy that kills from this state - was never credited with a casualty however many times it killed you,
  and the run was not counted as a death either: `save_stats` asks `update_deaths` only when the flag the
  same notification sets is on, so the Deaths total on the statistics screen missed it too.  Case 8 posts it
  now, as case 3 does.  One post per death still: the enemy goes to state 4 in `attack`, and every other
  enemy is stopped by `stop_all_enemies_after_player_death_by_enemy_with_name`.
* The coins and the diamonds belong to Play (user request).  Each screen decides for itself in the original
  (`setCurrenciesVisibility:` 0x10001d4b0 and `setDiamonsdsVisibility:` 0x10001d5c8 in its `viewDidLoad`),
  and what falls out of that has no pattern: Settings shows them, the Play menu does not, the challenge list
  does, the screen after a challenge does not.  They are shown from the Play menu until the player is back
  at the main menu instead (`App.in_play`, set by `go_to_play_menu` and cleared by `go_to_main_menu`;
  `StatusBar._wanted` has the last word, whatever a screen asks for), so every menu under Play has them -
  a mode added later without being told to - and nothing else does.  A screen inside Play can keep them off
  with `shows_currencies = False`: the Play menu itself does, being the choice between the modes rather than
  one of them, and so does the pause screen, being a fight rather than a menu.
* The power-up page reads like the weapon page (user request).  `ADArmoryPowerUpUpgraderViewController` is
  added to the armory's own view and made modal (`addSubview:` 0x10003b68c, `setAccessibilityViewIsModal:1`
  0x10003b6d8), and a modal view hides all of its siblings - the status bar among them - so the one page
  in the game where coins are spent was the one page that would not say how many you have.  The weapon page
  is added to its tab's view instead and keeps them.  This page now hides the tab underneath it
  (`content_container.elements_hidden`, put back when it closes) rather than being modal, so the status bar
  stays; its back button says what it closes, as the weapon page's "Close weapon description" does, in
  place of the nib's bare "Back" (`voiceOverBack`, 0x10004d848), and sits below the status bar so both
  pages read in the same order; and the title carries the level, as the weapon page's does, where
  `loadInformation` 0x10004da74 has the name alone and nothing on the page said what you already had.
* Closing a weapon page and equipping a weapon click (user request).  Only `ADButtonWithFont` plays a sound
  (`playSound` 0x100073578), and the nib makes these three plain `UIButton`s - `#23` "Close weapon
  description", `#7` and `#26` "Equip instead of" - so they were the last silent presses in the armory.
  The power-up page's own button is an `ADButtonWithFont` (`#103`) and always clicked.
* The power-up page's button says "Close powerup description" (user request), in the game's own spelling -
  the armory tab is "Powerup" and the original's strings are POWERUP - rather than the hyphen this port
  wrote first.  The nib's own title for it is "  BACK", with the accessibility label "Back"; the wording
  follows the weapon page's "Close weapon description", which is the nib's.
* Opening a weapon from the Loadout tab clicks (user request).  The shop's selection plays one
  (`[self playSound]` at 0x100090a88) and so does the power-ups' (0x10003b53c), but the loadout's
  (`-[Accessible_ADArmoryLoadoutViewController tableView:didSelectRowAtIndexPath:]` 0x10004a264) has none,
  and its sighted twin has none either - `handleItemTap:` 0x10000adf4 goes straight to
  `openDescriptionForItemWithName:`.  So the loadout was the one way into a weapon page that was silent.
* The statistics screen speaks a weapon's exact accuracy (user request).  `configureWeaponCell:ForRow:`
  0x1000d0ff0 builds the label at 0x0d129c from everything before the first dot of the accuracy's string
  value, so 66.6 per cent is announced as 66; and a weapon that has never been fired has shotsHit /
  shotsFired = 0 / 0, which is nan, so its row is read out as "accuracy, nan percent".  The figure is spoken
  to one decimal instead, and a weapon with no shots says so.
* PORT ADDITION: the launcher names a missing package rather than handing over a traceback
  (`AudioDefence.py`, `PACKAGES`).  Somebody downloaded the repository's own zip - GitHub's Code, Download
  ZIP, which unpacks as a folder named for the repository and its branch - believing it was the build, ran
  `AudioDefence.py` with a bare Python and got `ModuleNotFoundError: No module named 'pygame'` in
  crash.txt.  A missing one of ours now says which package it is and the line that installs them all, in
  the console, in crash.txt and out loud; anything else still reports the traceback as before.
* PORT ADDITION: a line built from parts is joined with a full stop, and not a second one where a part
  already ends a sentence of its own - a stop, a mark, a colon (`screens.joined`, `ENDS_A_SENTENCE`).  An
  alert is two of those in a row: "Not enough Coins!. You don't have enough Coins ... playing Endless
  Mode.. OK" had one after the title's exclamation mark and another before the button's name.  The same
  joining is used where a screen change names what was opened before the element it lands on
  (`_apply_pending_focus`), which had the same fault in a row's list of choices.
* PORT ADDITION: every screen names itself as you enter it - "Main Menu. Play, button".  These are the
  game's own names: each of these controllers sends `-[ADStatusBarViewController setPageTitle:]` in its
  `viewDidLoad` (ARMORY, PLAY, CHALLENGE, ZOMBIPEDIA, STATISTICS, INFO, GAME OVER, Credits, Dr Bastard's
  Tarot, Challenge completed), and the iPhone nib has no `pageTitle` outlet, so every one of them goes to
  nil and is never seen or heard.  The capitals are not shouted, and four screens are named for the button
  that opens them rather than for the original's title, so the two agree: the main menu is "Main Menu" and
  not "AUDIO DEFENCE"; the stats portal, which the main menu's Info button opens, is "Info" and not
  "AUDIO DEFENCE"; `ADInfoViewController` says which page you opened - "Challenge Info" or "Endless Info",
  after the two buttons on the play menu - instead of the original's bare "INFO"; and the tarot screen is
  "Endless", since it is how Endless starts and the button that reaches it says Endless.  Settings has no
  title in the binary at all and is called "Settings".
  The challenge screens all set "CHALLENGE", which made four different screens announce the same word, so
  each is named for the row that opened it: the world list keeps "Challenge" (the play menu's button says
  that), a world's challenge list takes the world's name from `challenges_index.plist`, a challenge's
  overview takes that challenge's `title`, and the failed screen is "Challenge failed" to sit beside the
  completed screen's own "Challenge completed".  A screen
  that already names what it opened, like the armory's tab, is not made to say it twice.
* PORT ADDITION: the tutorial announcer's lines are also spoken as text, with the keys you have bound
  (`game/tutorial_text.py`, hooked into `-[ADSound play]` 0x1000b416c).  The announcer tells you to tilt the
  device, swipe, or tap a corner button, none of which a keyboard can do.  The brick scripts name these
  sounds with a placeholder - `announcer_tutorial_aim_CONTROLMODE`, `announcer_tutorial_shoot_BUTTONMODE` -
  which `init_sound` 0x1000b3594 resolves against the control scheme and the button mode, so the three aim
  variants share one line and each button/gesture pair shares another.  Rebinding a key changes what is
  said.  With a controller connected and Settings -> Miscellaneous -> Names in hints and tutorial on Controller
  buttons, the lines name its buttons instead ("the R2 button", "a stick flicked up"), aiming is "To aim,
  push either stick left or right", with the buttons that turn named after it by whatever they are bound to
  ("or press the D-pad left button or the D-pad right button", `PAD_AIM_BUTTONS`; with neither bound the
  sticks stand alone).  It says what it is for first, as the melee line does, since a screen reader reads
  the chain of buttons straight through and the purpose would otherwise arrive last.  Under Gesture the
  melee line offers the shake as well ("or shake the controller") when the controller being named has the
  sensor for it (`Pads.can_shake`).  `aimhelp` and `aimprompt` name
  no key and have no line.  Settings -> Miscellaneous -> Tutorial
  text chooses "As the announcer speaks" (the default), "After the announcer finishes", or "Off".
* PORT ADDITION: an action can hold several keys, and the binding rows say how.  Enter adds a key,
  Shift+Enter replaces every key the action has, and Delete removes the one added last; an action is never
  left with none.  The storage was already a list per action - only the rebinding screen was one key at a
  time.  Melee is bound to both Ctrls by default, so it is under whichever hand is not on the turn keys.
* PORT ADDITION: changing a tarot card says the new card.  `changeCardButtonPressed:` 0x1000a62b8
  rewrites the card's `accessibilityLabel` in place, under a cursor that is already sitting on it, and a
  screen reader reads a label when it is moved onto one - not when one changes beneath it.  On the phone
  that mattered less: VoiceOver users flipped with a double tap and swiped on.  Here the card you had
  just paid three diamonds for could only be heard by arrowing off it and back.  It now speaks
  `View.spoken()`, which is the exact text the arrow keys produce when the cursor lands on that card, so
  a changed card is heard as any card is heard.  `announce_card` in `ui/tarot.py`.
* DIVERGENCE (user request): a paused game no longer reloads.  `pauseGame` 0x10005b5fc stops the timers
  and pauses the bricks and the ambience, and says nothing about the weapon, so two things went on
  through a pause.  The reload sound is not a brick's and kept playing.  And `-[ADWeapon update:]`
  0x100014c8c advances `timeInState` by the wall clock between calls rather than by the timer's dt (the
  quirk at the top of `game/weapon.py`), so the first pass after resuming credited the entire length of
  the pause to whatever state the weapon was in: pausing during a reload finished it, however long the
  reload and however long the pause.  Pausing mid-reload was a free reload and a way to stop the clock
  while getting one.  `Weapon.pause` / `.resume` pause the reload and continuous sounds and re-base the
  wall clock on resume, and `pauseGame` / `resumeGame` send them through the weapon manager.
* TRIED AND REVERTED: placing the melee hit on the enemy.  A melee weapon has two recordings, `_miss_`
  and `_hit_`, and the original plays both with `setSpatialized:NO` (`-[ADMeleeWeapon playHitSound]`
  0x100007538, `playMissSound` 0x100007610), so a swing that connects arrives at the head exactly like
  one that does not.  A version of this port placed `_hit_` on the enemy that was struck and played
  `_miss_` at the player for the swing, since the enemy makes no sound of its own for a melee blow -
  `playImpactAndHitSoundForDamages:melee:` 0x10006150c skips the impact sound when `melee` is YES - so
  nothing at all said where the blow landed.
  It shipped in 26.09.22-1 and the players did not want it, which settles it.  Two reasons worth keeping
  here so that nobody reaches for this again.  `_hit_` is not the impact on its own: it is the swing
  *and* the impact in one file, the wok's being 0.97 s of rising whoosh into the clang where `_miss_` is
  0.67 s of whoosh alone.  Splitting that across two positions cuts across a recording that was made as
  one, and it was heard as the impact being clipped rather than as the blow opening out.  And it was a
  deliberate change to a game that had not asked for one: a melee weapon sounding from the hand is what
  the original does, on purpose, and this port's business is that game rather than a better idea of it.
  The gain arithmetic that went with it is gone too; it is in the history if it is ever wanted.
* PORT ADDITION: Restart challenge on the pause screen.  `ADPauseViewController` offers Resume
  (`validateButtonPressed` 0x100055bbc) and End Game (`quitButtonTouched` 0x1000559c0) and nothing else,
  so a challenge already lost - a time limit missed, an accuracy that cannot be recovered - had to be
  played out to its end, or ended and then found again three screens away in the challenge list.  The
  button tears the run down the way End Game does (`MissionManager endGameplay`, then `killGameplay`) and
  starts the same dictionary again, which is what the failed screen's Try again does
  (`tryAgainButtonPressed` 0x100071ee8).  It is built only when the paused game has a challenge
  dictionary, so an endless run does not grow a button for a challenge it is not playing, and it sits
  between the two nib buttons so the order read is Resume, Restart challenge, End Game: least final
  first, most final last.
  The new game has to be started *after* `killGameplay`'s deferred block, not after `killGameplay`
  returns.  That block (0x10005c770, a tenth of a second later) ends in `BrickManager.clean()` and
  `WeaponManager.clean()`, both of which are the shared singletons rather than the dying controller's
  own, so starting the challenge straight away built the new arena first and emptied it a tenth of a
  second afterwards: an arena with nothing in it, and a weapon that still fired.  The delay is
  `KILL_GAMEPLAY_CLEANUP`, named where `killGameplay` schedules it so the two cannot drift apart.
* PORT ADDITION: the game updates itself, which on iOS was the App Store's job and has no counterpart in
  the binary.  `platform/updater.py` asks GitHub for the newest release, compares its tag with the
  version compiled into the executable (`compiler.py` writes the repository's `VERSION` into a module,
  `version.BAKED_MODULE`, so no file beside the executable can change it or be lost), and offers what it
  finds through the game's own alert rather than a Windows dialog, so a screen reader reads it like every
  other screen.  Two things are worth knowing.
  First, nothing a player owns is at risk by construction: every write the game makes goes to
  `paths.user_dir()`, the installed folder is read-only while the game runs, and the updater will not
  write outside the folder the executable is in - so replacing program files cannot touch a save.
  Second, the download is a delta.  The release is one zip of about 155 MB of which nearly all is the
  game's audio, identical in every build; `platform/remotezip.py` fetches the archive's central directory
  over HTTP byte ranges and compares each member's CRC-32 with the file already installed, so a
  code-only build downloads megabytes rather than the lot.  A server that will not serve ranges, or a
  zip64 archive, falls back to fetching the whole asset.  The last step cannot happen from inside the
  game, because a running program holds its own executable and DLLs open: the changed files are staged
  under `%APPDATA%\AudioDefence\updates` with a backup of what they replace, and a PowerShell script
  waits for the game to exit, copies them in, and starts it again - putting the backup back if the copy
  fails.  PowerShell rather than a `.cmd` because a player's folder can have non-ASCII characters in it.
  A download the player puts off is kept, marked ready, and offered again at the next start rather than
  fetched twice; the sweep that clears staging folders leaves that one alone.  The offer has three answers:
  Yes, No (asked again at the next start) and Skip this version (`GameParameters.skipped_update`: the check
  at start-up passes that tag over, a newer one is offered, and Check for updates on the main menu, being
  a question the player asked, still offers it).  The buttons carry hints, which UIAlertView's do not.
  `tools/verify_updater.py` proves the whole path offline, against a local server that serves ranges and
  a real hand-off, on a folder whose name has a space and Arabic in it.
* PORT ADDITION: the game can be played in another language (contributed).  The original ships `en.lproj`
  and `it.lproj` and `game/data.py` reads `en.lproj` as a constant, so the game was built to be translated;
  it never was.  `audiodefence/localization.py` reads `localization/<code>.json`, a flat map of an English
  phrase to that language's, and every place the port already gathers text goes through it - `View.label`,
  `View.hint` and `View.text` as properties, `MenuItem`'s label and hint, a `MenuScreen`'s title,
  `AccessibleScreen.page_title`, `data.localized()`, and `Speech.speak` as the last resort, so nothing the
  player hears escapes it.  The port's own small vocabulary - Selected, dimmed, button, heading - goes
  through the same table, so a translated screen cannot be left with one English word in the middle of a
  sentence.  A line is matched whole first, then as a template (`%i`, `%s`) with its word forms chosen by
  number, then by the pieces the port assembles itself, and last by looking for phrases it
  knows inside a longer line.  Nothing is translated while the language is English, which is the default.
  A conjunction does not by itself make a line translated (`_JOINS`): " and " is a phrase in the table, so
  a line the layer could split but not otherwise translate came back with only its conjunction changed -
  "the text is shown и spoken in" - which reads worse than leaving it alone.  The Language row is the first
  in Miscellaneous and opens its choices as a list, as Speech output and the SAPI 5 voice do, because each
  language names itself in its own script and stepping would read one out in a language not yet chosen.
  `tools/verify_localization.py` walks every phrase the port can show or speak and fails when one is still
  English.  The recorded audio - the announcer and the game's spoken lines - stays English: it is sound, not
  text.

  Nothing of one language is in the code (user request, 2026-09-28).  The layer as it came had Russian
  written into it: a table of Russian word forms keyed by the English word after a number (`UNITS`), the
  Russian way of choosing between them, the Russian "or" and "and", and some twenty whole Russian sentences
  for lines the port builds (`_MANUAL`).  A second language could have none of that without code.  It is all
  in `ru.json` now, and the layer is the same for every language:

  * a line with a gap - `%i` a number, `%s` anything else - is offered to a translator whole, and the
    translation writes its sentence round the same gaps, filled in the English order or by their place in
    the English (`%2$s`), so a language can put them the other way round;
  * a word that changes with a number carries its forms in the translation itself, in braces where the
    language puts it - "нужно %i {звезда|звезды|звёзд}" - and takes the number nearest before it;
  * how a language chooses between them is named once, in the file's "@plural" entry, from
    `PLURAL_RULES`: seven rules of arithmetic (none, one-other, french, east-slavic, polish, czech, arabic),
    no words.  With no number to go by, the last form - the "however many" one - is used.

  Russian reads exactly as it did: old layer and old file against new layer and new file, over 5,824 lines -
  every line of the file filled in at thirteen numbers and several names, every phrase the verifier
  collects, every challenge row, and every line the old hand-written sentences took - not one differs.
  Along the way two things were put right that the old detection had got wrong: the counted word was found
  only when it ended the line ("You need %i stars to play this level" was never inflected, so "нужно 73 звёзд"), and three
  Russian rules added for it the same morning were the kind of thing this is meant to keep out.  The tools
  changed with it: `make_language.py` gives a new language every line with a gap and an empty "@plural", and
  `verify_localization.py` says when a line has more or fewer forms than its "@plural" allows.  Six tarot card
  descriptions with a percent sign in them ("10% more damage") had also been taken for templates and never
  offered; they are now.  A template asked for with its gaps still empty - to be filled in by whoever asked -
  gets each word's last form, so no brace is ever read out.

  `make_language.py` run with nothing after it brings every language file under `localization/` up to date,
  and the template with them (user request, 2026-09-29).  It used to write the template and nothing else,
  so a phrase the port gained reached a new translator and never a language already written, unless each
  file was named in turn.  And a build leaves the translator's `template.json` out: it was bundled with the
  rest of the folder, so a template lying in the folder a build was made from would have been offered to
  every player as "Template, being translated" (a build now writes an empty one of its own: see below).

  The Language row offers each language by its file's name, whatever the file is called (user request),
  rather than from a list in `GameParameters.LANGUAGES`, which named Russian: a language is added by adding
  its file, and the Russian one is offered as "ru" until somebody renames it.  A language chosen whose file
  is no longer there - renamed, or left out of a build - falls back to English, and English is saved, so the
  game does not go on looking for it.  "@plural" is typed by hand, so it is read forgivingly (capitals,
  spaces, underscores and hyphens do not count, and a name a letter or two out is taken for the nearest), and
  `verify_localization.py` names a rule it cannot read and says which one was probably meant.  The choices,
  and how to find a word's forms for each, are written for translators in the README, under "Words that
  change with a number" (user request, 2026-09-29).  They were written into every language file as
  "@plural guide" for a day; `make_language.py` takes that entry back out of a file that has it, since it
  was never a phrase.

  In a build the language files are a folder a player can open, `localization/` beside the executable
  (beside the app on the Mac), rather than data inside `_internal` (user request, 2026-09-29).  The updater
  already did the rest: it puts back any file of the release that is missing or differs, and deletes only
  inside the folders it owns, which this is not.  So the files the game ships are kept as released - a
  change a player makes to `ru.json` is undone by the next update, as a translator's fix is delivered - and
  a copy saved under another name is never touched.  What such a copy cannot get from the updater is the
  lines the game gains, so the game gives it them when it starts (`localization.bring_up_to_date`, a build
  only): each line of the word list the file lacks, empty, where its English sorts, nothing taken out and no
  translation changed, and a file that is not valid JSON left exactly as it was.  The word list is a
  `template.json` the build writes beside the languages, empty, which the updater keeps current like any
  file of the release; it is offered in the Language row only once something in it is translated, since
  until then it is English under another name.  The build fills in the lines a shipped language lacks, in
  its copy, and says so, so the game never has cause to write to a file the updater keeps, and a file
  written by hand is read with or without the byte-order mark Notepad can put first.  Writing a language
  file moved out of `make_language.py` into `localization` (`dump`, `fill_in`), since the game writes them
  too and every file has to come out in one order.  `tools/merge_language.py` puts a file someone sent into
  the game's own: each line they translated, in the place it already has, every change printed, a line
  the game no longer has named rather than added.  Considered and not done: carrying the languages inside
  the executable (nobody could add or fix one), and a player's file of the same name laid over the official
  one (a stale copy would hide every later fix).

  A file of the build that has gone missing is put back from the release of the version the player already
  has, without waiting for a newer one (user request, 2026-09-29).  The build writes the list of its files
  into itself, `release-files.txt` in `_internal` or the app's Resources (`compiler.write_file_list`, the
  same walk as the zip), so the game finds a missing one when the main menu opens without asking GitHub
  (`updater.missing_files`, one look at each file on a worker thread).  It asks Yes or No; the quiet
  update check still runs first when it is on, and a newer version is offered in the missing files' place,
  since installing it puts them back too.  Yes fetches the release by its tag and reads only those files out
  of the zip, or takes them out of the whole zip when the server will not serve ranges, and writes each
  straight into place: a file that is not there holds no lock, so there is no hand-off and no restart, and
  a file that is there is never written, changed or not.  The player is told to restart only when something
  outside `localization/` and the side files came back.  The question is asked as the update is (user
  request, the same day): No is not now and the next start asks again, and with Check for updates when the
  game starts switched off the start asks nothing, while Check for updates, finding nothing newer, offers
  them.  At first No was remembered for that set of files and the start asked with the check off too.  A
  one-file build has nowhere to keep the list and goes without.  Tested against a local server: two files
  deleted and one changed, No asked again next start, Check for updates offering them, Yes putting back
  exactly the two, byte for byte,
  with the changed one and a player's own file untouched, a restart asked for only when a sound came back,
  the whole-zip fallback, and a version missing from GitHub said plainly; `verify_updater.py` still passes.

  A substitution a template opens with no longer reaches back across ", " (`_template_regex`).  A table row
  is spoken as its title, a comma and its status, and "%s required, press Enter to go to armory" swallowed
  the title with the weapon, so a locked challenge that wanted a gun was read "нужно The Mixed Bag, Обрез" -
  the challenge said as though it were the thing to buy - in their challenge list and in Extra's alike.  A
  line like that now falls through to `_translate_segments`, which has learned to take a tail that is a
  whole phrase with separators of its own and translate the head in front of it apart.  Compared over
  3,133 lines - every template in the Russian file filled in, the same with a title glued in front, every
  phrase the verifier collects, and every challenge's row in each state - 114 weapon rows are put right,
  the rest that changed now use a whole line the translator wrote (a stats row, "теперь" after the title
  rather than before it), and none reads worse.

* PORT ADDITION: the additions overlay - the plists are the original, and everything the port adds is in
  code (user request).  `game/` holds Somethin' Else's files exactly as they shipped them: not re-encoded,
  not appended to, not corrected.  They are binary plists, a rewrite of one is an unreviewable diff, and on
  a Mac a player can open them, so a port that wrote into them would leave nobody able to say which parts
  of the game were the game.  `audiodefence/game/additions.py` is where the port's own content is declared
  instead, and `data._load` hands each plist through whatever is registered for it as it is read, so an
  addition is seen by all twenty-two places that read the original's data without any of them knowing.
  **Additions only, never replacements**: `new_key` refuses a key the original already has, so what is in
  `game/` is theirs and what is in `additions.py` is ours, and changing a value the original set stays a
  divergence in the code that reads it, where it can be seen and written down here.  An addition that
  raises is logged and skipped rather than stopping the game from loading.  Sound is the limit: a new enemy
  or weapon that makes a noise needs recordings, and the engine finds those by name under `game/sounds/`,
  which is their folder - audible content would need a folder of the port's own and an engine that looks in
  both.  This is for data.

* PORT DIVERGENCE: Powered Power Ups says what it does (user request).  Its description reads "All Power
  Ups are fully levelled up for this game", and the card has never done that: `-[ADMinigunPowerUp preload]`
  0x1000b242c and the three like it read the inventory's level and add 1 when `level_<level+1>` exists, so
  a Minigun bought to level 1 is played at level 2, not at 4.  The sentence was wrong in the original for
  everyone below the top, and the port's fifth level (below) makes it wrong at the top as well, where the
  card now reaches a level no purchase can.  It reads "All Power Ups go up a level for this game, even
  beyond the top level you can buy."

  `data.REWORDED` is where that sentence lives, beside `TYPOS` and applied by the same `corrected()` as
  their data is read in, so every screen that shows the card gets it and `game/Tarot.plist` is untouched -
  a copy of the app given with `--game` is restated too.  It is a table of its own and not an entry in
  `TYPOS` because nothing in `TYPOS` is the port's doing: those are the original's own spelling mistakes,
  and this is a sentence the port made untrue.  It is the other half of the rule in `additions.py`: an
  addition may never replace what the original wrote, so a value the port does change is restated by name
  in one place, where it can be read beside the original's and found from here.

  `tools/verify_localization.py` now offers a translator both forms of any phrase a correction touches -
  as their file writes it, and as the game reads it in - because the corrected form is what the player is
  actually told and was invisible to the walk before.  All fifteen phrases `TYPOS` touches already had
  their corrected form in Russian; this one does not yet.

* PORT ADDITION: a fifth power-up level, which the Powered Power Ups tarot card is the only way to reach
  (user request, and the first content the port adds rather than restores).  The card said "All Power Ups
  are fully levelled up for this game" - restated since, see above - and `_levelDictionary` gives one
  level, and only when the data has
  a next one (`level_<level+1>`): a player who has bought every upgrade therefore gets nothing at all from
  it, while being told it is one of the best cards in the deck.  They keep it and play a run with one of
  their tarot slots empty.  `additions.FIFTH_POWER_UP_LEVEL` is what that player gets instead - the
  Minigun 15 seconds, the Fireworks 9 damage, the Tesla 5 kills, the Tornado 7 of reach - each carrying its
  own progression one step.

  It arrives through the overlay above, as a `level_5` on four of the `PowerUps` entries, so the original's
  own rule does the work and `_levelDictionary` is unchanged: one level up when `level_<level+1>` exists,
  which is now true once more than it was.  It cannot be bought, and not by accident either: the armory
  stops at four in three places of its own (`upgrade_button_pressed` tests `level > 3`, and two more test
  `level >= 4`), all of which read the inventory rather than this table.  `frequency` is deliberately absent: `resetPowerUpCooldown` 0x10004b640 reads its level straight
  from the inventory and not through `_levelDictionary`, so the card has never reached the cooldown, in
  the original or here.

* PORT ADDITION: key names are spoken as the keys people call them.  pygame's names for the two Enter keys
  are "return" and "enter", which read out as "Return or Enter" and sound like one key said twice; they are
  "Enter" and "Numpad Enter" here, the arrows are "Left Arrow" and so on, and space is "Spacebar".
* PORT ADDITION: the one defaults file is split three ways - `save.json` (progress: coins, diamonds,
  weapons, power-ups, missions, challenge data and the four stats blocks), `settings.json` (control scheme,
  button mode, sensitivity, menu arrows, cursor memory, tutorial text, the update check, a skipped update,
  the menu music volume, the announcer and the game's own gain) and `keys.json` (the key bindings, and the
  joystick later).  `announcer` and `masterGain` are the original's keys and went with the progress at
  first, being neither named in `SETTINGS_KEYS` nor new; they are settings, so they were named on 2026-09-24
  at the user's request.  A value already written to a player's `save.json` is left there and ignored, and
  both start at their defaults once - the announcer on, the gain 1.0 - which is what the user asked for
  rather than a migration.  The game reaches all three through one `UserDefaults.standard()`, which routes each key by name.
  the figure at 0x0d129c from everything before the first dot of the number's `stringValue`, so a weapon
  that has never been fired (`shotsHit` / `shotsFired` = 0 / 0, which is nan) is read out as
  "accuracy, nan percent", and a real figure is cut at the decimal point - 66.6 per cent announced as 66.
  The port speaks one decimal place, trimming a trailing zero, and says "not fired yet" when there are no
  shots to divide.
  sends `startMenuMusic:@"game_over_theme"` at 0x0db7f0 with nothing guarding it, but a recording of the
  real game has no theme at the death nor on the retry screen that follows: what is heard is that screen's
  own sting, a random `gameover_1..3` playlist started by `-[ADChallengeFailedViewController viewDidLoad]`
  0x100071718 at 0x071c90, and the menu theme only returns at the challenge selector.  Ruled out as the
  cause, read as listings rather than digests: `startMenuMusic:` 0x100082ca0 (neither early exit applies),
  `killGameplay` 0x10005c170 and its 0.1 s block, `playListWithName:` 0x1000fc050 (a cache, still returns
  the playlist after a deactivate), `activate:` 0x1000fe9c0 (skips only while already activating), the
  retry screen's own `viewDidLoad`, and all three callers of `stopMenuMusic`.  The mechanism is
  unidentified - most likely something in S3D's asynchronous activation on the device - so this one follows
  the recording rather than the line, and is the only divergence here that is not read off the binary.
  Pressing End Challenge never reaches `showDeathOverlay`, so that path was already silent.
* The status bar's coins and diamonds counters keep their spoken labels in step with the number on screen.
  `animateCoins:` 0x10001c728, `animateDiamonds:` 0x10001c850 and their timer methods 0x10001ca14 /
  0x10001cb68 only call `setText:`; the accessibility label is set once by `setCoinsLabel:` 0x10001d278 /
  `setDiamondsLabel:` 0x10001d394 and refreshed only by `refreshCoinsAndDiamonds` 0x10001c3d0, which the
  tarot screen never calls - so in the original a VoiceOver player hears the count from before the purchase
  until some other screen happens to refresh it, while the screen itself is right the whole time.
* A tarot card you pay to change is stored.  In the original only `-[ADTarotViewController
  loadCardWithNumber:]` 0x100035390 writes `tarotCardN`, and only when the key is missing;
  `changeCardButtonPressed:` 0x1000a62b8 and `changeCard` 0x1000a65a4 never touch it, so leaving the screen
  and coming back deals the stored card again and the diamonds are gone.  `change_card` now saves the new
  modifier under the same key.  Nothing else moves: `applyAllModifiers` 0x100035a5c still reads the live
  card, and `resetCardsModifiersIfNeeded` 0x1000d42a8 still clears all three keys after an endless game
  lasting over 60 seconds, so a fresh deal still follows a real run.
* DIVERGENCE: a second explosion makes the ringing last longer, and is heard (user request, found by
  playing it).  `startTinnitusWithDuration:gain:` 0x1000b6984 has two faults that only show when one blast
  lands while another is still ringing, which before Chain Reaction meant two Farties and was rare.

  It takes the new duration and gain whole and resets the timer, so a distant blast landing on a bad ring
  **shortens** it - thirteen seconds left becomes four - and quietens it with the same stroke.  The longer
  of the two and the louder of the two are kept now, so another explosion can only add to a ring.

  And it starts the sound only when no ring is running at all (`tinnitusDuration == 0.0`).  The recording
  is 14.1 s and a ring is at most 13 (`intensity * 10 + 3`), so one blast never outlasts its own sound; two
  do, and the second was extending the ring without restarting anything.  What that left was the reverb
  sitting on every enemy in the arena with nothing ringing over it - the effect with its cause gone.  The
  sound is started whenever it is not playing, which answers both cases.

  The ring **loops and adds up** (user request).  Rings add rather than replace - what is left of one plus
  what the new blast is worth, to `TINNITUS_MAX`, twenty seconds - because a crowd of exploding zombies
  would otherwise deafen a player for minutes, and because one blast can only ever manage thirteen.  The
  louder gain is still kept, so a distant blast lengthens a bad ring and never quietens it.

  And the recording loops, because a ring can now outrun its 14.1 seconds by some way.  That makes
  `stopTinnitus` 0x1000b6b4c stop the sound, where the original left it to run itself out - which it could
  do safely, its ring never outlasting one playing of the file.  What stops is already silent: the fade
  over the last fifth of a ring has taken the gain to nothing by then.

* PORT ADDITION: a diamond and a power-up do not go up with the rest (user request).  Chain Reaction says
  every Zombie explodes, and `DiamondDropper` and `PowerUpContainer` are `ADEnemy` underneath like
  everything else in the arena, so they were being lent a bomb too - and a diamond that blows up when it
  is shot takes away the thing a player shoots it for.  `Enemy.is_a_bystander` is the line: a passer-by or
  a diamond is not lent one.  The Machine and the Cars are bystanders and go on exploding, because their
  explosion is their own in `enemies.plist` rather than one a card lent them, and it is why a player
  shoots them.

* DIVERGENCE: a kill that did no damage is still heard (user request).  Almost everything that kills goes
  through `hitByWeapon:` or `hitByExplosion:`, and both schedule `playHitSoundForDamages:` 0x100062db8,
  which is where the death sound and any explosion are played.  The two Teslas do not: the tarot card's
  kill in `aggressive` 0x10005ffd4 and the power-up's `setLife:0` in `-[ADTeslaPowerUp update:]`
  0x1000d786c both end a zombie without hurting it, so all that could be heard was the zap.

  A Farty killed that way was the tell: `setLife:` calls `die`, `die` fires the blast, and the blast set
  the player's ears ringing with no bang anywhere to explain it.  `Enemy.heard_dying` is what both paths
  call now - the death sound, and the explosion if the enemy has one.  The Fireworks needed nothing:
  `hitByExplosion:` schedules the sound like any other damage.

* DIVERGENCE: an explosion is not cut off by the next one (user request).  An `S3DSound` owns one OpenAL
  source, so playing it again restarts it where it had got to.  A chain puts a zombie inside two blasts,
  so `playHitSoundForDamages:` runs twice for it, and the second call finds the first sound not yet
  playing - scheduled, not started - and plays the same voice again.  That is an explosion heard halfway
  and then cut.  `overlapping_voice_of` hands out a voice that is free instead, which is the port's own
  answer to exactly this and was already carrying the bullet impacts.

* PORT ADDITION / DIVERGENCE: everything adds in, with nothing left with nowhere to go (user request).
  Counting the cards was not enough on its own, because three things ran out or shut each other up.

  **The power-up levels go further than any hand can reach.**  Two cards can ask for two levels - Powered
  Power Ups in the level-1 deck, Emergency Supplies in the level-4 - and the data stopped at the one level
  the port had added, so a player at level 4 paid Emergency Supplies' ten seconds and got nothing for it:
  Powered Power Ups had already taken them as high as the data went.  `additions.extra_power_up_levels`
  carries each progression four levels past what can be bought, reading the step from the original's own
  last two levels rather than writing numbers down - the Minigun's 2.5 (10 to 12.5), the Fireworks' and the
  Tornado's 2, the Tesla's 1 - which reproduces exactly the hand-written `level_5` it replaced and goes on.
  The tiers past what a hand can reach are inert, and they are there so a card added later cannot quietly
  be given nothing.  `frequency` is still left out, its cooldown being read from the inventory.

  **A clip gains and loses.**  `Weapon.__init__` is an `if/elif`, so Golden Bullet silenced any card taking
  bullets away - and with four decks that is a real hand: Golden Bullet is in the level-3 deck and Hair
  Trigger in the level-4 one, so the card a player was told holds 10% fewer bullets held none fewer.  Each
  card takes its tenth of what is there now, up or down, and two opposite cards cancel out.

  **A revive for each card that offers one**, where `freeRevive` gave one however many asked.

  **The horde ramps once for each card**, `enragedHorde` being in two decks.  The game's own step past wave
  11 counts as one of them rather than another on top, so one card, or wave 12 with no card, is 0.14 exactly
  as the original has it, and two cards are 0.28.

* DIVERGENCE: two cards with the same effect do it twice (user request).  The original's modifiers are
  booleans, so `applyModifier:` 0x100035da4 setting `moreDamages` twice left it exactly as one card had -
  Military Grade Weapons in slot 3 and Heavy Artillery in slot 4 gave 10% more damage between them, not
  20, and Heavy Hands with Heavy Artillery slowed one reload rather than two.  With two decks that was
  impossible; with four it is common.  Measured: **24 flags can be set twice** and `moreHeadshots` three
  times, a hand holding one card from each deck.

  `GameModifiers.stacks` counts how many cards asked for each flag and `times()` reads it; the booleans
  stay beside it, because most of what reads them only asks whether a thing is on at all - the cows are
  in the arena or they are not - and because everything outside the class goes on working unchanged.  A
  flag set straight onto the object rather than dealt counts as one, which is what `--endless` and the
  tests expect.

  Every derived modifier is now the original's own arithmetic written as a base and a step, each reading
  exactly as the original did at one card: damage 1.0 +/- 0.1 a card, melee +/- 0.25, headshots +/- 0.5,
  spread +/- 5 degrees, reload +/- 0.2, enemy life -0.1 or +0.2, enemy speed +0.2 or -0.1.
  `reload_time_modifier` has a floor of 0.2 because it is a divisor and five slow cards would otherwise
  reach zero; the others have one at 0.1 for the same kind of reason.

  The effects that are not derived modifiers stack too: the coin multiplier is applied once a card,
  a clip gains or loses its tenth once a card, the power-up cooldown moves ten seconds a card, a
  power-up climbs a level a card as far as the data goes, Lucky Shot adds its chance a card up to
  certainty, and a Diamond Dropper pays a diamond for the full moon and one for each Lucky Night.

* PORT ADDITION: going back has a sound of its own (user request).  `back_button` is in the `buttons`
  playlist and on disk at `game/sounds/menu/buttons/back_button.m4a`, and **nothing in the original plays
  it**: `playSound` 0x100073578 and the five other copies of it all ask for `click_button`, so every
  button in the game makes the one noise, Back among them.  It is another recording the bundle ships and
  the game never reaches, like the tarot icons and the roulette.

  `play_back_click` is what plays it, and it belongs to going back rather than to a particular button:
  the Back button in the status bar, Escape and Backspace, and the armory's two Close buttons, which are
  `backButtonPressed` reached another way and would otherwise have disagreed with Escape on the same
  screen.  Back is built with `font_button=False` so the general click is not added on top of it.

  Escape is unchanged in when it sounds: `accessibilityPerformEscape` answers False on a screen with
  nowhere to go - the main menu among them - and nothing is heard, which is how a player can tell.

* PORT ADDITION: Chain Reaction and Damp Squib - every zombie carries a bomb, or the Farties lose theirs
  (user request).  Whether an enemy explodes is a key in `enemies.plist`, and only six things have one:
  Farty, FartyB, Machine and the three Cars, all with the same block - radius 3, 50 damage, dispersal 75.
  `Enemy.blast` is what everything asks now, and it answers with the enemy's own, or with
  `modifiers.CHAIN_REACTION_BLAST` - the same numbers - when Chain Reaction has lent one, or with nothing
  when Damp Squib has taken the Farties' away.  Machine and the Cars keep theirs under Damp Squib: they are
  things a player shoots on purpose to stop a noise, and taking the blast away takes the point away.

  **The cascade is the original's own and needed nothing.**  `solveExplosionWithDictionary:` 0x1000c5c40
  damages everything inside the radius and then calls `checkDeathsForHitEnemies`, so a neighbour killed by
  a blast and carrying one of its own goes off in turn, and that runs as far as the crowd reaches.
  Measured: six zombies a unit apart, kill the first and all six die; the same six without the card and
  only the one that was shot; ten units apart and the blast reaches nobody.  The ringing ears are the
  original's too - a blast inside 5 units starts tinnitus, its intensity scaled by how close it was.

  What did need writing was the bang.  `playHitSoundForDamages:` 0x100062db8 plays an explosion from the
  dying enemy's own playlist, and a zombie has none - only the Farties and the Cars were ever given one -
  so the damage would have been silent, which in this game is damage nobody can play around.  The
  **Farty's** explosion is borrowed when an enemy has none of its own (`Farty_explosion_SPA`): the
  grenade's was used first and the Farty's is the right one (user request), being what this game already
  means by a body going off rather than by a weapon.  Either way it is a recording already in `game/` and
  already spatialised, and `ADEnemy` reaches into another playlist by name for the Tesla kill the same way.

* PORT ADDITION: a card is not there until its own flip has been heard (user request).  The deal is a
  sound per card, and the cursor now reaches exactly the cards that sound has brought in: before the
  first flip there is nothing to arrow onto, after the second there are two, whatever the hand will hold.
  `reading_order` skips an element that is not `accessible`, so an undealt card is not something to pass
  over - it is not there.  `TarotCardViewController.reveal` is what the flip calls
  (`TarotScreen._deal_card`), and `_cards_dealt` reveals whatever is left as a backstop.

  A card that has arrived is still dimmed until the whole deal is over, so it can be read and cannot be
  paid to change - which is the state Back, Armory and Play are in for those same seconds.

* PORT ADDITION: a shuffle flips once for each card it deals, and reads them out after the last of them
  (user request).  Two locked cards are two sounds, so what a player hears is how many cards moved;
  `SHUFFLE_FLIP_GAP` is the half second between them.  Nothing is spoken until they have all landed,
  because a card read out while another is still arriving is a card read over, and finding out what came
  back is the whole reason for paying.  The button is dimmed while a shuffle lands (`shuffling`) so a
  second press cannot be paid for on top of the first.

* PORT ADDITION: a shuffle rolls for the last slot again, not only for what is in it (user request).
  The slot is a chance, so a hand can come back from a shuffle without it - as though it had never been
  dealt one - and a hand of three can come back with it.  Measured over 60 shuffles of a four-card hand:
  ten lost the fourth card and nine gained one back.

  Nothing says so out loud.  The flips do: one sounds for each card the shuffle deals, so a four-card hand
  answering with a single flip has lost its fourth and a three-card hand answering with two has gained
  one.  That is the language the deal already speaks, and it is why this needed no new sentence.

  What it did need was for the hand to stop being a fixed size.  `place_cards` replaces the placing that
  0x100035390 did one card at a time: the spacing is a function of the count, so a card arriving or leaving
  moves the rest, and both have to be able to happen after the deal.  `load_card_with_number` takes
  `dealing=False` for a card a shuffle brings in - revealed and live at once, with no flip of the deal's
  own scheduled for it - and `drop_card_with_number` takes one out of the hand, the container and the
  defaults together.

  The announcement was cut back with it.  A card read out after being changed is now the title and the
  description and nothing else (`accessible_description(with_action=False)`): what the cursor would say
  also carries the price of changing it again, the diamonds in the purse and the word "button", none of
  which is what somebody who has just paid wants to hear.

  And a shuffle says the cards in **one** utterance (`announce_cards`).  `Screen.speak` interrupts by
  default, so a call per card cut every card but the last off mid-sentence: a shuffle that dealt cards 3
  and 4 read out only card 4, which is what it did until it was played (user request).  They are joined
  now, each still naming its own slot, so what is heard is the whole hand that moved.

* PORT ADDITION: a Shuffle button, for the cards that cannot be changed one at a time (user request).
  It deals every locked slot again at once - card 3, and card 4 on a hand that has one - at random, and
  what comes back may be worse than what went.  That is the point: the locked cards are there so a hand
  holds something nobody chose, and a way to pay for a *particular* card would undo them.  This is the way
  out of a hand that has gone wrong, not a shop.

  It costs both currencies, `SHUFFLE_DIAMONDS` and `SHUFFLE_COINS` - 3 and 2500 - because they are earned
  differently.  Diamonds are scarce, about twenty a run, so they are the real price; coins are not, twelve
  thousand in a long run, so they are what makes it sting before a player has a bank.  Three diamonds is
  what changing the first card costs, the dearest single change the original sells.  Short of either and
  the matching alert goes up and nothing is dealt or taken; `--free-cards` makes it free like the rest.

  The button sits after the cards and before Play, which its frame decides rather than its order in the
  file: `reading_order` sorts by the vertical centre of a frame, and 255 falls between the cards' 180 and
  Play's 302.  Its label says how many cards it would deal - one or two - and its hint carries the price
  and what the player has, rebuilt on the way into the screen as the cards' own hints are, because the
  armory opens over this screen and a number read from before a purchase is a number that lies.  It is
  dimmed while the cards are dealt and comes alive with Play, as they do, and
  `shuffle_button_pressed` returns while `dealing` so no path round it reaches the money.  Both wordings
  of the label are written out rather than built with a `%s`, so `verify_localization` can see them.

* PORT ADDITION: the last card is a chance, not a fixture (user request).  A quarter of hands are dealt
  one; the rest hold three.  That is what the level-4 deck is for - a card worth reading because it is not
  there every time - and it is why those cards can be as strong and as costly as they are.
  `tarot.LAST_CARD_CHANCE` is the number, and rarer reads better on paper than in play: the deck has
  twelve cards, and at one hand in ten a player would meet one for the first time after an evening of runs
  with no idea what it was about to do to them.

  The roll is made once and kept, under `tarot.HAND_SIZE_KEY` beside the cards themselves.  It has to be:
  the armory opens over this screen and the player comes back to it, and a hand that rolled its size again
  each time would gain and lose a card under them.  `resetCardsModifiersIfNeeded` clears the key with the
  cards, so the next game rolls its own.  The original has no key for this because it always dealt two.

  A three-card hand is laid out by the original's own spacing, gaps of exactly 10 points, because that
  formula only goes negative at four.

* PORT ADDITION: **Play, Extra** - challenges the port wrote itself - and the first of them, Powder Keg
  (user request).  It was a tarot card for a day; the idea outgrew a card.  Chain Reaction and Damp Squib
  went back to the level-2 deck, whose subject is what the Zombies do, and the tarot is four slots again.

  Almost none of it is code, because a ring turns out to be a **wave**.  `spawn_angle` and
  `spawn_distance` have always meant what they say, so ten zombies at one distance and even angles is a
  circle, and the engine's own machinery does the rest: it activates the playlists a wave names, so a ring
  of four kinds is four kinds a player can hear without anything being loaded on the fly; and it moves on
  when a wave is cleared, which is what makes three rings and three crowds a challenge of six waves.  The
  first shape of this was a manager spawning zombies into a live wave (`spawner.py`), and it is gone: a
  wave was always the right shape, and the risk it was written to dodge - a zombie whose sounds are not
  loaded - was a risk only because it was fighting the engine instead of using it.

  Two keys are the whole of the code.  A wave with `Rigged` gives every zombie in it the blast the game
  gives a Farty, so one shot takes the ring in the original's own chain; a wave with `NoBlast` promises
  the opposite whatever cards are in hand, which is what the crowd between the rings is for.  Their own
  waves have neither key and are untouched.

  `additions.PLISTS` is where the challenge and its six waves live: whole files the original does not
  have, rather than additions to files it does.  `data._load` falls back to it when the bundle has nothing
  by that name, so `dictionary_for_challenge_with_name` 0x1000810c8 finds a challenge of the port's by
  name exactly as it finds one of theirs, and every screen that reads the game's data reads these too.

  The menu is built like the play menu rather than like the challenge selector, which is a table of worlds
  and stars and locks that these are not part of: one button a challenge, Back to Play.  The Extra button
  sits after Endless on the play menu, which its frame decides - `reading_order` sorts by a frame's
  vertical centre.

  A challenge of the port's is shown before it is played, as the selector shows the original's (user
  request).  `Accessible_ADChallengeOverviewViewController` 0x1000d8178 takes a challenge dictionary and
  reads out its title, its objective, its tip and its three stars with Play at the bottom, and tells a
  player who has not bought one of its guns to go and buy it.  A dictionary is all it wants, so the
  port's own get every bit of that for nothing.  The accessible one is used whether a screen reader is
  running or not: the sighted overview is a nib nobody ported, so asking for it hands back a placeholder
  and a dead end.

  The three rings get worse and the challenge can still be finished (user request).  A ring is cleared by
  one kill whatever is standing in it, the chain doing the rest, so what makes a ring hard is not how
  tough it is but **how long the first kill takes while the other eleven close in** - which is why the
  last ring holds a Hulk at 100 life and the player's job is to pick the soft one by ear.  No ring holds
  a Runner: 1.3 speed from three units is not a puzzle.  The crowds are the opposite, everything in them
  having to be killed, so that is where the Runners go, and they walk in one at a time.  Ten at 3.5
  units, twelve at 3.2, twelve at 3.0, which is as near as a ring can stand and still leave a moment to
  choose; crowds of five, seven and nine at ten, nine and eight.  The guns are a pistol that never runs
  dry, a Micro SMG with 200 rounds and a wok - the pistol is what makes it finishable however badly it
  goes, and there is no shotgun because a ring is a target a shotgun cannot miss.

  Belonging to no world is what the rest of the game had to be told.  `challengeAfter:world:` 0x10001f52c
  looks a challenge up in its world's list and returns the next one, taking `NSNotFound + 1` wrapping to 0
  as "then the first"; for a challenge in no world the list comes back empty and `challenges[0]` runs off
  the end of it, which a player found by pressing Next challenge after Powder Keg.  `hasChallengeAfter:`
  0x10001f230 answers False for the port's own now, and for any world with no challenges at all - the
  same crash reached another way, and one that was there before any of this.  The button says "back to
  Extra" and goes there, since "next arena" would be a lie about a challenge in no arena; the overview's
  own Back goes the same way for the same reason.  Since 2026-09-29 (user request) a chapter is walked as a
  world is: Next challenge opens the arena after it in its chapter (`additions.arena_after`), or the
  chapter's list when that one wants a gun not bought, as the original falls back to its challenge list;
  and the last arena of a chapter says "Chapter selection" - named for where it leads, as Challenge
  selection is (it said "next chapter" for an hour, until the user asked) - and goes to the Extra screen,
  as the last of a world says "next arena" and goes to the world list (`App.go_to_challenge_after`
  0x100081c70).  Copy results on
  an Extra arena's completed or failed screen opens "Audio Defence Extra Challenge Statistics" (user
  request, the same day), so a paste of one is not taken for one of the original's challenges.

  Three more screens had to be told the same thing, and were not until a player found them.  Every screen
  behind a challenge goes back to its list through `goToChallengeSelector` 0x1000816e0, which opens the
  challenge list of `lastChallengeWorld` - and an arena of the port's belongs to no world, so it never sets
  that.  The list for no world holds nothing: `challenges_index[None]` is absent, `challenge_files` is
  empty, and the screen that appears is the challenge selector with no rows in it at all.  It is the one
  screen of that walk that turns the coins and the diamonds **on**
  (`Accessible_ADChallengeSelectorViewController` viewDidLoad 0x10005419c), so what a player got was a
  screen holding nothing but the money, whose own Back went out to the world list.  Reported as "I can see
  nothing except the dymonds and coins... it bring me to the original challenge screen instead of extra
  challenge menu".

  The overview's Back had been taught this; the failed screen's Select challenge
  (`missionSelectButtonPressed` 0x100071e1c), the completed screen's Select challenge (0x100068f64) and the
  completed screen's Back (0x100048728) had not - so it was reached by finishing an arena or failing one,
  which is the ordinary way out of every arena and the way nobody had walked.  All four ask
  `App.go_to_challenge_list_for` now, one place that knows which list a challenge came from, rather than
  four copies of the test.

  Six more arenas, and the seven of them locked in a chain (user request), which is chapter 1.  Each names
  the one before it in `challenges_requirement` - the original's own key, read by
  `hasChallengeRequirementsForChallengeWithName:` 0x10001ffbc - so the locking needed no code.  The Extra
  menu reads each button's status out of `statusForChallengeWithDict:` 0x100054960, the selector's own:
  `locked`, or how many of its three stars are won.  A locked button does nothing and says nothing when
  pressed, which is what the selector's locked rows do.  What is drawn stays the title and what is read is
  the title and the status, because on that screen there is nothing else to say it.

  **They were all built wrong the first time**, and the way they were wrong is worth writing down, because
  it is a trap the shape of this game sets.  They were sized by eye, against how much life a wave held -
  and life is very nearly irrelevant here.  There is no health in this game: `-[ADEnemy update:]` walks an
  enemy in at `speed` until it is three units out, closes at `agressiveSpeed`, and `attack` 0x100060304
  posts PLAYER_DIED, so **one enemy arriving is the whole game**.  What decides a wave is therefore not its
  total life but whether every enemy in it can be killed before its own clock runs out, with the clock of
  the one behind it already running - and the only thing that makes a wave get harder as it goes is
  enemies arriving *faster than they can be killed*.  A revolver sustains 16.7 damage a second at level one
  once its reloads are counted, so a Zombie is 2.9 seconds; a crowd walking in every four seconds never
  builds pressure at all, however many of them there are.  Every one of the first six arenas staggered its
  waves more widely than that.

  Two of them were broken outright.  **Three Bullets** could not be lost: three rigged rings and
  `alwaysCritical`, so firing in any direction whatsoever cleared a wave, and after the first shot of each
  nothing in the arena could reach the player at all.  **Powder Keg** could not be won: its third ring
  cycled Hulks into the circle, and 100 life survives a chain that does 37.5, so four of them were left
  standing three units from the player with four seconds to live.  Neither is visible by reading the data;
  both are obvious the moment it is measured.

  So `tools/arena_pressure.py` measures it.  It gives every enemy a deadline, sorts a wave by deadline,
  and asks whether the guns the challenge hands out can have killed the first *n* of them by the *n*th -
  printing the slack at the tightest moment.  It simulates the chain properly (`hit_by_explosion`
  0x100061284: dispersal 75 means a fixed 37.5 plus a falloff, so everything soft inside a ring dies and
  everything tough merely flinches), it reads a challenge's own `Modifiers`, and it carries two numbers
  that are judgement rather than disassembly and are labelled as such: `DEAF_COST`, because the game gives
  tinnitus no mechanical effect and it is the player it disables, and `MELEE_COST`, because a wok reaches
  three units and a swing that misses is the end of the run rather than a lost second.

  Both chapters are tuned to a deliberate curve of that number and ordered by it **across the pair rather
  than within each** (user request), so the thirteen arenas fall from fifteen seconds of slack to eleven
  seconds short in one line and the first arena of chapter 2 carries on from the last of chapter 1.  Short is
  not impossible - the tool counts only the gun, where a player also has a wok worth 25 a swing, headshots,
  and whatever they have spent diamonds on; at level four the hardest of them come out to the good.

  Which arena sits in which chapter therefore follows from the measuring and not from when it was written.
  Chapter 1 took the easiest seven, which is also every arena a player already owns the guns for; chapter 2
  took the six where the slack has run out, and Powder Keg went with them - it was chapter 1's finale while
  chapter 1 was all there was, and by the numbers it belongs fourth from the end of the whole thing.

  The chain and the rewards are worked out from that order (`_derive_order`) rather than written into each
  arena.  They are facts about the order and nothing else, and while they were written by hand they were
  wrong twice: once with an arena pointing two places back at itself, once with the rewards climbing inside
  each chapter but not across the pair.

  What each of them is for.  **Barnyard** is listening: three cows walk through every wave and a jukebox
  plays in the last, and its constraint is not the clock but forty-two rounds against four hundred of life,
  so a cow shot is a kill given away.  **The Wall** is reload discipline - a Hulk has 100 life and a
  cylinder holds six rounds, so every one of them has to be reloaded through, and the Riot Gear Zombie
  stops dead for five seconds whenever it is hit (`protect` 0x10005ff4c), which delays itself while the
  Hulks walk on past.  **Clockwork** is anticipation: the same four bearings on a beat that tightens to
  1.9 seconds, which is faster than a Zombie can be killed.  **The Survivor** is fighting deaf - the ring
  is free and is meant to be, and what it costs is twenty seconds of hearing while eight more walk in.
  **Stampede** is everything that runs, played with `fasterEnemies`.  **Powder Keg** is all of it at once
  and closes the chapter.

  **Three Bullets** is the one the tool cannot rank, and it is placed by judgement - fourth of the thirteen -
  with the reason written here.  Ted, Jim and Bob are zombies with the whole sound set - spawn, approach, aggressive, hit,
  death - and a speed of 0: they stand where they spawn and never come.  So the wok cannot touch them
  (reach 3), `brickIsCleared` 0x1000a1658 will not pass a wave until they are dead.  The three are Bob,
  who has 1 life, since 2026-09-30; they were Ted and Jim, with 10, on the belief that 10 was one revolver
  round at level one.  It is not: the revolver's `dispersal` is 90, so a level one round does 9 and a
  fraction anywhere but at the muzzle, and only a hit inside its ten-degree `criticalSpread` (x1.3) or a
  critical made 10 - a round a few degrees off left the dummy on under one life and the wave with no way
  to end.  Three of them, three rounds, no modifier holding it up - and everything else in the arena walks
  and has to be met at arm's length, because there is nothing left to shoot it with.  Its difficulty is categorical rather than
  arithmetic: what the tool cannot price is that a melee duel with no health is the frightening thing in
  this game.  (It used to measure the wok at 25 damage a second as though a swing reached ten units, and
  called the arena comfortable; priced as a weapon that reaches three, since 2026-09-28, it puts it a second
  below Scrapyard, which follows it - and Scrapyard's sixty rounds are two hundred damage short of its
  zombies, which the margin does not count at all.  So it stays where judgement put it.)

  Three rounds and not one spare means a wasted round leaves a wave that can never be cleared, with the
  arena gone quiet and nothing arriving - which for a player with no screen is the worst thing a design can
  do.  There is no fail-on-time in this game to rescue it (`time_limit_star` is a star, not a limit), and a
  static enemy cannot be given a speed from a wave entry, so the tip says it plainly: if it goes quiet and
  will not end, a round went somewhere it should not have, so end the challenge and start again.

  None of the seven says what it wants (user request).  An objective is what a player can hear and a tip is
  a nudge, and the thing to be worked out is left to be worked out.  Powder Keg's own was rewritten to
  match: it used to say the Zombies were rigged and that one kill took the ring, which is the whole of the
  puzzle given away in the first sentence a player hears.

  **Chapters** (user request), and a chapter opens on stars as one of their worlds does.  Extra is a list
  of chapters now and each chapter a list of arenas, which is one screen more than before and the shape
  the original uses for worlds; inside a chapter the arenas still unlock one behind the next.

  They are the port's own structure (`additions.CHAPTERS`) and deliberately **not** worlds in
  `challenges_index`, which they could have been - `apply_to` reaches that file, and their world list would
  have given the locks, the star counting and a "you need N stars" row for nothing.  It would also have
  changed Somethin' Else's game.  `totalStarsUnlocked` 0x10001ecd4 sums every world in that file and is
  what gates theirs, and City Crossroad opens at 25 stars with Maya Ruin at 40 - so twenty-one stars' worth
  of arenas of ours would have opened worlds the player had never touched.  Counting on this side
  (`ChallengeData.stars_unlocked_for_chapter` and the three beside it) costs a screen and a few lines, and
  a test asserts the thing that matters: with all seven arenas beaten and 21 stars won,
  `total_stars_unlocked` is still 0.

  Everything behind an arena now goes back to the arena's own chapter rather than to Extra -
  `App.go_to_challenge_list_for` asks `chapter_of` - and the completed screen's button says which one, "back
  to Chapter 1".

  **Chapter 2** (user request), six arenas built out of the parts of this engine chapter 1 never touched,
  written as six arenas of its own and then sorted in with the rest.  At level four its hardest comes out
  twelve seconds to the good, which is the point: chapter 2 is entered by a player who has been playing.

  It opens on stars alone, as one of their worlds opens (user request): every star won in the port's arenas
  counts, whichever chapter it was won in (`ChallengeData.chapter_is_open`), and a chapter asks for every
  star the chapters before it hold **but two** (`SPARE_STARS`, user request) - 19 of 21 here, 37 of 39 for
  chapter 3, 55 of 57 for chapter 4, and the same rule for any chapter added after, since the number is
  worked out from the chapters and not written down (`chapter_stars_required`).  Two is less than the three
  an arena is worth, so no arena can be skipped on the way; what may be missed is two accuracy or time stars
  across everything behind you.  It stays two rather than shrinking, because at nought one star a player
  cannot win would shut every chapter after it for good.

  How it got there, all on 2026-09-28 and all asked for: first every arena of the chapter before had to be
  beaten *and* a lower count of stars won, and a locked chapter said which of the two was missing ("1 arena
  still to beat before this chapter", "5 more stars needed"); then stars alone, as their worlds do, at 12,
  26 and 40; then the counts raised to these, because at 12 a player could walk into chapter 2 with a third
  of chapter 1 unplayed.  A locked chapter reads as a locked world in their world list reads - "Chapter 2,
  You need 19 stars to play this level" - which is their own line, so a language file that has it
  translates it already.  Two of the six turned out to belong
  in chapter 1 once they were measured (Scrapyard and Do Not Wake It), and Powder Keg came the other way.

  **Scrapyard** is an economy.  A Car keeps its own explosion from `enemies.plist` - radius 3, 30 damage,
  dispersal 50, which `hit_by_explosion` makes 15 flat plus 15 falling off inside one unit - so it kills
  nothing outright and takes 15 off everything within three units.  Against sixty rounds and 815 of life,
  the question is whether the zombies walking past are worth what the car costs to set off.  The cars go in
  as `PasserBy` and not as enemies, which is where the game puts them and the only place they work:
  `sounds/passerBy/Car` holds an alarm, a spawn, an impact and a death and **no `_approach_`**, so a Car
  driven by the enemy state machine falls silent the moment it finishes spawning - an inaudible thing that
  `brickIsCleared` would still wait for, which is the dead end Three Bullets had to be written around.  As a
  passer-by, `CarAlarm` loops the alarm so it can be found, it can still be shot, it still explodes, and it
  holds nothing up if a player decides it is not worth a round.

  **Do Not Wake It** is the only arena in either chapter where the right move is sometimes not to shoot.
  Everything about a Berserk runs backwards: 225 life, and in its walking state the orientation is negated so
  it walks *away*, and `berserk_go_away` 0x100060944 sets its life to nought once `disappearAfter` is up - so
  the wave counts it as cleared and no shot was ever fired.  But `hit_by_weapon` sends it to
  `transition_to_berserk` the moment it is hit and survives, and it comes back at `berserkSpeed` with
  whatever is left of 225, which at level one is thirteen seconds of shooting it does not give you.  The
  Berserks stand on bearings between the zombies that do have to die, close enough that a shot thirty degrees
  wide might find the wrong one.

  **Sidestep** is a target that will not stay found.  `dodge` {dodgeTime 0.7, dodgeSpeed 5} fires from
  `hit_by_weapon` every time a Dodge is hit and survives, and it strafes **3.5 units** - measured, not
  assumed - at random to one side, which at ten units out is nineteen degrees.  (This said "and so outside
  the revolver's spread of thirty" until 2026-09-28, which is wrong: `calculateHitEnemies` 0x1000c41c4
  measures `spread` either side of the aim, so the revolver reaches thirty degrees each way and one strafe is
  still inside it.  It is outside the ten either side where a hit is lined up, and two the same way are
  outside both.)  Eight rounds at level one is being found again near enough eight times, while it closes at
  0.9 and the walkers behind it do not wait.  The tool charges `DODGE_COST` of overhead per hit for that.

  **Hydra** hands the player the timer.  `spawn_after` is the original's own key (`challenge_arena1_1` uses
  it) and `checkSpawnAfterKill:` 0x1000a20ac reads it: an enemy spawns so many seconds after the one it names
  **dies**.  So heads stand out there with more waiting behind each, and nothing happens at all until one is
  cut off - kill them one at a time and the clock runs out, kill them together and they all come back at
  once.  An enemy with a `spawn_after` and no `spawn_time` is built and then left in the state it was born
  in, which a test confirms: thirty seconds pass and the brood has not moved.  Since 2026-09-28 what grows
  back grows back closer, two seconds after the cut, and some of it has heads of its own (`_heads`, a tree),
  because measured properly the first version was a chapter 1 arena - see the second correction to the tool
  below.

  **The Long Walk** is 500 life at a quarter of a unit a second - forty-eight seconds to arrive and thirty
  seconds of level-one shooting to put down - and the arena is what walks in behind the player during those
  thirty seconds.  **Big Game** closes the chapter and is the first arena of either that names a gun the
  player has to buy (user request): `hasWeaponForChallengeWithName:` 0x10001f868 is what the overview checks,
  and a player without a Hunting Rifle is told to go to the armory rather than let in.

* FIX to a PORT ADDITION: `NoBlast` used to throw away an enemy's **own** explosion as well as refusing it
  the one Chain Reaction lends.  It was written for the crowds between Powder Keg's rings, and those crowds
  contain Farties - whose bang is theirs out of `enemies.plist` and the reason a player is glad to hear one -
  so the Farties in Powder Keg had been silent since the day the key was added.  `blast` answers with the
  enemy's own explosion first and only then consults the flag, so setting the flag alone says exactly what
  was meant, and the key now leaves an enemy's own explosion alone.

  **Chapter 3** (user request: harder again), six arenas on the last levers the engine had, opening on
  thirty-seven of the thirty-nine stars the chapters before it hold.  It runs from thirteen
  seconds short to twenty-five, which carries straight on from Big Game's twelve; at level four the same six
  come out between five short and eleven to the good, which is what a chapter reached with thirty-seven stars
  should feel like.

  **Iron Sights** narrows the cone.  `spread_modifier` is five degrees a card and `Weapon.__init__` adds it
  to the weapon's own, so `narrowedSpread` twice takes the revolver from thirty degrees to twenty - a third
  less arena to find a zombie in by ear - and `noCritical` removes the doubling on top, so a shot lined up
  perfectly is worth no more than one that merely landed.  **Thunder** is the storm, which is the original's
  own idea: `maya_2`, "A storm is coming!", whose tip says plainly that it is hard to hear zombies through
  one.  Naming `ambient_storm` as the arena's ambient is the whole of it - `startWithambient:gain:`
  0x100098004 starts the storm playlist on that name alone, with no modifier set, and stops the random scare
  sounds while it runs - so nothing in that arena is hard to kill and all of it is hard to place.  **Rust**
  is the gun itself: `rustyWeapons` to jam it, `lessBullets` twice to take the cylinder from six rounds to
  four, and `slowerReloadTime` twice to make the 1.8 second reload two and a half, which between them drop
  the revolver's sustained damage from 16.7 a second to 9.5.  **The Drop** counts the rounds short on purpose
  and hands over a power-up instead: `PowerUp` {force_spawn_time, type} is the original's own key, and
  `forceToPopPowerUpContainerWithType:` 0x1000c7b68 puts a container on a random bearing five units out with
  one life on it, to be found and shot in the middle of everything else.  **Carousel** is the ones that do
  not come at you, and **The Last Word** is all of it in a storm with `strongerEnemies`.

  What chapter 3 cannot have is Dr. Bastard.  `Brick.init_sounds` asks the engine for a playlist named after
  the brick (`play_list_with_name(self.name)`), and all ninety-two of those belong to their challenges, each
  with a folder of its own under `game/sounds/challenges/`.  A brick of ours has no playlist and no folder,
  so a `Sounds` entry on one would load nothing at all - `brickIsCleared`'s guard keeps that from hanging the
  wave, but the line would never be heard.  Their arenas talk; ours cannot, without putting recordings into
  their data.

  **Chapter 4** (user request: harder again, and built on the weapons no arena had used yet), six arenas
  each fought with a weapon from the armory and built against what that weapon is bad at.  It opens on
  fifty-five of the fifty-seven stars the chapters before it hold, and by the tool's
  crowd-weapon reckoning (`area_pressure`, see the second correction to the tool below) it runs from 27.7
  seconds short to 39.8, carrying on from The Last Word's 25.6.  It is the steepest chapter so far and the
  one the tool is surest to overstate: it counts no critical hits, and the Sawn-off's are two and a half
  times at thirty per cent inside fifteen degrees.

  **Point Blank** is the Sawn-off, whose `dispersal` of 1 makes its damage almost all distance - 5 at ten
  units, 21 at six, 28 at three (`hit_by_weapon` 0x100060b30) - so the arena is waiting, and every wave is
  packs.  **One Swing** is the Claymore, 70 a swing and two and a half seconds between swings, during which
  `isWeaponReadyToShoot` 0x1000aa350 will not let the revolver fire either; nothing in it but arrivals, closer
  together each wave.  **Fuse** is the Grenade Launcher, which `targetEnemiForExplosiveWeapon:` 0x1000c57b8
  aims at the **nearest** thing in front of the player rather than the one meant, and which rings the ears
  inside five units - so every pack walks in behind something that got there first, a little to one side.
  **Collateral** is what a blast does not do: `hit_by_explosion` 0x100061284 wakes no Berserk, sends no
  Dodge sideways and never asks whether a shield is up, and every pack there escorts one of the three in the
  middle, where a revolver aimed at the pack's sound finds it first.  **Crossfire** is the Sawn-off against
  two packs at once from opposite sides - its cone is sixty degrees each way and never the half behind -
  with the Hunting Rifle for whichever has to wait.  **The Armory** is all three of the chapter's weapons.
  A Colossus was in its first draft and came out: five hundred life is twelve direct grenades or twenty-four
  shells, which none of those weapons is for.

  Three weapons have to be bought, and `hasWeaponForChallengeWithName:` 0x10001f868 sends a player without
  one to the armory as it does for the original's own challenges.  The Sawn-off is one the original's Roman
  Theater makes a player buy anyway; the Grenade Launcher and the Claymore are the chapter's price.  The
  Bazooka, the Police Shotgun, the Machine Gun and the Sonic Cannon are left out: between them they cost
  more than eighty thousand coins and a hundred diamonds, which is a bill rather than a challenge.

  Its waves are bigger than anything the original sends - its largest is fifteen, and some of these are
  forty - and every enemy of the port's holds its own voices (`voice_of`), so the busiest were played in the
  real engine with the listener silenced before being kept: 84 voices at once at the most, against the 255
  mono sources `Device` asks for, and none refused.

  The Extra info page was rewritten with it (user request): it says plainly that these arenas are not the
  original game's, and otherwise says as little as it can - none of them tells you how it is won, one opens
  the next, and stars open another chapter - since what an arena wants is the arena's to be found out.

  One Swing was given a little room after it was played (user request, 2026-09-29): "sometimes passable,
  usually not".  Its last wave sends a Runner, a Hulk, a Chainsaw and a second Runner in turn, and a Hulk
  does not walk until its arrival roar ends, which is one of two recordings, 3.7 or 5.7 seconds long.  So
  it came into reach anywhere in the two seconds the second Runner was arriving in, with the Chainsaw a
  second and a half behind: three inside one swing of the Claymore, won or lost on which roar was played.
  The second Runner of each group now walks in three and a half seconds after its place in the crowd, which
  puts it after the Chainsaw; two seconds would have put it on the Chainsaw instead.  Played out a few
  thousand times with the game's own movement and both lengths of every recording, a player a second slow
  on each enemy lost wave 3 in four runs of ten before and in none after, with under a second to spare at
  its worst moment.  Nothing else in the arena changed - not its bullets, and not wave 2, whose Runner and
  Chainsaw a second apart the player gets through.  The tool's line for it does not move, since it never saw
  the pile-up (the third correction to it, below).

  Fuse's single walkers are ordinary Zombies (user request, the same day).  Each crowd there comes in behind
  one enemy seven units out, a little to one side, which the grenade goes to instead of the crowd, since
  `targetEnemiForExplosiveWeapon:` 0x1000c57b8 takes the nearest thing in its cone - and the Grenade Launcher
  has no `criticalSpread`, so no aim picks the crowd over it.  The answer is to hear the near one and use
  the revolver on it first.  They were Quiet Zombies, and a Quiet Zombie's walking recordings measure
  25 dB under a Zombie's (-46 against -21 RMS), a whisper beside a crowd: the thing taking the grenade could
  not be heard, which the player found in play.  Five of them are ZombieB and ZombieC now, the voices the
  crowds already have; the Quiet Zombies inside crowds stay, since they die with the crowd.  The tool reads
  the arena as harder afterwards (level 1, 30.4 seconds short to 36.6), which it is not: it hears every
  enemy perfectly, so it never priced the whisper, and the later arrival of a Zombie's longer spawn sound
  shifts where its grenades land against its judgement of deafness.  Fuse keeps its place.

  And then, still too many at once (user request, the same day), Fuse's last wave lost its second Hulk pair.
  Of the six crowds in that wave, taking out each in turn, that pair gave the most back at level 4 (a Hulk
  is a hundred of life, three or four grenades), and the wave went from 36.6 seconds short to 27.6 at
  level 1, level with Point Blank and a shade inside One Swing - close enough, on a tool that cannot hear
  what the player is listening for, to leave the chapter's order alone.  Taking the revolver out, so the
  arena was grenades and the wok alone, was put to the player and turned down: they want the gun, and the
  answer to the near one is theirs to find.  The tip hints at it now - "The near one is not worth a
  grenade." - without saying what is.

  Still too many, the player said, and the weapons not strong enough for them - and no gun there kills a
  Zombie at seven units in one: the revolver takes three, the Hunting Rifle two, the Sawn-off two.  So the
  crowds of waves 2 and 3 are weak ones round an ordinary Zombie that walks in the middle half a unit ahead
  (`_escort`).  A blast is 30 to everything within five units and a WeakZombie has 20; the Zombie is always
  the nearest thing in the crowd, so it is where the grenade goes and it takes the whole blast, up to 60.
  One grenade on target is a crowd.  Checked against every arrival recording's length: at the worst, a weak
  one still walks 0.18 units behind its Zombie, and every one of them stands within about 2.6 units of it -
  inside the blast even with the aim ten degrees out.  The Quiet Zombies left in crowds went with it.  The
  Runners, the Hulk pair and the near ones are as they were.  The tool barely moves (level 4: 13.3 and 15.7
  seconds short to 2.1 and 16.7), because it prices an explosive as though it never lands on the toughest
  thing in a pack - which here it always does.

  And the Hulk pair walked in behind a near one of its own, so it could not be grenaded until that one was
  dead - while the Runners were coming (user, the same day).  The pair has no near one now, so it can be
  grenaded as it roars, eleven units out, and the near ones left are WeakZombieB and WeakZombieC: twenty
  of life, two revolver shots or one swing of the wok instead of three shots, and the loudest of the weak
  voices (-27 to -32 dB against a Zombie's -21, and seven units out against a crowd's eleven).

  Then too many Runners in the last wave (user, the same day): the second pack of three, which arrived with
  the Hulk pair, is gone, leaving one pack early and one Runner on its own later - four where there were
  seven.  And the accuracy star asks for 70 per cent rather than 80: the player, playing it well, reached
  62 (60 was tried first, and the player asked for something to reach for).  A wok swing and a grenade
  count as shots as a revolver's does, and seldom miss, so the star is won by taking the near ones with the
  wok and keeping the revolver for when there is no time.  The tool puts Fuse at 18.0 seconds short at level 1 now,
  which is inside the end of chapter 3 (The Last Word, 22.0 short): it goes back in order with the rest of
  chapter 4 when that is tuned, and not under a player half way through it.

  Collateral was rebuilt the same day (user request: too many, "and does it make sense").  It did not: its
  first draft escorted a Berserk, a Dodge or a Shield in the middle of every crowd, and only the Shield can
  stay there.  A Berserk left alone walks away from the player (state 2 of `update:` heads along
  -orientation) and leaves after `disappearAfter`, 15 seconds; a Dodge at 0.9 outruns a crowd at 0.5; and
  some of the crowds were Runners round a Berserk walking the other way.  Now a Berserk rests seven units
  out on a crowd's way in and the crowd walks past it (`_resting`) - a revolver at the crowd can find it, a
  grenade cannot wake it, and a grenade on it still takes the crowd four units behind; a Shield walks in its
  crowd at the crowd's pace; a Dodge comes alone or two together; Runners come in a pack of their own with
  nothing in it to disturb; and the crowds are weak ones, one blast each, as in Fuse.  The last wave went
  from 38 enemies in seven crowds to 26 in five groups, and every fast thing in it is heard about twelve
  seconds before it arrives.  The tool puts it at 12.7 seconds short at level 1, from 32.1 - easier than
  Fuse and than the end of chapter 3 by its reckoning, which counts ringing ears heavily and a grenade as
  never landing on the toughest; the play-test settles it, and chapter 4's order is settled after.

  Crossfire too (user request, the same day: too many, Runners from both sides at once while the tip
  pointed at the rifle, and "room to breathe" as the condition of changing it).  The Sawn-off kills in one
  shell only inside about five units (`dispersal` 1), two to a load; the Hunting Rifle is 25 a shot, one
  enemy at a time - so a pack of three Runners wants six rifle shots and a second's switch, and is on the
  player in eight.  Its last wave had sent Runner packs from opposite sides twice over, fifteen Runners in
  46 enemies.  Now a pair is never two fast packs: two crowds that walk, or Runners with a crowd that walks,
  and the one that walks is the side that waits; the rifle is for what comes alone, a single Zombie or a
  Hulk, out of the shotgun's reach.  The groups are spaced so each comes within five units five to eleven
  seconds after the one before, the crowds are threes, and the last wave has 29.  The tip says so without
  saying it ("One side can always wait a little: choose the one that walks.  What comes alone can be met
  further out."), and the time star is 240 seconds, from 220, since the spacing makes the waves longer.
  The tool swings from 35.8 seconds short to 1.1 to spare at level 1: it never counts finding a crowd by
  ear, the half-turn between the sides or the Sawn-off's reloads, which are the arena; the play-test says
  whether it wants tightening.  Three of its crowds carry a Quiet Zombie again (the player asked for them
  back: fine inside a crowd, as long as no Runner pack comes with another), which leaves every gap as it was.

  Played, it was easy, and the player asked for two Runner packs at once after all - "but give some gaps,
  so that I have time to reload, turn and shoot" (`_runner_pair`).  A pack of three dies to a shell or two
  inside five units; the two shells a load holds, the 2.3 second reload and the half-turn, turned during the
  reload, come to about three and a half seconds.  So wave 2 sends the second pack from the opposite side
  5.5 seconds behind the first, and wave 3 sends one 4.5 behind: a second to spare, and none for waiting.
  Nothing else comes within five units within six seconds of either pair.  The tool goes from 1.1 seconds
  to spare to 0.8 short at level 1.  Then tighter, at the player's asking: the crowds that walk come in
  four to six seconds after what came before instead of six to eleven, and in fours after the first wave,
  the Runner pairs keeping their gaps.  Wave 3 has 38 enemies; the tool gives 3.0 seconds short (wave 2)
  and 1.8 (wave 3) at level 1.

  And then back to the first version, which the player liked best once all of that had been played, with
  one thing changed: in the last wave the far pack of each Runner pair comes 2.3 seconds behind the near
  one, where `_pair` puts it three tenths behind - which for Runners is both packs inside five units at
  once.  A shell into the first, a half-turn, a shell into the second.  The rebuilds above are what that
  was learnt from, and are gone.  The tip keeps the rewording that stops it pointing at the rifle for
  Runners ("One side can wait a moment, as long as you choose which.  What comes alone can be met further
  out."); the time star is 220 again.

  The Armory, last (user request, the same day: too crowded).  Its busiest eight seconds brought 23 enemies
  within five units - four Hulks and five fast ones among them - and it had the mistakes Collateral and
  Crossfire had: Runner packs from opposite sides half a second apart in wave 2, a Berserk and a Dodge
  escorted inside crowds, and in wave 3 a pack of Runners escorting a Dodge.  Changed as little as that
  needed, as the player now prefers: Berserks rest on a crowd's way in (`_resting`), Dodges come alone, the
  Shield stays in its crowd, wave 2's Runner packs are 2.3 seconds apart, wave 2 has a Hulk pair and a
  single Hulk instead of two pairs, and wave 3 two pairs instead of three and its opening crowds in fours.
  Wave 3 has 35 enemies from 40, and its busiest eight seconds 15, one fast and two Hulks.  The tool moves
  from 34.2 to 32.4 seconds short at level 1, a shade inside Crossfire before it (35.8) - one more thing
  for chapter 4's order once the player has been through it.

  Still too many, played; and the advice to meet its Chainsaws and Clowns with the Claymore was wrong while
  anything else was near - a swing locks the guns for a second and a half.  The Sawn-off takes a circling
  thing as well (its cone is sixty degrees each way; two shells for seventy of life inside three units).
  So every crowd is a three, wave 2 has no single Hulk and wave 3 one Hulk pair, a crowd went from the end
  of each, and - what the counting showed mattered most - everything was spaced: each group now comes within
  five units about five seconds after the one before, with the Runners, the Dodge, the Chainsaw and the
  Clown each arriving on their own, the spawn times worked back from where each should be.  The busiest
  eight seconds bring six, eight and seven enemies in its three waves, from fifteen, fourteen and
  twenty-three.  The tool gives 5.6 seconds short at level 1 and 1.2 to spare at level 4.

  And no Berserk, which the player caught: the Sawn-off hits everything sixty degrees either side of where it
  is aimed, and in each wave something the player would naturally shotgun - a crowd, the Hulk pair, the
  Dodge - came within five units inside that of a resting Berserk while it was there, and woke it.  Checked
  for every Berserk in every arena with a shotgun: the three in The Armory were the only ones, and their
  crowds are plain crowds now.  Collateral keeps its Berserks, having no shotgun - its grenades never wake
  one and its revolver hits one thing at a time.

* CORRECTION to `tools/arena_pressure.py`: it assumed every enemy walks straight at the player, and the ones
  with a `circling` dict do not.  State 2 heads along `(1 - circlingFactor)` toward the player plus
  `circlingFactor` sideways, so only that fraction of the speed closes the distance: a Clown, at
  `circlingFactor` 0.9 and speed 2, covers two tenths of a unit a second and takes **forty-five seconds** to
  arrive from eleven units rather than the nine the tool had been claiming.  Stampede and Big Game had both
  been sized on the wrong number and were a good deal easier than they measured - Stampede came out at plus
  3.5 seconds once this was fixed, having been tuned to minus 2.7 - so both were tuned again.  The aggressive
  state has no circling in it and comes straight in, which is why the last three units are unaffected.

  The tool also models what a challenge's `Modifiers` do to a gun now, which is arithmetic rather than
  judgement: `lessBullets` and `goldenBullet` on the capacity, the reload modifiers on the reload, and the
  spread modifiers as a change to how much overhead finding a target costs.  Two more judgement constants sit
  beside `DEAF_COST` and `MELEE_COST` and say so where they are defined: `STORM_COST`, because the game gives
  a storm no mechanical effect and it is the player it disables, and `DODGE_COST`, charged per hit an enemy
  with a `dodge` dict takes.

  An info button for Extra, beside the two the play menu already has (user request).
  `ADInfoViewController` takes a page name and reads its title and its text out of `Localizable.strings`,
  which is Somethin' Else's file and holds nothing for a mode they never wrote; so the words for this one
  are in `menus.py` and each goes through `localization.translate` on its own, which is also what puts them
  in front of a translator.  The button shares Extra's vertical centre and sits to the right of it, which
  is what makes `reading_order` read it straight after Extra - the original's own two are placed the same
  way, and one consequence of that is that Endless Info is read *before* Endless.  Play on that screen goes
  to the Extra menu, as Challenge Info's Play goes to the challenge screen.
* CORRECTION to `tools/arena_pressure.py`, the second: three things it had been getting wrong, found on
  2026-09-28 by playing the waves out tick by tick against a simple bot in a scratch file and asking why the
  two answers disagreed.  The bot is not kept - what it answers depends on how cleverly it is written, and
  one change to how it chose its next target moved an arena by fourteen seconds - but where the two
  disagreed, the reason each time was something the tool did not count.

  **`spawn_after` was ignored.**  An enemy that `checkSpawnAfterKill:` 0x1000a20ac only starts when another
  dies went into the order with a spawn time of nought, as though it had been standing there from the first
  second.  Hydra is made of nothing else, and it had measured nine seconds short when it had three to
  spare.  Such an enemy now enters the order when the one it names has been dealt with.

  **What a hit costs a Dodge was not counted.**  Case 7 of `update:` moves a Dodge sideways for `dodgeTime`
  and not an inch towards the player, and a step square to its line leaves it further out than it was, so
  every hit but the last gives the player about a second and a half back (`dodge_delay`).  The tool charged
  the hits as time spent finding it again and never as time it lost: Sidestep measured five seconds short
  with four to spare, and Iron Sights and The Last Word read several seconds harder than they are.

  **A melee weapon could be swung at anything.**  An arena fought with the wok was priced at the wok's
  damage a second, as though it reached ten units.  It reaches three, so nothing can be started on until it
  has walked that far, and it kills in whole swings a cooldown apart (`wave_pressure`'s `swing`); the
  player turns to face it on the way in.  Three Bullets read eleven seconds to spare and has four - and its
  last wave had a Runner reaching arm's length a second before two Zombies did, which leaves one second at
  the very best.  That Runner is a Zombie now.

  The four arenas those errors had misplaced were tuned back into their places rather than the order being
  changed under a player who has already been through it.  Sidestep has more walkers and a third Dodge;
  Hydra's heads grow back closer and some of them have heads of their own; Iron Sights has a walker more in
  each wave; and The Last Word's last wave comes in sooner with a second Chainsaw, so that it closes
  chapter 3 again.  The line printed afterwards falls without a break from 15.7 seconds of slack to 25.6
  short, Three Bullets excepted for the reason given with it.

  The tool also prices weapons that hit a crowd now, which it had no way to do (`area_pressure`).  A wave is
  taken pack by pack - enemies spawned together, a few degrees and a couple of units apart, at nearly one
  pace - and each pack goes to whichever weapon in hand kills it soonest.  An explosive puts `dispersal`
  percent of its damage into all of a pack and the rest only into the one it lands on (`hit_by_explosion`
  0x100061284, whose fall-off only reaches one unit), and whatever outlives the rest of its pack takes whole
  blasts after that; where it lands is the price, since inside five units it rings the ears, and the choice
  of weapon counts that ringing before making it.  A pack holding a Berserk, a Dodge or a Riot Gear Zombie
  is only ever given the explosive, which wakes nothing, sends nothing sideways and never asks after a
  shield.  A shotgun is not fired until a shell is worth `SHOTGUN_WAIT` of its best, a judgement constant
  that says so where it is defined, because the Sawn-off's damage is almost all distance.  And since a round
  of a crowd weapon is not worth its damage once, the tool counts the rounds each gun spends and prints them
  against what the arena hands out.
* CORRECTION to `tools/arena_pressure.py`, the third: an enemy's arrival sound.  `-[ADEnemy spawn]`
  0x10005fbc0 plays one of its `_spawn` recordings and `update:` 0x10005eb94 keeps it in state 1, standing
  where it spawned, until the recording ends, and the tool had taken that for a second for everything.  The
  recordings were measured on 2026-09-29, when One Swing was found to be won or lost on luck: a Zombie's
  last 1.3 to 1.7 seconds and a Runner's 1.4 to 1.9, close enough, but a QuietZombie's 0.6, a Clown's 2.4
  to 2.6, a Chainsaw's 4.6 and a Hulk's **3.7 to 5.7** - so every Hulk and Chainsaw had been measured
  seconds early, and in the wrong order against the Runners around them.  `spawn_sound` reads each enemy's
  recordings out of `game/sounds/enemies/` and takes the shortest, since a player cannot count on the longer
  one; a flat second is left only for when they cannot be read.  An enemy can be shot while it arrives
  (`canBeShotAt` 0x100061f68 refuses only states 0 and 999), so a crowd weapon's first round still waits a
  second for it to be heard and no longer.  Re-measured across all twenty-five arenas the chapters still
  climb, with two near-ties at the ends of chapters 3 and 4 (Carousel and The Last Word level at 22.0 short;
  Crossfire, at 35.8, now a shade harder than The Armory after it, at 34.2), left for the chapter 4 tuning.

  What the tool still cannot see is two enemies' arrivals lining up by chance.  It walks a wave in the order
  the clocks run out and never asks what happens when a random roar puts two of them into the same swing,
  which is what One Swing was lost on; that was found by playing the arena out a few thousand times in a
  scratch file with the game's own movement, both lengths of every recording and a player given a fixed
  time to find, turn to and strike each enemy.  Not kept, as the bot before it was not.
* FIX to a PORT ADDITION: a chapter's list of arenas answered a press in the wrong order, and a locked
  arena could be played.  A row reads the status the accessible selector gives (`statusForChallengeWithDict:`
  0x100054960), which asks about guns before it asks about locks - so an arena that wants a gun reads "Hunting
  Rifle required, press Enter to go to armory" whether or not the arena before it has been beaten.  The row
  then opened the challenge's overview for anything that did not read `locked`, and the overview only asks
  about guns (0x10003e980), since the original never shows it for a locked challenge.  So a player could open
  an arena three places ahead, buy its gun from the overview's own armory button, come back and press Play.
  Big Game and The Last Word had that hole from the day they were written; chapter 4, where four arenas of
  six want a gun bought, is what found it (2026-09-28).

  `ExtraChapterScreen.challenge_chosen` now does what the selector's `tableView:didSelectRowAtIndexPath:`
  0x100054f8c does, in the same order: a gun not bought goes to the armory, which is what the row has just
  promised; a locked arena does nothing and says nothing; anything else opens the overview.  The armory is
  presented over the list, so the rows are read out again when it is dismissed, and a player who has just
  bought the gun hears the row say `locked` if that is what it now is.
* PORT ADDITION: a challenge may name the modifiers it is played with (user request).  The original has no
  such key and none of its challenges wants one: a challenge is the same arena for everybody, which is the
  point of its stars.  Some of the port's own are built on one - Stampede's speed, Iron Sights' narrow
  cone, Rust's short cylinder - so a `Modifiers` list on a challenge dictionary is applied by
  `ChallengeGameplayController.view_did_load` (0x1000da420) through `applyModifier:` 0x100035da4 like any
  card's.

  Applied first, before the weapons and the first wave are made.  `Weapon.__init__` reads `lessBullets`,
  `goldenBullet` and the spread and head-shot modifiers when a weapon is made, and `Enemy.__init__` the
  speed and life ones when an enemy is made; applied after them, as they first were, a start from the
  overview played Iron Sights with the ordinary spread, Rust with a full cylinder and the first wave of
  Stampede, Carousel and The Last Word at ordinary speed and life, while Restart from the pause menu, which
  does not reset the modifiers, played the arenas as designed.  The referee found it (2026-09-30).
* PORT ADDITION: a wave of a challenge may hand over weapons of its own (user request, 2026-10-01), so that
  one long arena can go from the guns of one chapter to the guns of the next.  A brick's `Weapons` - a list
  in the form of the challenge's `weapons` - is handed over when the brick is loaded
  (`BrickManager.load_brick_with_name` to `ChallengeGameplayController.hand_over_weapons`): the guns in hand
  are taken away and the new ones given, the first of them drawn as a switch draws it (its deploy sound,
  and its name if the announcer is on), and the set read out - "New weapons: Police Shotgun, Revolver,
  Golf".  The first wave's is handed over before anything is heard, and says nothing.  The challenge's
  own `weapons` lists every gun any wave hands over, because that is what the overview checks
  (`hasWeaponForChallengeWithName:` 0x10001f868) and names when one is not bought.  The new guns are made
  before the old are let go, since a gun of the same name shares its playlist and activating one again is
  not immediate: the old gun releases only the playlists nothing new is using.  Checked headless with a
  two-wave arena: the second wave's guns in hand and fired, the revolver carried across still heard, the
  wok's playlist released.

  Exactly those modifiers, and nothing else: they are reset first.  Nothing resets them between the tarot
  screen and the next game-over screen, so a player who walked out of an endless game without finishing it
  would otherwise carry their hand into the challenge - and a hand holding Black Cat (`noCritical`) would
  make that arena unwinnable through no fault of theirs.  A challenge with no `Modifiers` key is left
  alone, so the original's challenges are as they always were.

* PORT ADDITION: `tools/verify_localization.py` could not see the plists the port adds whole.  The walk
  goes through the files in `game/` and offers each one twice, as it is written and as `additions.apply_to`
  hands it over - but a whole plist of the port's (`additions.PLISTS`) is in no file there, so its title,
  objective and tip were never offered to a translator at all.  Powder Keg's text had been invisible since
  the day it was written.  They are walked now, which is what the tool's own docstring had always promised.

  It still missed the one-word ones, found on 2026-09-28 (user request to fix).  `PLUMBING` took every
  single word for an id, so twelve arena titles (Fuse, Hydra, Rust...), two tarot cards of the port's
  (Berserker, Executioner) and the "Extra" a chapter's Back button says were never listed; and a short
  piece counted as covered whenever a longer key contained it, which passed "Rust" on the strength of
  "Rusty Weapons" and "Thunder" on "Thunderstorm".  A single word is now an id only when it is written like
  one - an underscore, a dot, a slash, a digit, `camelCase`, a small first letter - and the containment
  shortcut is for pieces of more than one word, which is what it was for.  A string used as a lookup key
  inside a text call (`setup_data.get('Bio')`) is not offered.  Measured over every one-word string in the
  code and the data: 88 words let through and no ids, 72 of them already in the Russian file, and the list
  of what is untranslated grew by exactly those fifteen.

* PORT ADDITION: the fourth tarot card, from a deck of the port's own where every card gives with one
  hand and takes with the other (user request).  `Tarot.plist` has no `level_4`, so the overlay makes one
  (`new_key`, the level being a key the original does not have) and fills it with twelve: Glass Cannon
  trades every hit critical for zombies with 20% more hit points, Thunder Luck trades half your shots
  critical for a storm over your hearing, Berserker melee for guns, Blood Money coins for faster zombies,
  Hair Trigger a quicker reload for a smaller clip, and so on.  Each is `goodbad` 'both', a value the
  original never uses; nothing reads it but card art that does not ship and the analytics dimension, where
  `is_good` coming back False is fair for a card that is half of each.

  A card is one flag that turns on two the game already has - `modifiers.PAIRED_FLAGS` - so the deck
  needed no new effect written for it at all, and another card is a line there and a line in
  `additions.NEW_CARDS`.  `apply_setter` turns on both halves, so a paired flag is applied by
  `applyModifier:` 0x100035da4 and cleared by `resetModifiers` exactly as the original's own flags are.
  Nothing pairs with `tesla`, which has a setter that starts a playlist.

  Two things had to be put right for a fourth slot to work at all.
  `resetCardsModifiersIfNeeded` 0x1000d42a8 cleared `tarotCard1` to `tarotCard3`, which was every card the
  original could deal, so a fourth would have been dealt once and kept for the rest of a player's life; it
  clears as many as are dealt now.  And the original's spacing is a gap put between and around the cards,
  `(container - cards x width) / (cards + 1)`, which at four 140-wide cards in a 460-wide container is
  **-20**: the row would hang off both ends.  Below zero the cards are spread across the container
  instead, the first and last flush with its edges and overlapping each other as much as they must.
  Nothing draws them, so what that protects is the reading order, which follows the frames.

* PORT DIVERGENCE: a card cannot be changed while the cards are being dealt (user request).  The original
  dims Back and Armory for those seconds (`deactivateButtons` 0x10001cee4) and the port dims Play with
  them, but every card stayed live the whole time, so a hand could be paid for and rerolled mid-deal - on
  a screen that is about to tell you what you were dealt.  A card is built during the deal and nowhere
  else, so it is built dimmed and `_cards_dealt` lets it go with Play.  `View.activate` refuses a dimmed
  element and a screen reader says "dimmed" on the way past, which is what the other three buttons do;
  `change_card_button_pressed` also returns while `dealing`, so no path round it reaches the money.

* PORT ADDITION: Executioner, a tarot card that makes every hit critical (user request).  It is the
  opposite of Black Cat, which is the original's own and says "Your weapons will land no critical hits";
  that card had no good half, and this is it.  `modifiers.PORT_FLAGS` carries `alwaysCritical`, and
  `calculateHitEnemies` 0x1000c2f14 sets the hit critical with no roll, beside Lucky Shot's and outside
  the `criticalSpread` test, so it pays for a hit however it was aimed.

  Measured through the real hit calculation, on the hunting rifle, 20,000 shots each.  On a shot 20
  degrees off - inside the gun's spread, outside its 10-degree critical cone - nothing is critical
  plainly, nothing is critical with Head-Seeking Bullets, 49.4% are with Lucky Shot and all of them are
  with Executioner.  Dead on: 14.7% plainly against the gun's own 15, 22.9% with Head-Seeking Bullets
  (1.5 times 15), none with Black Cat, and all of them with Executioner.  That is the whole shape of the
  four cards in one table, and the reason Head-Seeking Bullets and Lucky Shot are not two sizes of the
  same thing: one pays only inside the cone, the other only outside it matters.

  Black Cat does not stop every critical in the game, and that is the original's: a direct hit from an
  explosive weapon sets one in `targetEnemiForExplosiveWeapon` 0x1000c57b8 without consulting the flag.
  Nothing else can reach it, since all four of these cards are level 3 and a hand holds one of those.

* PORT DIVERGENCE: Lucky Shot makes half of every hit critical (user request).  `calculateHitEnemies`
  0x1000c2f14 rolls `random() % 100 == 1` - one hit in a hundred, which is a whole game for one extra
  critical, on a card a player gave a tarot slot to.  `modifiers.LUCKY_SHOT_PERCENT` is 50.

  What the card is for is the shot that is not lined up.  A weapon's own critical - 5% to 15%, by weapon
  - is rolled only when the shot is inside `criticalSpread`, a cone of 5 to 10 degrees, so a hit that
  lands without being aimed at can never be a critical, whatever else is in play.  Head-Seeking Bullets
  does not change that: `headShotModifier` 0x1000de51c returns 1.5, which multiplies the weapon's own
  chance inside the same cone, so it pays for good aim and nothing else.  This roll sits outside the cone
  check and is the only thing in the game that pays for a hit the player did not line up.

  That makes it the strongest card in its deck by some way, Military Grade Weapons being 10% more damage,
  and 20 was the number first for that reason.  It was raised to 50 knowingly: a game played by ear puts
  a great many shots into a zombie that was heard rather than aimed at, and a card paying for those is
  worth more here than one paying for shots already going where they should.

  The card names its own odds, so its sentence is built from the number rather than written beside it
  (`data.REWORDED`): "All shots have a 20% chance of dealing critical damage, however you aim."  Tuning
  the number moves the words with it, which is the fault that had to be fixed by hand twice - once on
  Powered Power Ups, and once here, where a 50 was left in the sentence after the number came down.

* PORT DIVERGENCE: Rusty Weapons jams three times as often (user request).  `resolveShoot` 0x100015a1c
  rolls `rand() % 100 == 1` at 0x100015b60 - one shot in a hundred - and on most guns that is a whole
  game without noticing, because the roll is per shot and a small clip is few rolls: a pistol's six
  rounds come through 94 times in 100.  `weapon.RUSTY_JAM_PERCENT` is 3, which is felt on every gun and
  leaves them all usable.  A clip then jams about 17% of the time on the pistol, 26% on the hunting
  rifle, 46% on the micro SMG, 53% on the tactical rifle and 78% on the machine gun, which has 50 rounds
  to roll and the game's longest reload at 6 seconds.  Five per cent would put the machine gun at 92%,
  which is not a weapon with a hazard but a weapon that does not work.  The number is
  `modifiers.RUSTY_JAM_PERCENT`, beside Lucky Shot's: both are tuning rather than logic, each read in one
  place, and a card that names its odds builds its sentence from the number that sits there.

  Nothing else moves.  A jam still costs the reload and no ammunition - `resolveShoot` zeroes
  `bulletsInClip` and leaves `bulletsTotal` alone, so the rounds come back on the reload - and the
  Minigun power-up still cannot jam, because `shotWithSpecialWeapon` 0x1000c4b38 never goes through
  `resolveShoot` at all.  The `< n` form has the original's odds at n = 1.

* PORT ADDITION: six tarot cards of the port's own, and more to come (user request).  Each deck keeps
  the subject the original kept it to - level 1 is the arena and what you brought to it, level 2 is the
  zombies, level 3 is your guns - and each gains as many good cards as bad, so the near-even split that makes
  the third card a coin flip stays even.  They are declared in `additions.NEW_CARDS` and dealt by the
  overlay, so `game/Tarot.plist` is untouched; `additions.new_entry` refuses a title one of their cards
  already has, which is `new_key`'s counterpart for the plists that are lists.

  Level 3: **Quick Hands** (`fasterReloadTime`) and **Heavy Hands** (`slowerReloadTime`), the two flags
  below.  Level 1: **Air Drop Inbound** (`earlyPowerUp`) drops this game's first power-up itself, owed by
  `BrickManager.reset` 0x1000c1a38 - which runs once a game, where `-[ADPowerUpManager init]` 0x10004b524
  runs once an app - and paid by the manager's next `update`, through `popPowerUpWithType:` 0x10004b8c4,
  which ends by resetting the cooldown so the drops after it keep the spacing the player paid for;
  **Lucky Night** (`luckyNight`) pays
  the two diamonds a full moon pays, on any night, through `-[ADDiamondDropper die]` 0x10007e800's own
  line; **Supply Delay** (`lessPowerUps`) adds ten seconds to the cooldown where More Power Ups! takes ten
  off, the same line in `resetPowerUpCooldown` 0x10004b640; and **Holes In Your Pockets** (`lessCoins`)
  takes 15% of the coins where Metal Detector adds 15%, the same line in `endLevel` 0x1000b89f0.

  Air Drop Inbound drops one itself rather than shortening the wait for one, which is what it did at
  first and what does not work.  The cooldown only decides whether a drop is *allowed*; what asks for one
  is the wave, through the `PowerUp` block in its own plist (`Brick.update` ->
  `tryToPopPowerUpContainer` 0x1000c7b4c), and a request made while the cooldown is running is refused.
  No level-1 wave carries that block - none of the seventeen - and an endless game's first wave is always
  a level-1 one and its second is four times in five (`brick_chance`), so nothing asks until the third
  wave or so.  By then the cooldown has run out by itself, and a card that only zeroed it gave a player
  nothing at all: the same fault as Powered Power Ups, found the same way, by asking what a player would
  actually notice rather than what the number says.

  The four new flags are `modifiers.PORT_FLAGS`, kept apart from `FLAGS` so that list stays the
  thirty-two the original's class has, in its order.  Everything that reads one reads the other: they are
  cleared by `resetModifiers` at the start of every game and accepted by `has_setter`, so `applyModifier:`
  0x100035da4 applies a card carrying one exactly as it applies theirs.

  The `icon` on each card names one of the original's own, and no card icon ships at all - the whole
  `Roulette_icon_*` set went with the roulette screen - so the port's cards are in the same position as
  Somethin' Else's and no art is invented.

* PORT DIVERGENCE: a reload takes as long as the modifiers say.  `reloadTimeModifier` 0x1000de77c is the
  original's own - 1.2 with `fasterReloadTime`, 0.8 with `slowerReloadTime` - and the original computes it
  and writes it to the log and nothing else: no card sets either flag, and no reload reads the number.  It
  is applied here, as a speed, so the time is divided by it: 1.2 makes a 2 s reload take 1.67 s and 0.8
  makes it take 2.5 s.  Which way round it was meant to go was never shipped, so this is the port's
  reading of a number the original chose (user request, for Quick Hands and Heavy Hands).

* PORT ADDITION: three tarot cards are dealt, and the third one cannot be changed (user request).
  `cardsToLoad` is 2 in `-[ADTarotViewController viewDidLoad]` 0x10003461c, but `Tarot.plist` ships a
  third level of twelve cards - six good and six bad - that the original never deals, and everything
  around it was finished: the layout divides the container by `cardsToLoad`, so 140-wide cards leave a
  10-point gap either side at three; `-[ADTarotCardViewController viewDidLoad]` 0x1000a4bd4 already prices
  a level-3 change at 1 diamond; `applyModifier:` 0x100035da4 has a setter for all twelve selectors; and
  `resetCardsModifiersIfNeeded` 0x1000d42a8 already clears three keys.  All that was missing was the 3.

  The third card is dealt and kept, and so is any card after it - the test is `>= LOCKED_CARD_LEVEL`, so
  a fourth slot would be locked the day it arrives.  It has no change button, nothing on it answers Enter,
  it is read as text rather than as a button - "button" at the end of it would be an offer it does not
  make - and it ends where it ends, while the other two say what pressing Enter costs.  It read "(this
  card cannot be changed)" at first and that came out again (user request): there is no button on the card
  and nothing to press, so a sentence saying so was a sentence explaining an absence.  It gives no
  count of diamonds in its hint either, because the count is what you would be spending.  The first two
  cards are untouched: 3 diamonds and 2, changed as often as you can pay for.  The point is that a hand
  always holds one card nobody chose, out of a deck that is a near-even split of good and bad - eight to
  seven as it stands, Executioner having found its opposite already in the deck.

  `--free-cards` (`UNLOCK_CARDS_FOR_TESTING`) opens the locked cards and charges nothing for changing
  them, so one can be looked for by pressing Enter rather than by playing hands until it turns up.  It is
  off unless the flag is passed and says so in the log when it is on, because a locked card a player can
  change is not a locked card.  Every slot goes free under it, not only the locked ones (user request):
  a hand is quicker to walk through when nothing in it has to be paid for.

  The deal still takes the time it always took (user request).  The original holds you 2.3 s and flips
  card N after N seconds, which for its two cards is the same number twice - the last card at 2 s, the
  wait 0.3 s later - and the port had read it as the second of those, so the wait grew with the deck and
  three cards took 3.3 s.  The cards share those two seconds now (`DEAL_LAST_FLIP`): the last one lands
  at 2 s however many there are, two still flip at 1 s and 2 s exactly as they always did, and nobody
  waits longer for a bigger hand.

  Two decks share a selector - `moreHeadshots` is Bobblehead Zombies on level 2 and Head-Seeking Bullets
  on level 3 - so
  about one hand in a hundred draws both and the second is a flag already set.  That is their deck, and
  it is left as it is.

* After a tarot card is paid for, every card's "You have N diamonds" hint is rebuilt.
  `changeCardButtonPressed:` 0x1000a62b8 calls `changeCard` (0x1000a63fc, ending in `refreshCard`) before
  `setDiamonds:` at 0x1000a6518, so the hint was built from the old balance; the cards that were not
  changed were never refreshed at all and kept the number they were dealt with.  The amount taken is
  unchanged (3 diamonds and 2 by card level, `viewDidLoad` 0x1000a4bd4; the third card is not for sale).
* The loadout tab names the currency a locked weapon is actually sold in.  `weaponStatus:` 0x100049c1c
  always formats the `price` key as "Locked, costs : %i coins", so the Sonic Cannon - which only has
  `priceInDiamonds` - was announced as "costs : 0 coins" while its own detail view said "Buy for 100
  diamonds".  The split used here is `checkBuyOrUpgradeButton`'s own (0x10006fa68): a price below 1 means
  the diamond price.  This line is only in the accessible loadout; the sighted `ADArmoryLoadoutViewController`
  is a drag-and-drop scroller with no price text.
* A tarot card says how many diamonds you have now, not when it was dealt.  `-refreshCard` 0x1000a58e0
  builds the card's hint, "You have N diamonds", when a card is dealt and when one is changed, and nothing
  runs it when the screen comes back - the armory is presented over this screen, so spending in it leaves
  the card quoting the balance from before.  The words are rebuilt as the screen reappears.  Only the
  words: the card, its cost and its action are untouched, because `refreshCard` also re-adds the card's
  target, and doing that twice would change the card twice, and charge twice, on one press.
* The price on a power-up's Upgrade button is right the moment it changes.  `upgradeButtonPressed:`
  0x10004e1b4 ends by asking for `loadInformation` a second later (the `dispatch_after` before
  0x10004ea84), because that second is the badge animation; the button's words are the next level's price,
  so for that second it offers a price that is no longer the one you would pay.  Sighted, the animation
  covers it.  With a screen reader, stepping off the button and back inside that second reads the old
  number as fact.  The words are refreshed at once, and the delayed call still runs, so the animation ends
  as it did.
* PORT ADDITION: three table rows that answered a key with nothing now click.  The original's buttons
  click - `-[ADButtonWithFont playSound]` 0x100073578, the status bar's and the play menu's being the same
  code - but its table rows never do.  Sighted, that is fine: the screen visibly changes.  On a keyboard,
  with the screen reader still finishing the row you were on, a press that makes no sound is
  indistinguishable from a key that did not register.  The three are the challenge selector's rows
  (`tableView:didSelectRowAtIndexPath:` 0x100054f8c, which opens the overview and is the only silent step
  of Play, world, challenge), the Zombiepedia's names (`cellSelectedWithZombieName:` 0x10007abcc), and its
  Preview sound button (`handleTapForSound:` 0x10008b9b4, where the zombie itself is held back a second by
  `dispatch_after` at 0x10008ba58 so it does not fight VoiceOver - a second that sounded like nothing
  happening), and the challenge-failed screen's Challenge selection (`missionSelectButtonPressed:`
  0x100071e1c, whose sibling on the completed screen does call `playButtonSound`, so the two screens
  answered the same key differently).  A challenge row locked by its requirements stays silent, because
  nothing happens.  This is the same reasoning as the Settings rows, which are `ADButtonWithFont`s in the
  sighted original.

  Not in this list, because it was a fault rather than a choice: the challenge-completed screen's three
  buttons - Retry, Challenge selection and Next challenge, read in that order (see Divergences) - do call
  `playButtonSound` 0x100049300 in the
  original (at 0x048884, 0x0489e0 and 0x048bc0), which plays `click_button` at gain 3, and the port had
  simply missed it.  They click now because the original does.
* PORT ADDITION: the Credits screen names the studio, and carries the port's own credits.
  `ADAboutCreditsViewController` 0x100020ea4 lays out two text views, and the nib's credits (object #25)
  list every person who made the game and `www.audiodefence.com`, but never Somethin' Else - the studio's
  name is nowhere on the screen.  Two lines go above that text saying whose game it is.  A third text view
  follows the nib's two, read last, with who made the Windows port and where the repository is; it is a
  view of its own so the cursor reaches it in one step instead of through the whole cast.  The nib's text
  is unchanged, and `ui/credits_text.py` still holds it exactly as extracted.
* REMOVED (user request): the magic tap, and F2, the key the port had bound it to.  VoiceOver's
  two-finger double tap is a gesture iOS gives no keyboard equivalent, and every screen that answered it
  did so with a button the screen already reads out - so the key was a second way to press something the
  cursor reaches anyway, and on the revive screen a second way to end the run by accident.  What each
  implementation did, for anyone comparing with the original: `-[ADViewController
  accessibilityPerformMagicTap]` 0x100072940 announced that a screen has none; the main menu 0x100065d40,
  the tarot screen 0x100036634 and the challenge overview 0x1000403e0 pressed Play (the overview's pressed
  it even while Play was disabled); the play menu 0x1000abc80 pressed Endless once tutorial_5 had been
  completed and Challenge before that; the Endless game over 0x10009bff8 pressed Play again; the
  challenge-completed screen 0x10006974c pressed Next mission; and the revive screen 0x100021cb4 pressed
  Game over.  F1, which read the focused element out again, went with it (user request): a screen
  reader's own review keys already do that, on any window.
* REMOVED (user request): the armory's Currency tab.  Its table asks `products` for its row count and
  nothing in the binary ever sets `products`, so the tab was blank on every device.  It was built to hold
  four "free coins" offers - Facebook, Twitter, the studio's other games, the App Store - each opening a web
  page, none of them wired up.  The port briefly kept it with a row explaining itself; it is now gone, so
  the armory has three tabs.  Two knock-ons: `showNotEnoughMoneyAlert` 0x1000768d4 no longer offers its
  "More coins" button, which called `currencyButtonPressed`, and `COINS_ALERT_CONTENT`'s last sentence -
  "You can also get coins in the Armory's currency tab" - is cut, since it would point at nothing.  The
  button itself stays in the nib layout, unreachable and with nothing routed to it.
* A power-up no longer survives the game it was picked up in.  `-[ADWeaponManager clean]` 0x1000aad50 cleans
  the power-up of the manager it is sent to, and killGameplay's block only sends it to the gameplay manager,
  whose own `powerUp` is always nil - `initPowerUp:` and `usePowerUp` go through `+sharedWeaponManager`,
  which nothing ever cleans.  The shared one is cleared with the rest of the game.
* A "survive" mission advances.  `-[ADMissionManager update:]` 0x1000085ac asks whether tutorial_5 is
  complete, throws the answer away, and never forwards the tick, so `-[ADMission update:]` 0x100044e30 never
  ran and `survivalTime` stayed at 0 however long you lived: the mission could be shown, attempted and
  saved, but never completed.  The tick is forwarded.
* A "kill N zombies" mission remembers its count.  `-[ADMission encodeWithCoder:]` 0x1000464c0 stores twelve
  fields and omits `progression_zombies`, which `isMissionCompleted` tests - so the count went back to zero
  on every restart and the mission could only be finished in one sitting.  It is saved with the rest.
* A finished game's rewards are paid once.  `-[ADGameOverWithStatsViewController viewDidLoad]` sends
  `ignoreRewards` at 0x100042030 and discards the answer, so the coins and diamonds were credited by every
  screen of that family - including the challenge overview, which sets `ignoreRewards` to YES precisely to
  avoid it, and which paid again each time it was opened.  The answer is tested.
* The completed screen reports a failed accuracy objective as failed.  The pass and fail paths converge at
  loc_100068794 and `accuracyObjectiveReached:1` is sent from there unconditionally.  The time-limit star
  three lines below already reports its failure properly; accuracy now does the same.
* A weapon at its maximum level says nothing instead of "Not enough Diamonds!".  With no next level there is
  no cost to compare, both branches read 0, and the alert was shown; `checkBuyOrUpgradeButton` 0x10006fa68
  hides the button by then, which is why it is hard to reach, but the alert was wrong wherever it appeared.
* The first control scheme screen offers Gyro.  The nib wires `gyroTextButton` to the Gyro button itself
  (`tiltTextButton` and `swipeTextButton` are not connected at all), so hiding the "text buttons" under a
  screen reader hid the recommended scheme - the one a fresh profile starts on - leaving Tilt and Swipe as
  the only choices on the one screen that exists to make that choice.
* A cow or a car is added to the passer-by list once.  `generateCow` 0x1000d5d04 appends it and then hands
  it to `ADBrickManager addPasserBy:`, which forwards straight back and appends it again; the duplicate was
  updated alongside the original, so they moved and aged at twice their speed.  Cars do the same at
  0x1000d5f08.
* A cow that cannot spawn waits its turn.  `generateCow` returns without touching `nextCow` when both cow
  playlists are busy, and `nextCow` is already below zero, so `update:` retried it every single tick.  The
  timer is re-rolled instead.
* The tornado cleans up once.  `update:` 0x100097af0 cleans it after its four gusts but never clears
  `active`, so every later tick fell through the guard and cleaned it again for the rest of the game.
* The enemy unlock gate reads the enemy's name, not the brick's slot label.  `canUseBrickWithName:`
  0x1000c259c looks each `Enemies` key up verbatim, but a brick wanting two of the same enemy labels the
  slots "Chainsaw - 2", "Runner - 3", "WeakZombieB " with a trailing space.  Those match nothing in
  `enemies.plist`, so the requirement came back 0 and the slot walked through the gate.  No gated enemy is
  written that way today, so nothing actually escaped - but one added in a repeat slot would have.
* An explosion pauses a jukebox.  `-[ADJukeBox hitByExplosionAtPosition:withDamages:dispersal:radius:]`
  0x100066784 pauses the music, but every sender - `solveExplosionWithDictionary:` 0x1000c5c40 and
  `hitByProjectile:` 0x100061098 - uses the five-argument `...powerupname:` form, so the override was never
  reached and ADEnemy's implementation ran instead: the jukebox took the damage and played on.
* The post-game statistics show the combo they measured.  `buildMiscPostGameData` 0x1000bacfc labels entry 4
  "Highest combo" and fills it from `numberOfEnemyKills` (the load at 0x1000bb1fc), so the screen reported
  the kill count twice and never showed `highestCombo`, which is maintained right beside it.
* The sound follows the default output (user request, 2026-09-29).  `s3d/device.py` opened the default
  playback device once, at start-up, and a player who chose other headphones or speakers in Windows while
  the game ran kept hearing it through the old ones - the speech moved, since SAPI 5 follows the default
  of its own accord, and the game did not.  A phone has one output that the system switches for it; this is
  the port's own problem and has no method in the binary to depart from.  OpenAL Soft 1.25 says when the
  default output changes (ALC_SOFT_system_events, asked for only when `alcEventIsSupportedSOFT` answers
  yes, which it does once a device is open) and can move an open device to another output keeping its
  contexts, sources and buffers (ALC_SOFT_reopen_device), so `Device` listens for the one event, hands it
  from OpenAL's thread to the run loop, waits half a second (`FOLLOW_AFTER`: Windows reports one change
  several times, once for each role a device plays), and reopens on the new default with the attributes it
  was opened with, HRTF and all.  Nothing that is playing stops.  Tested silently: four reports from another
  thread made one move, and a forced reopen kept a playing source playing with the game's HRTF still on;
  the change of output itself was left to a player, since a test has no business changing the system's.
* Tilt turns the way its key says (user request, 2026-09-29).  `KeyboardMotion.tilt_angle` stands in for
  `-[ADMotionManager getTiltAngle]` 0x100005dec, which reads the attitude's pitch - whose sign in landscape
  follows which way round the phone is held, `statusBarOrientation` - and `tiltDidMoveFromAngle:`
  0x10009cfe8 turns by it times -15 and the sensitivity.  The stand-in gave the right key a positive angle,
  which turned the listener left, so under Tilt the right key and a stick pushed right turned left, against
  Gyro and Swipe.  It gives the right key the negative angle now.  Checked a step at a time: the right key
  lowers the heading under all three schemes (Swipe through `touchesMoveDetected:`, which flips the drag).


## Original quirks kept on purpose

* Melee cancels a reload.  `shootWithMelee` 0x1000aaa98 interrupts a reload in progress and *then* asks
  `isWeaponReadyToShoot` 0x1000aa350, which by then answers yes because interrupting put the weapon back
  in Idle: melee does not override the check, it clears the state the check reads.  Firing waits instead,
  `readyToShoot` 0x10001537c answering no in the reload states, so the two do not behave alike.  This was
  changed on 2026-09-21 so that melee waited as firing does, and reverted the same day at the user's
  request: swinging the machete mid-reload is something the game lets you do, and losing the reload is
  what it costs.  (`interruptReload` has a second caller, the weapon switch, which is meant to cancel.)

These are the original's, reproduced deliberately.  Each is either a design decision rather than a fault, a
change that would alter how the game plays or sounds rather than what it tells you, or something with no
observable effect at all.

* **Endless hides enemies that challenges show.**  `-[ADBrickManager canUseBrickWithName:]` 0x1000c259c
  refuses a wave while any enemy in it still has a kill requirement (`bestiary -> Unlock requirement` minus
  the save's total kills, 0x100084ea8).  Challenges do not check: `scenarioBrickNameForWaveNumber:`
  0x1000c28d8 indexes the challenge's own brick list, and several scripts hold gated enemies - maya_8 is all
  Berserk (250 kills), maya_10 Berserk and Riot Gear Zombie, maya_5 and maya_6 the Whisperer.  The gated
  five: Whisperer 150, Berserk 250, Riot Gear Zombie 350, Zombie Dog 400, Colossus 450.  This is the design -
  challenges are scripted set pieces - and changing it either breaks them or removes Endless's progression.
* **`brick_chance.plist` has a row 12 that nothing can read.**  `brickNameForWaveNumber:` clamps the wave
  with `arg1 > 11 ? 11 : arg1`, so from wave 11 the mix stops changing and `loadNextBrick` ramps
  `difficultyModifier` by 0.14 a wave instead.  Reaching row 12 would change the difficulty curve of every
  long Endless run.
* **The weapon timers advance by wall-clock time** (`CACurrentMediaTime`), not by the timer's interval.
  Changing it would alter every weapon's fire rate and reload.
* **Only an enemy's looping voice and footstep sounds reach the reverb**
  (`playAnySoundContaining:looping:spatialized:` with spatialized YES); its hit, pain, death, impact and
  explosion sounds are dry.  Changing it would rewrite how the game sounds.
* **The explosion falloff cancels its own radius**: `1 - (d2 / radius) * radius`, so damage falls off by
  squared distance whatever the blast radius.  Changing it would re-balance every explosive weapon.
* **A blast never wakes a Berserk.**  `hit_by_explosion` 0x100061284 takes the life off and nothing else;
  only a weapon's hit (`hit_by_weapon` 0x100060b30) sends it berserk, so a grenade next to a Berserk that has
  not been shot leaves it resting, as was seen in play - but it does take the damage.  (This entry used to
  say the blast could not touch it at all: `canBeShotAt` 0x100061f68 excludes only state 0, an enemy still
  waiting for its spawn time, and a resting Berserk has arrived.  Measured 2026-09-30: a grenade took 45 off
  one resting and one walking away, and neither woke.)
* The accessible Endless game-over screen is silent, because `-[Accessible_ADGameOverEndlessViewController
  viewDidLoad]` 0x100099f50 never calls `[super viewDidLoad]` and so never starts `game_over_theme`.  Kept at
  the user's request: it is the score you just lost, not a menu.
* `-[ADSound initWithDictionary:]` hardcodes a speed of 2.0 and ignores any `speed` key.  No scripted sound
  in any of the game's plists carries one, so nothing can reach it.
* The diamond dropper schedules `[nil deactivatePlaylist]` five seconds after dying (the `str xzr` at
  0x10007e950): the receiver is nil, so nothing is scheduled and nothing happens.
* `-[ADWeapon changeState:]` 0x100015148 returns `(old != 0) != newState`, comparing a bool with a state
  number.  Every caller discards the result.
* The challenge selector asks the app delegate for the sighted challenge overview with a nil challenge;
  `goToChallengeSelector` 0x1000816e0 always passes nil for `challengeToLoad`, so the port never reaches that
  call at all.
* The tarot schedules each card flip with `dispatch_after(<card number>)`, a time already past, so the block
  runs on the next pass and then flips after that many seconds - which is the timing either way.
* `checkEquipButtons` 0x10006ff8c leaves `equip1Button` with whatever hidden state it had when the weapon is
  a melee weapon; the nib's state is visible, which is what that branch wants.
* `-[ADPersistentStats allUnlockedEnemies]` 0x100085dd4 keys its dictionary by display name rather than by
  the enemy's internal name.
