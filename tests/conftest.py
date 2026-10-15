import os

# Before pygame or config load: no window, no sound card, no metrics port.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["LCARS_SOUND"] = "false"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
