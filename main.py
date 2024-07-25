import os


os.system("")  # For ANSI escape sequences to be processed correctly


ANSI_RESET = "\033[0m"
UNICODE_BLOCK = "\u2588"


def ansi_rgb(r: int, g: int, b: int) -> str:
    foreground = f"\033[38;2;{r};{g};{b}m"
    background = f"\033[48;2;{r};{g};{b}m"   
    return foreground + background


def pixel(r: int, g: int, b: int) -> str:
    return f"{ansi_rgb(r, g, b)}{2*UNICODE_BLOCK}{ANSI_RESET}"


print(*[pixel(i, 0, 0) for i in range(0, 256, 4)], sep="")
print(*[pixel(0, i, 0) for i in range(0, 256, 4)], sep="")
print(*[pixel(0, 0, i) for i in range(0, 256, 4)], sep="")
print(*[pixel(0, i, i) for i in range(0, 256, 4)], sep="")
print(*[pixel(i, 0, i) for i in range(0, 256, 4)], sep="")
print(*[pixel(i, i, 0) for i in range(0, 256, 4)], sep="")
print(*[pixel(i, i, i) for i in range(0, 256, 4)], sep="")