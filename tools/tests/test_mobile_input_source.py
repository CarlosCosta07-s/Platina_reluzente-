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
    installed_overlay_header = root / "libraries" / "sim" / "src" / "virtual_touch_controls.hpp"
    repo_root = Path(__file__).resolve().parents[2]
    tracked_header = repo_root / "mobile" / "input" / "touch_input_router.hpp"
    tracked_overlay_header = repo_root / "mobile" / "input" / "virtual_touch_controls.hpp"
    gui_header_path = root / "include" / "simulator" / "sim_gui.hpp"
    gui_source_path = root / "libraries" / "sim" / "src" / "sim_gui.cpp"

    for path, label in (
        (source_path, "prepared sim_main.cpp"),
        (installed_header, "installed touch router header"),
        (installed_overlay_header, "installed virtual-control header"),
        (gui_header_path, "prepared simulator GUI header"),
        (gui_source_path, "prepared simulator GUI source"),
    ):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"Missing or unsafe {label}: {path}")

    if installed_header.read_bytes() != tracked_header.read_bytes():
        raise SystemExit("The prepared libntr router header differs from the tracked source.")
    if installed_overlay_header.read_bytes() != tracked_overlay_header.read_bytes():
        raise SystemExit("The prepared virtual-control header differs from the tracked source.")

    gui_header = gui_header_path.read_text(encoding="utf-8")
    gui_source = gui_source_path.read_text(encoding="utf-8")
    source = source_path.read_text(encoding="utf-8")
    required = (
        MARKER,
        '#include "touch_input_router.hpp"',
        '#include "virtual_touch_controls.hpp"',
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
        "SIM::GUI::TouchOverlayHitTest(position.x, position.y)",
        "SIM::GUI::TouchOverlayCancelAll();",
        "SIM::GUI::ConfigureTouchOverlay(windowWidth, windowHeight, 0, 0, 0, 0)",
        "SIM::GUI::TouchOverlayBegin(true",
        "SIM::GUI::TouchOverlayBegin(false",
        "SIM::GUI::TouchOverlayMove(true",
        "SIM::GUI::TouchOverlayMove(false",
        "SIM::GUI::TouchOverlayEnd(true",
        "SIM::GUI::TouchOverlayEnd(false",
        "SIM::GUI::TouchOverlayPressedMask()",
        "touchOverlayBasePadKeys",
        "touchOverlayBaseXy",
        "VirtualButtonA",
        "VirtualButtonB",
        "VirtualButtonX",
        "VirtualButtonY",
        "VirtualButtonL",
        "VirtualButtonR",
        "VirtualButtonStart",
        "VirtualButtonSelect",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise SystemExit("Prepared SDL input source is missing required tokens: " + ", ".join(missing))

    if "SDL_GetMouseState(&x, &y)" in source:
        raise SystemExit("Legacy polling path remains after the event-driven router patch.")
    if "static u8 isMouseDown = 0;" in source:
        raise SystemExit("Legacy single-pointer mouse state remains after the router patch.")
    if "static u64 map(u64 x, u64 in_min" in source:
        raise SystemExit("Unused legacy mouse coordinate mapper remains after the event-driven router patch.")

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

    gui_required = (
        "virtual_touch_controls.hpp",
        "DrawMobileTouchOverlay()",
        "ImGui::GetForegroundDrawList()",
        "AddCircleFilled",
        "TouchOverlayHitTest(int x, int y)",
        "TouchOverlayBegin(bool finger",
        "TouchOverlayMove(bool finger",
        "TouchOverlayEnd(bool finger",
        "TouchOverlayCancelAll()",
        "TouchOverlayPressedMask()",
        "sTouchControls.Claims({x, y})",
        "VirtualButtonUp",
        "VirtualButtonDown",
        "VirtualButtonLeft",
        "VirtualButtonRight",
    )
    missing_gui = [token for token in gui_required if token not in gui_header + gui_source]
    if missing_gui:
        raise SystemExit("Prepared ImGui overlay is missing required tokens: " + ", ".join(missing_gui))
    if "return SIM::GUI::TouchOverlayHitTest(position.x, position.y);" not in source:
        raise SystemExit("The SDL hit-test is not connected to the responsive virtual-control layout.")

    print("Pinned SDL touch input and ImGui overlay source contracts passed.")
    print("Verified mouse/finger routing, per-pointer capture, DS geometry, and virtual pad register mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
