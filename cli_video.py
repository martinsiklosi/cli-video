import os
import sys
from time import time, sleep
from typing import Tuple, Callable

from moviepy.editor import VideoFileClip
from tqdm import tqdm
import pygame


# For ANSI escape sequences to be processed correctly on windows
os.system("")


FRAME_RATE = 24
FRAME_TIME_S = 1 / FRAME_RATE
ANSI_RESET_STYLE = "\033[0m"
ANSI_RESET_CURSOR = "\033[H"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"


Rgb = Tuple[int, int, int]


def clear_terminal() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def terminal_size() -> Tuple[int, int]:
    height = os.get_terminal_size().lines - 1
    width = os.get_terminal_size().columns // 2
    return height, width


def ansi_backround_rgb(rgb: Rgb) -> str:
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def convert_frame(frame: list[list[Rgb]]) -> str:
    output = [ANSI_RESET_CURSOR]
    for row in frame:
        output.append("\n")
        for pixel in row:
            output.append(ansi_backround_rgb(pixel) + "  ")
        output.append(ANSI_RESET_STYLE)
    return "".join(output)


def create_frames(video: VideoFileClip) -> list[str]:
    frame_count = round(video.duration * FRAME_RATE)
    print("Loading frames")
    frames = [frame for frame in tqdm(video.iter_frames(), total=frame_count)]
    print("Processing frames")
    return [convert_frame(frame) for frame in tqdm(frames)]


def play_frames(frames: list[str]) -> Callable[[], None]:
    print(ANSI_HIDE_CURSOR)

    start_time = time()
    for i, frame in enumerate(frames):
        elapsed_time = time() - start_time
        theoretical_elapsed_time = i / FRAME_RATE
        correction = theoretical_elapsed_time - elapsed_time
        if abs(correction) > FRAME_TIME_S and i % FRAME_RATE != 0:
            continue

        print(frame, end="")
        sleep_time = FRAME_TIME_S + correction
        sleep(max(sleep_time, 0))

    def cleanup() -> None:
        print(ANSI_SHOW_CURSOR, end="")

    return cleanup


def play_audio(video: VideoFileClip) -> Callable[[], None]:
    audio = video.audio
    if not audio:
        return lambda: None

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

    return cleanup


def load_video(path: str, frame_rate: int, size: Tuple[int, int]) -> VideoFileClip:
    video = VideoFileClip(
        path, target_resolution=size, resize_algorithm="fast_bilinear"
    )
    video = video.set_fps(frame_rate)
    return video


def play_video(path: str) -> None:
    video = load_video(path, frame_rate=FRAME_RATE, size=terminal_size())
    frames = create_frames(video)
    try:
        audio_cleanup = play_audio(video)
        clear_terminal()
        frames_cleanup = play_frames(frames)
        clear_terminal()
    finally:
        audio_cleanup()
        frames_cleanup()
        video.close()


def main() -> None:
    if len(sys.argv) != 2 or "--help" in sys.argv:
        print("USAGE: python cli_video.py <path>")
        return
    play_video(sys.argv[1])


if __name__ == "__main__":
    main()
