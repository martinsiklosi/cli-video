import os
from time import time, sleep
from tempfile import mkstemp
from dataclasses import dataclass
from argparse import ArgumentParser
from contextlib import contextmanager
from typing import Tuple, Callable, Optional, List, Generator

from moviepy.editor import VideoFileClip
from pynput import keyboard
from pygame import mixer
from tqdm import tqdm


# For ANSI escape sequences to be processed correctly on windows
os.system("")


ANSI_RESET_STYLE = "\033[0m"
ANSI_RESET_CURSOR = "\033[H"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"
ANSI_CLEAR_TERMINAL = "\033[2J"


Rgb = Tuple[int, int, int]
Frame = List[List[Rgb]]
AudioFunc = Callable[[], None]
TargetResolution = Tuple[Optional[int], Optional[int]]


def max_video_size() -> Tuple[int, int]:
    height = os.get_terminal_size().lines - 1
    width = os.get_terminal_size().columns // 2
    return height, width


def ansi_backround_rgb(rgb: Rgb) -> str:
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def convert_frame(frame: Frame, offset: Tuple[int, int]) -> str:
    vertical_offset = "\n" * offset[0]
    horizontal_offset = " " * offset[1]

    output = [ANSI_RESET_CURSOR, vertical_offset]
    for row in frame:
        output.append("\n")
        output.append(horizontal_offset)
        for pixel in row:
            output.append(ansi_backround_rgb(pixel) + "  ")
        output.append(ANSI_RESET_STYLE)
    return "".join(output)


def calculate_offset(video: VideoFileClip) -> Tuple[int, int]:
    terminal_height, terminal_width = max_video_size()

    if terminal_height > video.h:
        vertical_offset = (terminal_height - video.h) // 2
        return vertical_offset, 0

    horisontal_offset = terminal_width - video.w
    return 0, horisontal_offset


@contextmanager
def hidden_cursor():
    print(ANSI_HIDE_CURSOR, end="")
    try:
        yield
    finally:
        print(ANSI_SHOW_CURSOR, end="")


@dataclass(frozen=True)
class AudioInterface:
    play: AudioFunc
    pause: AudioFunc
    unpause: AudioFunc


class Player:
    def __init__(
        self,
        video: VideoFileClip,
        audio_interface: AudioInterface,
        offset: Tuple[int, int],
        enable_pause: bool,
    ) -> None:
        self.video = video
        self.frame_rate = video.fps
        self.frame_time_s = 1 / self.frame_rate
        self.offset = offset
        self.audio_interface = audio_interface
        self.enable_pause = enable_pause
        self.is_paused = False
        self.start_time = 0
        self.pause_time = None
        self.check_paused_time_s = self.frame_time_s
        self.setup_keyboard_listener()

    def setup_keyboard_listener(self) -> None:
        if not self.enable_pause:
            return

        def on_press(key) -> None:
            if key == keyboard.Key.space:
                self.toggle_pause()

        keyboard.Listener(on_press=on_press).start()

    def toggle_pause(self) -> None:
        if self.is_paused:
            assert isinstance(self.pause_time, float)
            self.audio_interface.unpause()
            self.start_time += time() - self.pause_time
            self.pause_time = None
        else:
            self.audio_interface.pause()
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
        self.audio_interface.play()
        print(ANSI_CLEAR_TERMINAL)
        with hidden_cursor():
            for i, frame in enumerate(self.video.iter_frames()):
                self.handle_pause()
                correction_s = self.calculate_correction_s(frame_index=i)
                if correction_s + self.frame_time_s < 0:
                    continue
                printable_frame = convert_frame(frame, offset=self.offset)
                print(printable_frame, end="")
                self.frame_sleep(correction_s)


@contextmanager
def load_audio(
    video: VideoFileClip,
) -> Generator[AudioInterface, None, None]:
    audio_path = None
    try:
        audio = video.audio
        if not audio:
            yield AudioInterface(lambda: None, lambda: None, lambda: None)
        else:
            audio_fd, audio_path = mkstemp(suffix=".mp3")
            os.close(audio_fd)
            audio.write_audiofile(audio_path)

            mixer.init()
            mixer.music.load(audio_path)

            yield AudioInterface(
                play=mixer.music.play,
                pause=mixer.music.pause,
                unpause=mixer.music.unpause,
            )
    finally:
        mixer.music.unload()
        mixer.quit()
        if audio_path:
            os.remove(audio_path)


def calculate_target_resolution(path: str) -> TargetResolution:
    terminal_height, terminal_width = max_video_size()
    terminal_aspect_ratio = terminal_width / terminal_height

    with load_video(path) as video:
        if terminal_aspect_ratio < video.aspect_ratio:
            return None, terminal_width
        return terminal_height, None


class DummyVideo:
    def close(self) -> None:
        pass


@contextmanager
def load_video(
    path: str,
    frame_rate: Optional[int] = None,
    target_resolution: Optional[TargetResolution] = None,
) -> Generator[VideoFileClip, None, None]:
    video = DummyVideo()
    try:
        video = VideoFileClip(
            path,
            target_resolution=target_resolution,
            resize_algorithm="fast_bilinear",
        )
        if frame_rate is not None:
            video = video.set_fps(frame_rate)
        yield video
    finally:
        video.close()


def play_video(
    path: str,
    frame_rate: Optional[int],
    enable_pause: bool = True,
) -> None:
    target_resolution = calculate_target_resolution(path)
    with load_video(
        path, frame_rate=frame_rate, target_resolution=target_resolution
    ) as video, load_audio(video) as audio_interface:
        offset = calculate_offset(video)
        Player(
            video=video,
            audio_interface=audio_interface,
            offset=offset,
            enable_pause=enable_pause,
        ).play()


def main() -> None:
    default_frame_rate = 24

    parser = ArgumentParser()
    parser.add_argument("path", help="path to video file")
    parser.add_argument(
        "-f",
        "--frame-rate",
        type=int,
        default=default_frame_rate,
        help=f"default {default_frame_rate}",
    )
    parser.add_argument("-n", "--no-pause", action="store_true", help="disable pausing")
    arguments = parser.parse_args()

    play_video(
        arguments.path,
        frame_rate=arguments.frame_rate,
        enable_pause=not arguments.no_pause,
    )


if __name__ == "__main__":
    main()
