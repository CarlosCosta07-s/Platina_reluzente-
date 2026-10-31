from __future__ import annotations

import argparse
from pathlib import Path


PINNED_REVISION = "1555d911ac80c0190ac1c321f99f1323de8b3c09"
MARKER = "PLATINA_MOBILE_TOUCH_INPUT_ROUTER_V1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the prepared pinned SDL touch source.")
    parser.add_argument("libntr_root", type=Path)
    args = parser.parse_args()

    root = args.libntr_root.resolve()
    source_path = root / "libraries" / "sim" / "src" / "sim_main.cpp"
    installed_header = root / "libraries" / "sim" / "src" / "touch_input_router.hpp"
    repo_root = Path(__file__).resolve().parents[2]
    tracked_header = repo_root / "mobile" / "input" / "touch_input_router.hpp"

    if not source_path.is_file() or source_path.is_symlink():
        raise SystemExit(f"Missing or unsafe prepared sim_main.cpp: {source_path}")
    if not installed_header.is_file() or installed_header.is_symlink():
        raise SystemExit(f"Missing or unsafe installed router header: {installed_header}")
    if installed_header.read_bytes() != tracked_header.read_bytes():
        raise SystemExit("The prepared libntr router header differs from the tracked source.")

    source = source_path.read_text(encoding="utf-8")
    required = (
        MARKER,
        '#include "touch_input_router.hpp"',
        "static Platina::MobileInput::TouchInputRouter s_TouchInputRouter;",
        "SIM_GetTouchPanel()",
        "SIM_TouchOverlayClaims(position)",
        "SDL_MOUSEBUTTONDOWN",
        "SDL_MOUSEMOTION",
        "SDL_MOUSEBUTTONUP",
        "SDL_TOUCH_MOUSEID",
        "SDL_FINGERDOWN",
        "SDL_FINGERMOTION",
        "SDL_FINGERUP",
        "Event.tfinger.touchId",
        "Event.tfinger.fingerId",
        "SDL_WINDOWEVENT_FOCUS_LOST",
        "SDL_WINDOWEVENT_HIDDEN",
        "SDL_WINDOWEVENT_MINIMIZED",
        "SDL_APP_WILLENTERBACKGROUND",
        "SIM_CancelTouchInput();",
        "SIM_NormalizedTouchCoordinate(Event.tfinger.x, windowWidth)",
        "SIM_NormalizedTouchCoordinate(Event.tfinger.y, windowHeight)",
        "SIM_NDS_SCREEN_WIDTH",
        "SIM_NDS_SCREEN_HEIGHT",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise SystemExit("Prepared SDL input source is missing required tokens: " + ", ".join(missing))

    if "SDL_GetMouseState(&x, &y)" in source:
        raise SystemExit("Legacy polling path remains after the event-driven router patch.")
    if "static u8 isMouseDown = 0;" in source:
        raise SystemExit("Legacy single-pointer mouse state remains after the router patch.")

    # The existing viewport/screen-layout calculation must remain the source
    # of DS touch geometry; the patch must not replace or duplicate it.
    for token in (
        "if (s_SIM_config.swapScreens)",
        "SIM_CONFIG_SCREEN_LAYOUT_VERTICAL",
        "SIM_CONFIG_SCREEN_LAYOUT_HORIZONTAL",
        "SIM_CONFIG_SCREEN_LAYOUT_LARGE",
        "s_TouchPanelCoords[0] = viewX",
        "s_TouchPanelCoords[3] = viewY + viewHeight",
        "SDL_GetWindowSize(window, &windowWidth, &windowHeight);",
    ):
        if token not in source:
            raise SystemExit(f"Existing DS panel geometry changed or disappeared: {token}")

    print("Pinned SDL touch input source contract passed.")
    print("Verified mouse/finger routing, touch-ID preservation, focus cancellation, and DS panel geometry.")
    print("The overlay hit-test is intentionally a false-returning hook until the overlay is implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
