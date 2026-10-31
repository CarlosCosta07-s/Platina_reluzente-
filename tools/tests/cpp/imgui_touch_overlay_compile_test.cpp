#include "imgui_touch_overlay.hpp"

int main() {
    Platina::MobileInput::VirtualTouchControls controls;
    controls.Configure(390, 844, {0, 24, 0, 18});
    Platina::MobileInput::DrawVirtualTouchControls(controls);
    return 0;
}
