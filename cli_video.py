import os
import sys
import multiprocessing as mp
from time import time, sleep
from functools import partial
from typing import Tuple, Callable, Optional, List

from moviepy.editor import VideoFileClip
from pynput.keyboard import Key
from pynput import keyboard
from tqdm import tqdm
import pygame


# For ANSI escape sequences to be processed correctly on windows
os.system("")


ANSI_RESET_STYLE = "\033[0m"
ANSI_RESET_CURSOR = "\033[H"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"
ANSI_CLEAR_TERMINAL = "\033[2J"


Rgb = Tuple[int, int, int]
RawFrame = List[List[Rgb]]
AudioFunc = Callable[[], None]


def max_video_size() -> Tuple[int, int]:
    height = os.get_terminal_size().lines - 1
    width = os.get_terminal_size().columns // 2
    return height, width


def ansi_backround_rgb(rgb: Rgb) -> str:
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def convert_raw_frame(raw_frame: RawFrame, offset: Tuple[int, int]) -> str:
    output = [ANSI_RESET_CURSOR]
    output.append("\n" * offset[0])
    for row in raw_frame:
        output.append("\n")
        output.append("  " * offset[1])
        for pixel in row:
            output.append(ansi_backround_rgb(pixel) + "  ")
        output.append(ANSI_RESET_STYLE)
    return "".join(output)


def convert_raw_frames_in_parallel(
    frames: List[RawFrame], offset: Tuple[int, int]
) -> List[str]:
    _convert_raw_frame = partial(convert_raw_frame, offset=offset)
    with mp.Pool(processes=mp.cpu_count()) as pool:
        return list(tqdm(pool.imap(_convert_raw_frame, frames), total=len(frames)))


def calculate_offset(video: VideoFileClip) -> Tuple[int, int]:
    terminal_height, terminal_width = max_video_size()

    if terminal_height > video.h:
        vertical_offset = (terminal_height - video.h) // 2
        return vertical_offset, 0

    horisontal_offset = (terminal_width - video.w) // 2
    return 0, horisontal_offset


def create_frames(video: VideoFileClip) -> List[str]:
    frame_count = round(video.duration * video.fps)
    offset = calculate_offset(video)
    print("Loading frames")
    frames = [frame for frame in tqdm(video.iter_frames(), total=frame_count)]
    print("Processing frames")
    return convert_raw_frames_in_parallel(frames, offset)


class FramesPlayer:
    def __init__(
        self,
        frames: List[str],
        frame_rate: int,
        pause_audio: AudioFunc,
        unpause_audio: AudioFunc,
    ) -> None:
        self.frames = frames
        self.frame_rate = frame_rate
        self.frame_time_s = 1 / self.frame_rate
        self.pause_audio = pause_audio
        self.unpause_audio = unpause_audio
        self.is_paused = False
        self.start_time = 0
        self.pause_time = None
        self.check_paused_time_s = self.frame_time_s
        self.setup_keyboard_listener()

    def setup_keyboard_listener(self) -> None:
        def on_press(key) -> None:
            if key == Key.space:
                self.toggle_pause()

        keyboard.Listener(on_press=on_press).start()

    def toggle_pause(self) -> None:
        if self.is_paused:
            assert isinstance(self.pause_time, float)
            self.unpause_audio()
            self.start_time += time() - self.pause_time
            self.pause_time = None
        else:
            self.pause_audio()
            self.pause_time = time()
        self.is_paused = not self.is_paused

    def calculate_correction_s(self, frame_index: int) -> float:
        elapsed_time = time() - self.start_time
        theoretical_elapsed_time = frame_index / self.frame_rate
        return theoretical_elapsed_time - elapsed_time

    def frame_sleep(self, correction_s: float) -> None:
        sleep_time_s = self.frame_time_s + correction_s
        sleep(max(sleep_time_s, 0))

    def handle_pause(self) -> None:
        while self.is_paused:
            sleep(self.check_paused_time_s)
        # Make sure start time has been corrected
        while self.pause_time is not None:
            sleep(self.check_paused_time_s)

    def play(self) -> None:
        self.start_time = time()
        for i, frame in enumerate(self.frames):
            self.handle_pause()
            correction_s = self.calculate_correction_s(frame_index=i)
            if correction_s > self.frame_time_s:
                continue
            print(frame, end="")
            self.frame_sleep(correction_s)


def play_audio(video: VideoFileClip) -> Tuple[AudioFunc, AudioFunc, AudioFunc]:
    audio = video.audio
    if not audio:
        return lambda: None, lambda: None, lambda: None

    current_time_ms = 1000 * time()
    temp_audio_path = f"cli-video-temp-{current_time_ms:.0f}.mp3"
    if os.path.exists(temp_audio_path):
        raise FileExistsError("Temporary sound file already exists.")
    audio.write_audiofile(temp_audio_path)

    pygame.mixer.init()
    pygame.mixer.music.load(temp_audio_path)
    pygame.mixer.music.play()

    def cleanup() -> None:
        pygame.mixer.music.unload()
        os.remove(temp_audio_path)

    def pause() -> None:
        pygame.mixer.music.pause()

    def unpause() -> None:
        pygame.mixer.music.unpause()

    return cleanup, pause, unpause
            


def calculate_target_resolution(path: str) -> Tuple[Optional[int], Optional[int]]:
    video = VideoFileClip(path)
    terminal_height, terminal_width = max_video_size()
    terminal_aspect_ratio = terminal_width / terminal_height

    if terminal_aspect_ratio < video.aspect_ratio:
        return None, terminal_width
    return terminal_height, None


def load_video(path: str, frame_rate: int) -> VideoFileClip:
    video = VideoFileClip(
        path,
        target_resolution=calculate_target_resolution(path),
        resize_algorithm="fast_bilinear",
    )
    video = video.set_fps(frame_rate)
    return video


def play_video(path: str, frame_rate: int) -> None:
    try:
        print(ANSI_HIDE_CURSOR, end="")
        video = load_video(path, frame_rate=frame_rate)
        frames = create_frames(video)
        audio_cleanup, pause_audio, unpause_audio = play_audio(video)
        print(ANSI_CLEAR_TERMINAL, end="")
        FramesPlayer(
            frames,
            frame_rate=frame_rate,
            pause_audio=pause_audio,
            unpause_audio=unpause_audio,
        ).play()
    finally:
        print(ANSI_SHOW_CURSOR, end="")
        audio_cleanup()
        video.close()


def main() -> None:
    if "--help" in sys.argv:
        print("USAGE: python cli_video.py [path] [options]")
        print()
        print("OPTIONS:\n  --frame-rate")
        return

    try:
        i = sys.argv.index("--frame-rate")
        sys.argv.pop(i)
        frame_rate = int(sys.argv.pop(i))
    except ValueError:
        frame_rate = 24

    play_video(sys.argv[-1], frame_rate=frame_rate)


if __name__ == "__main__":
    main()
