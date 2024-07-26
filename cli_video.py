import os
import sys
from time import time, sleep
from typing import Tuple, Callable

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
    return height, width


def convert_frame(frame: np.ndarray) -> str:
    output = []
    for row in frame:
        output.append("\n")
        for pixel in row:
            output.append(ansi_backround_rgb(pixel))
            output.append("  ")
        output.append(ANSI_RESET)
    return "".join(output)


def load_video(path: str, frame_rate: int, size: Tuple[int, int]) -> VideoFileClip:
    video = VideoFileClip(
        path, target_resolution=size, resize_algorithm="fast_bilinear"
    )
    video = video.set_fps(frame_rate)
    return video


def create_frames(video: VideoFileClip) -> list[str]:
    frame_count = round(video.duration * NAIVE_FRAME_RATE)
    print("Loading frames")
    frames = [frame for frame in tqdm(video.iter_frames(), total=frame_count)]
    print("Processing frames")
    return [convert_frame(frame) for frame in tqdm(frames)]


def play_frames(frames: list[str]) -> None:
    for frame in frames:
        before = time()
        print(frame, end="")
        after = time()
        print_time = after - before
        sleep(max(FRAME_TIME_S - print_time, 0))


def play_audio(video: VideoFileClip) -> Callable[[], None]:
    audio = video.audio
    if not audio:
        return lambda: None

    temp_audio_path = "cli-video-temp-audio.mp3"
    if os.path.exists(temp_audio_path):
        raise FileExistsError("Temporary sound file already exists.")
    audio.write_audiofile(temp_audio_path)

    pygame.mixer.init()
    pygame.mixer.music.load(temp_audio_path)
    pygame.mixer.music.play()

    def cleanup() -> None:
        pygame.mixer.music.unload()
        os.remove(temp_audio_path)

    return cleanup


def play_video(path: str) -> None:
    video = load_video(path, frame_rate=NAIVE_FRAME_RATE, size=terminal_size())
    frames = create_frames(video)
    try:
        audio_cleanup = play_audio(video)
        clear_terminal()
        play_frames(frames)
        clear_terminal()
    finally:
        audio_cleanup()
        video.close()


def main() -> None:
    # TODO choose framerate from cli (maybe with a --frame-rate)
    if len(sys.argv) != 2:
        print("USAGE: python cli_video.py <path>")
        return
    play_video(sys.argv[1])


if __name__ == "__main__":
    main()
