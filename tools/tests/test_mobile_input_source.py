from __future__ import annotations

import argparse
from pathlib import Path


PINNED_REVISION = "1555d911ac80c0190ac1c321f99f1323de8b3c09"
MARKER = "PLATINA_MOBILE_TOUCH_INPUT_ROUTER_V1"


def require_tokens(source: str, tokens: tuple[str, ...], label: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise SystemExit(f"{label} is missing required tokens: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate prepared SDL input and ImGui overlay in pinned libntr.")
    parser.add_argument("libntr_root", type=Path)
    args = parser.parse_args()

    root = args.libntr_root.resolve()
    source_path = root / "libraries" / "sim" / "src" / "sim_main.cpp"
    installed_header = root / "libraries" / "sim" / "src" / "touch_input_router.hpp"
    installed_overlay_header = root / "libraries" / "sim" / "src" / "virtual_touch_controls.hpp"
    installed_imgui_overlay_header = root / "libraries" / "sim" / "src" / "imgui_touch_overlay.hpp"
    repo_root = Path(__file__).resolve().parents[2]
    tracked_header = repo_root / "mobile" / "input" / "touch_input_router.hpp"
    tracked_overlay_header = repo_root / "mobile" / "input" / "virtual_touch_controls.hpp"
    tracked_imgui_overlay_header = repo_root / "mobile" / "input" / "imgui_touch_overlay.hpp"

    for path, label in (
        (source_path, "prepared sim_main.cpp"),
        (installed_header, "installed touch router header"),
        (installed_overlay_header, "installed virtual-control header"),
        (installed_imgui_overlay_header, "installed ImGui overlay header"),
    ):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"Missing or unsafe {label}: {path}")

    if installed_header.read_bytes() != tracked_header.read_bytes():
        raise SystemExit("The prepared libntr router header differs from the tracked source.")
    if installed_overlay_header.read_bytes() != tracked_overlay_header.read_bytes():
        raise SystemExit("The prepared virtual-control header differs from the tracked source.")
    if installed_imgui_overlay_header.read_bytes() != tracked_imgui_overlay_header.read_bytes():
        raise SystemExit("The prepared ImGui overlay header differs from the tracked source.")

    source = source_path.read_text(encoding="utf-8")
    require_tokens(
        source,
        (
            MARKER,
            '#include "touch_input_router.hpp"',
            '#include "virtual_touch_controls.hpp"',
            '#include "imgui_touch_overlay.hpp"',
            "static Platina::MobileInput::TouchInputRouter s_TouchInputRouter;",
            "static Platina::MobileInput::VirtualTouchControls s_TouchControls;",
            "SIM_GetTouchPanel()",
            "return s_TouchControls.Claims(position);",
            "s_TouchControls.CancelAll();",
            "s_TouchControls.Configure(windowWidth, windowHeight, {});",
            "SDL_MOUSEBUTTONDOWN",
            "SDL_MOUSEMOTION",
            "SDL_MOUSEBUTTONUP",
            "SDL_TOUCH_MOUSEID",
            "SDL_FINGERDOWN",
            "SDL_FINGERMOTION",
            "SDL_FINGERUP",
            "Event.tfinger.touchId",
            "Event.tfinger.fingerId",
            "s_TouchControls.Begin(pointer, position);",
            "s_TouchControls.Move(pointer, position);",
            "s_TouchControls.End(pointer);",
            "s_TouchControls.PressedMask()",
            "s_reg_PAD_KEYINPUT = touchOverlayBasePadKeys;",
            "touchOverlayBaseXy",
            "VirtualButtonA",
            "VirtualButtonB",
            "VirtualButtonX",
            "VirtualButtonY",
            "VirtualButtonL",
            "VirtualButtonR",
            "VirtualButtonStart",
            "VirtualButtonSelect",
            "SDL_WINDOWEVENT_FOCUS_LOST",
            "SDL_WINDOWEVENT_HIDDEN",
            "SDL_WINDOWEVENT_MINIMIZED",
            "SDL_APP_WILLENTERBACKGROUND",
            "SIM_CancelTouchInput();",
            "SIM_NormalizedTouchCoordinate(Event.tfinger.x, windowWidth)",
            "SIM_NormalizedTouchCoordinate(Event.tfinger.y, windowHeight)",
            "SIM_NDS_SCREEN_WIDTH",
            "SIM_NDS_SCREEN_HEIGHT",
        ),
        "Prepared SDL input source",
    )

    require_tokens(
        source,
        (
            "Platina::MobileInput::DrawVirtualTouchControls(s_TouchControls);",
            "s_TouchControls.Configure(windowWidth, windowHeight, {});",
            "#include \"imgui_touch_overlay.hpp\"",
        ),
        "Runtime ImGui overlay connection",
    )
    imgui_overlay = installed_imgui_overlay_header.read_text(encoding="utf-8")
    require_tokens(
        imgui_overlay,
        (
            "inline void DrawVirtualTouchControls(VirtualTouchControls &controls)",
            "ImGui::GetForegroundDrawList()",
            "ImGui::CalcTextSize(label)",
            "drawList->AddCircleFilled",
            "drawList->AddCircle",
            "drawList->AddText",
            "VirtualButtonUp",
            "VirtualButtonDown",
            "VirtualButtonLeft",
            "VirtualButtonRight",
            "#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)",
        ),
        "Shared ImGui overlay renderer",
    )

    if "SIM::GUI::TouchOverlay" in source:
        raise SystemExit("Legacy GUI bridge calls remain; the overlay must use the simulator's active ImGui frame.")
    if "SDL_GetMouseState(&x, &y)" in source:
        raise SystemExit("Legacy mouse polling path remains after the event-driven router patch.")
    if "static u8 isMouseDown = 0;" in source:
        raise SystemExit("Legacy single-pointer mouse state remains after the router patch.")
    if "static u64 map(u64 x, u64 in_min" in source:
        raise SystemExit("Unused legacy mouse coordinate mapper remains after the event-driven router patch.")

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

    print("Pinned SDL touch input and ImGui overlay source contracts passed.")
    print("Verified per-pointer routing, DS panel geometry, ImGui rendering, and DS virtual-button register mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
