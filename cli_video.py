import os
from io import BytesIO
from argparse import ArgumentParser
from shutil import get_terminal_size
from time import perf_counter, sleep
from contextlib import contextmanager
from dataclasses import dataclass, field
from collections.abc import Generator, Callable

from moviepy.editor import AudioFileClip, VideoFileClip
from pynput import keyboard
from pygame import mixer
import soundfile


DEFAULT_FRAME_RATE = 24
DEFAULT_VOLUME = 0.7
VOLUME_INCREMENT = 0.1


# For ANSI escape sequences to be processed correctly on windows
os.system("")


ANSI_RESET_STYLE = "\033[0m"
ANSI_RESET_CURSOR = "\033[H"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"
ANSI_CLEAR_TERMINAL = "\033[2J"


Rgb = tuple[int, int, int]
Frame = list[list[Rgb]]
AudioFunc = Callable[[], None]
TargetResolution = tuple[int | None, int | None]


def ansi_backround_rgb(rgb: Rgb) -> str:
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def to_printable_frame(frame: Frame, offset: tuple[int, int]) -> str:
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


def terminal_pixel_size() -> tuple[int, int]:
    height = get_terminal_size().lines - 1
    width = get_terminal_size().columns // 2
    return height, width


def calculate_offset(video: VideoFileClip) -> tuple[int, int]:
    terminal_height, terminal_width = terminal_pixel_size()

    if terminal_height > video.h:
        vertical_offset = (terminal_height - video.h) // 2
        return vertical_offset, 0

    horisontal_offset = terminal_width - video.w
    return 0, horisontal_offset


@contextmanager
def hidden_cursor() -> Generator[None, None, None]:
    print(ANSI_HIDE_CURSOR, end="")
    try:
        yield
    finally:
        print(ANSI_SHOW_CURSOR, end="")


@dataclass(frozen=True)
class AudioInterface:
    play: AudioFunc = field(default=lambda: None)
    pause: AudioFunc = field(default=lambda: None)
    unpause: AudioFunc = field(default=lambda: None)
    raise_volume: AudioFunc = field(default=lambda: None)
    lower_volume: AudioFunc = field(default=lambda: None)


class Player:
    def __init__(
        self,
        video: VideoFileClip,
        audio_interface: AudioInterface,
        offset: tuple[int, int],
        enable_keyboard: bool,
    ) -> None:
        self.video = video
        self.frame_time_s = 1 / self.video.fps
        self.offset = offset
        self.audio_interface = audio_interface
        self.enable_keyboard = enable_keyboard
        self.is_paused = False
        self.start_time = 0
        self.pause_time = None
        self.check_paused_time_s = self.frame_time_s
        self.setup_keyboard_listener()

    def setup_keyboard_listener(self) -> None:
        if not self.enable_keyboard:
            return

        def on_press(key) -> None:
            match key:
                case keyboard.Key.space:
                    self.toggle_pause()
                case keyboard.Key.up:
                    self.audio_interface.raise_volume()
                case keyboard.Key.down:
                    self.audio_interface.lower_volume()
        keyboard.Listener(on_press=on_press).start()

    def toggle_pause(self) -> None:
        if self.is_paused:
            assert isinstance(self.pause_time, float)
            self.audio_interface.unpause()
            self.start_time += perf_counter() - self.pause_time
            self.pause_time = None
        else:
            self.audio_interface.pause()
            self.pause_time = perf_counter()
        self.is_paused = not self.is_paused

    def calculate_correction_s(self, frame_index: int) -> float:
        elapsed_time = perf_counter() - self.start_time
        theoretical_elapsed_time = frame_index / self.video.fps
        return theoretical_elapsed_time - elapsed_time

    def frame_sleep(self, correction_s: float) -> None:
        sleep_time_s = self.frame_time_s + correction_s
        sleep(max(sleep_time_s, 0))

    def block_while_paused(self) -> None:
        while self.is_paused:
            sleep(self.check_paused_time_s)
        # Make sure start_time has been corrected
        while self.pause_time is not None:
            sleep(self.check_paused_time_s)

    def play(self) -> None:
        self.start_time = perf_counter()
        self.audio_interface.play()
        print(ANSI_CLEAR_TERMINAL)
        with hidden_cursor():
            for i, frame in enumerate(self.video.iter_frames()):
                self.block_while_paused()
                correction_s = self.calculate_correction_s(frame_index=i)
                if correction_s + self.frame_time_s < 0:
                    continue
                printable_frame = to_printable_frame(frame, offset=self.offset)
                print(printable_frame, end="")
                self.frame_sleep(correction_s)


