def warn(text: str) -> str:
    return yellow_text(f"[WARN] {text}")


def yellow_text(text: str) -> str:
    return f"\033[1;33m{text}\033[0m"

def cyan_text(text: str) -> str:
    return f"\033[1;36m{text}\033[0m"

def green_text(text: str) -> str:
    return f"\033[1;32m{text}\033[0m"