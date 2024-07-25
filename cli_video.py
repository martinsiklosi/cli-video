import os
import sys
from time import time, sleep
from typing import Tuple, Callable

from moviepy.video.fx.all import resize  # type: ignore
from moviepy.editor import VideoFileClip
from tqdm import tqdm
import numpy as np
import pygame


os.system("")  # For ANSI escape sequences to be processed correctly


NAIVE_FRAME_RATE = 12
FRAME_TIME_S = 1 / NAIVE_FRAME_RATE
ANSI_RESET = "\033[0m"


def clear_terminal() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def ansi_backround_rgb(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"\033[48;2;{r};{g};{b}m"


def terminal_size() -> Tuple[int, int]:
    """Returns (width, heigth) of terminal"""
    height = os.get_terminal_size().lines
    width = os.get_terminal_size().columns // 2
    return width, height


def convert_frame(frame: np.ndarray) -> str:
    output = ""
    for row in frame:
        for pixel in row:
            output += ansi_backround_rgb(pixel)
            output += "  "
        output += ANSI_RESET
        output += "\n"
    return output.strip()


def load_video(path: str, frame_rate: int, size: Tuple[int, int]) -> VideoFileClip:
    video = VideoFileClip(path)
    video = video.set_fps(frame_rate)
    video = resize(video, newsize=size)
    return video


def create_frames(video: VideoFileClip) -> list[str]:
    frame_count = video.duration * NAIVE_FRAME_RATE
    return [
        convert_frame(frame) for frame in tqdm(video.iter_frames(), total=frame_count)
    ]


def play_frames(frames: list[str]) -> None:
    for frame in frames:
        before = time()
        print(frame, end="")
        after = time()
        print_time = after - before
        sleep(max(FRAME_TIME_S - print_time, 0))


def play_audio(video: VideoFileClip, temp_file_name: str) -> Callable[[], None]:
    audio = video.audio
    assert audio  # TODO add support for video without audio
    pygame.mixer.init()
    temp_audio_path = temp_file_name
    audio.write_audiofile(temp_audio_path)
    pygame.mixer.music.load(temp_audio_path)
    pygame.mixer.music.play()
    return pygame.mixer.music.unload


def play_video(path: str) -> None:
    video = load_video(path, frame_rate=NAIVE_FRAME_RATE, size=terminal_size())
    frames = create_frames(video)

    temp_file_name = "cli-video-temp-audio.mp3"
    if os.path.exists(temp_file_name):
        raise FileExistsError("Temporary sound file already exists.")
    try:
        clear_terminal()
        unload_audio = play_audio(video, temp_file_name)
        play_frames(frames)
        clear_terminal()
    finally:
        unload_audio()
        os.remove(temp_file_name)


def main() -> None:
    if len(sys.argv) != 2:
        print("USAGE: python cli_video.py <path>")
        return

    print("Loading video...")
    play_video(sys.argv[1])


if __name__ == "__main__":
    main()