def audio_to_wav(audio: AudioFileClip) -> BytesIO:
    soundarray = audio.to_soundarray()
    bytes_io = BytesIO()
    soundfile.write(
        bytes_io,
        soundarray,
        samplerate=audio.fps,
        format="wav"
    )
    bytes_io.seek(0)
    return bytes_io


@contextmanager
def load_audio(
    video: VideoFileClip,
    volume: float | None,
) -> Generator[AudioInterface, None, None]:
    audio = video.audio
    if not audio:
        yield AudioInterface()
        return

    mixer.init()
    mixer.music.load(audio_to_wav(audio), namehint="wav")
    mixer.music.set_volume(volume if volume is not None else DEFAULT_VOLUME)

    def raise_volume() -> None:
        proposed_volume = mixer.music.get_volume() + VOLUME_INCREMENT
        max_volume = 1.0
        new_volume = min(proposed_volume, max_volume)
        mixer.music.set_volume(new_volume)

    def lower_volume() -> None:
        proposed_volume = mixer.music.get_volume() - VOLUME_INCREMENT
        min_volume = 0.0
        new_volume = max(proposed_volume, min_volume)
        mixer.music.set_volume(new_volume)

    try:
        yield AudioInterface(
            play=mixer.music.play,
            pause=mixer.music.pause,
            unpause=mixer.music.unpause,
            raise_volume=raise_volume,
            lower_volume=lower_volume
        )
    finally:
        mixer.music.unload()
        mixer.quit()


def calculate_target_resolution(path: str) -> TargetResolution:
    terminal_height, terminal_width = terminal_pixel_size()
    terminal_aspect_ratio = terminal_width / terminal_height

    with load_video(path) as video:
        if terminal_aspect_ratio < video.aspect_ratio:
            return None, terminal_width
        return terminal_height, None


@contextmanager
def load_video(
    path: str,
    frame_rate: int | None = None,
    target_resolution: TargetResolution | None = None,
    mute: bool = False
) -> Generator[VideoFileClip, None, None]:
    video = VideoFileClip(
        path,
        target_resolution=target_resolution,
        resize_algorithm="fast_bilinear",
    )
    if frame_rate is not None:
        video = video.set_fps(frame_rate)
    if mute:
        video = video.without_audio()

    try:
        yield video
    finally:
        video.close()


def play_video(
    path: str,
    frame_rate: int | None,
    volume: float | None,
    mute: bool = False,
    enable_keyboard: bool = True,
) -> None:
    target_resolution = calculate_target_resolution(path)
    with load_video(
        path, frame_rate=frame_rate, target_resolution=target_resolution, mute=mute
    ) as video, load_audio(video, volume=volume) as audio_interface:
        offset = calculate_offset(video)
        Player(
            video=video,
            audio_interface=audio_interface,
            offset=offset,
            enable_keyboard=enable_keyboard,
        ).play()


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("path", help="path to video file")
    parser.add_argument(
        "-f",
        "--frame-rate",
        type=int,
        default=DEFAULT_FRAME_RATE,
        help=f"default {DEFAULT_FRAME_RATE}",
    )
    parser.add_argument(
        "-v",
        "--volume",
        type=float,
        default=DEFAULT_VOLUME,
        help=f"between 0.0 and 1.0, default {DEFAULT_VOLUME}",
    )
    parser.add_argument("-m", "--mute", action="store_true", help="disable audio")
    parser.add_argument("-d", "--disable-keyboard", action="store_true", help="disable keyboard controls")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"ERROR: Path does not exist ({args.path}).")
        exit(1)

    play_video(
        args.path,
        frame_rate=args.frame_rate,
        volume=args.volume,
        mute=args.mute,
        enable_keyboard=not args.disable_keyboard,
    )


if __name__ == "__main__":
    main()
