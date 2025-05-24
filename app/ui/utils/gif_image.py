"""GIFImage by Matthew Roe"""

from PIL import Image
import pygame
from pygame.locals import *
import time


class GIFImage(object):
    def __init__(self, filename, duration=-1):
        self.duration = duration
        self.filename = filename
        self.image = Image.open(filename)
        self.frames = []
        self.get_frames()

        self.cur = 0
        self.ptime = time.time()

        self.running = True
        self.breakpoint = len(self.frames)-1
        self.startpoint = 0
        self.reversed = False

    def get_rect(self):
        return pygame.rect.Rect((0,0), self.image.size)

    def get_frames(self):
        self.frames = []
        try:
            while True:
                self.image.seek(self.image.tell() + 1)
                frame = self.image.convert('RGBA')
                mode = frame.mode
                size = frame.size
                data = frame.tobytes()

                duration = self.image.info.get('duration', 100)
                pi = pygame.image.fromstring(data, size, mode)
                self.frames.append((pi, duration))
        except EOFError:
            pass

    def render(self, screen, pos):
        if self.running:
            if time.time() - self.ptime > self.frames[self.cur][1]:
                if self.reversed:
                    self.cur -= 1
                    if self.cur < self.startpoint:
                        self.cur = self.breakpoint
                else:
                    self.cur += 1
                    if self.cur > self.breakpoint:
                        self.cur = self.startpoint

                self.ptime = time.time()

        screen.blit(self.frames[self.cur][0], pos)

    def seek(self, num):
        self.cur = num
        if self.cur < 0:
            self.cur = 0
        if self.cur >= len(self.frames):
            self.cur = len(self.frames)-1

    def set_bounds(self, start, end):
        if start < 0:
            start = 0
        if start >= len(self.frames):
            start = len(self.frames) - 1
        if end < 0:
            end = 0
        if end >= len(self.frames):
            end = len(self.frames) - 1
        if end < start:
            end = start
        self.startpoint = start
        self.breakpoint = end

    def pause(self):
        self.running = False

    def play(self):
        self.running = True

    def rewind(self):
        self.seek(0)
    def fastforward(self):
        self.seek(self.length()-1)

    def get_height(self):
        return self.image.size[1]
    def get_width(self):
        return self.image.size[0]
    def get_size(self):
        return self.image.size
    def length(self):
        return len(self.frames)
    def reverse(self):
        self.reversed = not self.reversed
    def reset(self):
        self.cur = 0
        self.ptime = time.time()
        self.reversed = False

    def copy(self):
        new = GIFImage(self.filename)
        new.running = self.running
        new.breakpoint = self.breakpoint
        new.startpoint = self.startpoint
        new.cur = self.cur
        new.ptime = self.ptime
        new.reversed = self.reversed
        return new

##def main():
##    pygame.init()
##    screen = pygame.display.set_mode((640, 480))
##
##    hulk = GIFImage("hulk.gif")
##    football = GIFImage("football.gif")
##    hulk2 = hulk.copy()
##    hulk2.reverse()
##    hulk3 = hulk.copy()
##    hulk3.set_bounds(0, 2)
##    spiderman = GIFImage("spiderman7.gif")
##
##    while 1:
##        for event in pygame.event.get():
##            if event.type == QUIT:
##                pygame.quit()
##                return
##
##        screen.fill((255,255,255))
##        hulk.render(screen, (50, 0))
##        hulk2.render(screen, (50, 150))
##        hulk3.render(screen, (50, 300))
##        football.render(screen, (200, 50))
##        spiderman.render(screen, (200, 150))
##        pygame.display.flip()
##
##if __name__ == "__main__":
##    main()
