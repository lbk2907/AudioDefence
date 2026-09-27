"""Audio Defence for Windows and the Mac.

The game is started by ``py AudioDefence.py [options]``, which calls
``main()`` here; ``python -m audiodefence`` runs the same thing.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time


def _setup_logging(level: str) -> None:
    from .paths import user_dir
    handlers = [logging.FileHandler(os.path.join(user_dir(), 'audiodefence.log'), 'w', encoding='utf-8')]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format='%(asctime)s %(name)s %(levelname)s %(message)s', handlers=handlers)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='audiodefence')
    parser.add_argument('--log-level', default='info')
    parser.add_argument('--game', help="the original app bundle (or the folder holding it), when it is not "
                                       "in the project's game folder")
    # PORT ADDITION (user request): the flags below exist in a checkout and not in a build.  They let
    # the game be started past its own rules - Endless before it is unlocked, a challenge whose
    # requirements are not checked, a locked tarot card that can be changed - which is what makes them
    # worth having while the port is being worked on and worth not shipping.  A release does not know
    # them at all: they are never added to the parser, so it answers "unrecognized arguments" rather than
    # carrying a switch that turns the rules off.  `sys.frozen` is what `paths.FROZEN` reads, asked
    # directly because `--game` has to reach the environment before `paths` is imported at all.
    #
    # `--game` and `--log-level` stay in a build on purpose: the first is how a player points the game at
    # its data when it is not where it is looked for, and the second is the first thing to try when
    # something misbehaves.  Neither changes how the game plays.
    from_source = not getattr(sys, 'frozen', False)
    if from_source:
        parser.add_argument('--endless', action='store_true',
                            help='start an endless game, unlocked or not (skips the menu and the cards)')
        parser.add_argument('--challenge', metavar='NAME',
                            help='start a challenge by its plist name, e.g. tutorial_1, unlocked or not')
        parser.add_argument('--free-cards', action='store_true',
                            help='testing: the tarot cards that cannot be changed can be, and cost nothing')
        parser.add_argument('--mute', action='store_true', help='testing: silence the listener')
        parser.add_argument('--no-speech', action='store_true', help='testing: do not speak')
        parser.add_argument('--exit-after', type=float, metavar='SECONDS',
                            help='testing: quit after this many seconds')
    args = parser.parse_args(argv)
    endless = getattr(args, 'endless', False)
    challenge = getattr(args, 'challenge', None)
    free_cards = getattr(args, 'free_cards', False)
    mute = getattr(args, 'mute', False)
    no_speech = getattr(args, 'no_speech', False)
    exit_after = getattr(args, 'exit_after', None)
    if args.game:
        # set before anything imports audiodefence.paths: that module resolves the bundle on import
        os.environ['AUDIODEFENCE_GAME'] = args.game
    _setup_logging(args.log_level)
    log = logging.getLogger('main')
    from . import paths
    log.info('game data: %s (from %s)', paths.BUNDLE, paths.BUNDLE_SOURCE)
    if not os.path.isdir(paths.BUNDLE):
        log.error("the game's data is not where the port looks for it: put the original audiodefence.app "
                  "in the project's game folder, or pass --game PATH (see the README)")
    if not paths.FROZEN:
        from .platform import version
        version.current()                               # a checkout with no VERSION file gets one now

    import pygame
    from .app import App
    from .game.parameters import GameParameters
    from .platform.runloop import RunLoop
    from .platform.speech import Speech
    from .s3d.engine import S3DEngine
    from .ui.host import ScreenManager

    if no_speech:
        Speech.shared().speak = lambda *a, **k: None
        Speech.shared().speak_automatic = lambda *a, **k: None
    if free_cards:
        from .ui import tarot
        tarot.UNLOCK_CARDS_FOR_TESTING = True
        log.warning('--free-cards: the locked tarot cards can be changed, and cost nothing. '
                    'This is not how the game plays.')
    GameParameters.screen_reader_running = Speech.shared().screen_reader_running()
    Speech.shared().choice = GameParameters.shared().speech_output()   # Settings -> Miscellaneous
    Speech.shared().configure_sapi(**GameParameters.shared().sapi_config())

    from .platform.pad import Pads, set_hints
    set_hints()                                         # before SDL's joystick layer starts, in pygame.init()
    pygame.init()
    pygame.display.set_caption('Audio Defence')
    pygame.display.set_mode((640, 480))
    Pads.shared().start()                               # PORT ADDITION: game controllers
    Pads.shared().speak = lambda text: Speech.shared().speak(text, False)

    host = ScreenManager()
    Pads.shared().changed = host.pads_changed           # Settings -> Joystick follows a controller in and out
    running = [True]
    host.request_quit = lambda: running.__setitem__(0, False)
    app = App.delegate()
    app.host = host
    if endless or challenge:
        app.init_papa_engine()
        app.run_sanity_check()
        if endless:
            app.go_to_gameplay()
        else:
            app.go_to_challenge_with_dict(App.dictionary_for_challenge_with_name(challenge))
    else:
        app.application_did_finish_launching()          # logo, then the opener or the control scheme choice
    if mute:
        from .s3d import openal as oal
        S3DEngine.engine().al.alListenerf(oal.AL_GAIN, 0.0)

    loop = RunLoop.main()
    engine = S3DEngine.engine()
    started = time.perf_counter()
    try:
        while running[0]:
            if exit_after is not None and time.perf_counter() - started > exit_after:
                break
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running[0] = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    app.application_will_resign_active()
                else:
                    host.handle_event(event)
            loop.run_once()
            engine.pump()
            host.frame()
            wait = min(loop.next_deadline() - loop.now(), 0.005)
            if wait > 0:
                time.sleep(wait)
    except KeyboardInterrupt:
        pass
    finally:
        log.info('shutting down')
        closing = time.perf_counter()
        try:
            try:
                # PORT ADDITION: silence the game before taking it apart.  Shutting the engine down, closing
                # the speech card and pygame.quit() are all Python work of a few tens of milliseconds each,
                # and the game's own sound is mixed by Python on the audio thread (the reverb bus): with the
                # music still playing it stuttered on the way out, stopping and starting between the steps.
                from .s3d import openal as oal
                engine.al.alListenerf(oal.AL_GAIN, 0.0)   # one call: silent before any of the slow work
                engine.stop_all()
            except Exception:
                log.exception('could not stop the sounds')
            try:
                Pads.shared().stop()                    # a DualSense keeps a trigger feel until told not to
            except Exception:
                log.exception('could not reset the controllers')
            try:
                Speech.shared().shutdown()              # and speech lets its own card go before the engine's
            except Exception:
                log.exception('could not stop the speech')
            engine.shutdown()
        finally:
            pygame.quit()
            # PORT ADDITION: the last line says how long the closing took, so "it was slow to close" can be
            # answered from a log instead of a stopwatch.  What is left after it is the interpreter itself.
            log.info('closed in %d ms', (time.perf_counter() - closing) * 1000.0)
    return 0


if __name__ == '__main__':
    sys.exit(main())
