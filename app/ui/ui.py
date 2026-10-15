import time

import pygame
from pygame.locals import *

from ui.utils import sound


class UserInterface:
    def __init__(self, screen, resolution=(800,480),
                 ui_placement_mode=False, fps=60, dev_mode=False, audio=True,
                 audio_params=(22050, -8, 1, 1024), fullscreen=False, panel=None, dark_fps=4):
        # init system
        pygame.display.init()
        pygame.font.init()
        sound.init(audio_params)

        self.screenSurface = pygame.display.set_mode(resolution, pygame.FULLSCREEN if fullscreen else 0)
        self.fpsClock = pygame.time.Clock()
        self.fps = fps
        self.dark_fps = dark_fps
        pygame.display.set_caption("LCARS")
        if not dev_mode: 
            # see https://github.com/tobykurien/rpi_lcars/issues/9
            #pygame.mouse.set_visible(False)
            try:
                pygame.mouse.set_cursor((8,8),(0,0),(0,0,0,0,0,0,0,0),(0,0,0,0,0,0,0,0))
            except pygame.error:  # no cursor support (headless): just hide it
                pygame.mouse.set_visible(False)

        # The panel (panel.context.Panel): night, the lock, metrics. Optional,
        # so the stock screens still run without it.
        self.panel = panel
        self._swallowing = False  # the rest of a touch that only woke the screen
        self._blank = False

        # set up screen elements
        self.all_sprites = pygame.sprite.LayeredDirty()
        self.all_sprites.UI_PLACEMENT_MODE = ui_placement_mode
    
        self.screen = screen
        self.screen.setup(self.all_sprites)
        self._screen_metric(screen, 1)
        self.running = True

    @property
    def dark(self):
        return self.panel is not None and self.panel.night.dark

    def update(self):
        if self.panel is not None:
            self.panel.tick()
        if self.dark:
            # Nothing to see: draw black once and skip the frames.
            if not self._blank:
                self.screenSurface.fill((0, 0, 0))
                pygame.display.update()
                self._blank = True
            self.screen.update(self.screenSurface, self.fpsClock)  # lets it go home
            return
        self._blank = False
        started = time.perf_counter()
        self.screen.pre_update(self.screenSurface, self.fpsClock)
        self.all_sprites.update(self.screenSurface)
        self.screen.update(self.screenSurface, self.fpsClock)
        pygame.display.update()
        if self.panel is not None:
            self.panel.metrics.set("lcars_frame_seconds", round(time.perf_counter() - started, 4))

    def _wanted(self, event):
        """False for the touches the panel swallows: the whole of a touch
        that only woke the dark screen."""
        if self.panel is None:
            return True
        if event.type == MOUSEBUTTONDOWN:
            self._swallowing = self.panel.tap()
            return not self._swallowing
        if event.type == MOUSEMOTION:
            return not self._swallowing
        if event.type == MOUSEBUTTONUP and self._swallowing:
            self._swallowing = False
            return False
        return True

    def handleEvents(self):
        for event in pygame.event.get():
            if (event.type == pygame.QUIT) or \
                (event.type == KEYUP and event.key == K_ESCAPE):
                pygame.quit()
                self.running = False
                return

            if not self._wanted(event):
                continue

            for sprite in self.all_sprites.sprites():
                if hasattr(event, "pos"):
                    focussed = sprite.rect.collidepoint(event.pos)
                    if (focussed or sprite.focussed) and sprite.handleEvent(event, self.fpsClock):
                        break
                
            self.screen.handleEvents(event, self.fpsClock)
            if self.switchScreen():
                break
        # Screens may also ask to switch from update() (a relock, a timeout).
        self.switchScreen()

    def switchScreen(self):
        newScreen = self.screen.getNextScreen()
        if not newScreen:
            return False
        self.all_sprites.empty()
        newScreen.setup(self.all_sprites)
        self._screen_metric(self.screen, 0)
        self._screen_metric(newScreen, 1)
        self.screen = newScreen
        return True

    def _screen_metric(self, screen, value):
        if self.panel is not None:
            self.panel.metrics.set("lcars_screen", value, screen=getattr(screen, "name", type(screen).__name__))

    def isRunning(self):
        return self.running
    
    def tick(self):
        self.update()
        if not self.running:
            return
        self.handleEvents()
        if self.running:
            self.fpsClock.tick(self.dark_fps if self.dark else self.fps)
