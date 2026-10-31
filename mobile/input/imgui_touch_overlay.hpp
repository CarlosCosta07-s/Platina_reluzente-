#pragma once

#include "virtual_touch_controls.hpp"
#include <simulator/imgui/imgui.hpp>

namespace Platina::MobileInput {

inline ImVec2 TouchPointToImVec2(const Point &point) {
    return ImVec2(static_cast<float>(point.x), static_cast<float>(point.y));
}

inline void DrawTouchLabel(
    ImDrawList *drawList,
    const ImVec2 &center,
    const char *label,
    ImU32 color
) {
    const ImVec2 textSize = ImGui::CalcTextSize(label);
    drawList->AddText(
        ImVec2(center.x - textSize.x * 0.5f, center.y - textSize.y * 0.5f),
        color,
        label
    );
}

inline void DrawTouchDirection(
    ImDrawList *drawList,
    const ImVec2 &center,
    float radius,
    const char *label,
    bool pressed
) {
    const ImU32 fill = pressed
        ? IM_COL32(55, 155, 235, 205)
        : IM_COL32(18, 25, 38, 155);
    drawList->AddCircleFilled(center, radius, fill, 20);
    drawList->AddCircle(
        center, radius, IM_COL32(220, 235, 250, 145), 20, 1.5f
    );
    DrawTouchLabel(
        drawList, center, label, IM_COL32(255, 255, 255, 235)
    );
}

// Draw only on mobile builds. The desktop simulator retains its original UI
// and input path. Call this between ImGui::NewFrame() and ImGui::Render().
inline void DrawVirtualTouchControls(VirtualTouchControls &controls) {
#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
    if (!controls.IsConfigured()) {
        return;
    }

    const auto visuals = controls.Visuals();
    ImDrawList *drawList = ImGui::GetForegroundDrawList();
    const auto &dpad = visuals[0];
    const ImVec2 dpadCenter = TouchPointToImVec2(dpad.center);

    drawList->AddCircleFilled(
        dpadCenter,
        dpad.radius,
        IM_COL32(12, 18, 30, 112),
        40
    );
    drawList->AddCircle(
        dpadCenter,
        dpad.radius,
        IM_COL32(225, 235, 248, 145),
        40,
        2.0f
    );

    const std::uint16_t pressed = controls.PressedMask();
    const float offset = dpad.radius * 0.53f;
    const float directionRadius = dpad.radius * 0.29f;

    DrawTouchDirection(
        drawList,
        ImVec2(dpadCenter.x, dpadCenter.y - offset),
        directionRadius,
        "U",
        (pressed & VirtualButtonUp) != 0
    );
    DrawTouchDirection(
        drawList,
        ImVec2(dpadCenter.x, dpadCenter.y + offset),
        directionRadius,
        "D",
        (pressed & VirtualButtonDown) != 0
    );
    DrawTouchDirection(
        drawList,
        ImVec2(dpadCenter.x - offset, dpadCenter.y),
        directionRadius,
        "L",
        (pressed & VirtualButtonLeft) != 0
    );
    DrawTouchDirection(
        drawList,
        ImVec2(dpadCenter.x + offset, dpadCenter.y),
        directionRadius,
        "R",
        (pressed & VirtualButtonRight) != 0
    );

    for (std::size_t index = 1; index < visuals.size(); ++index) {
        const auto &button = visuals[index];
        const ImVec2 center = TouchPointToImVec2(button.center);
        const ImU32 fill = button.pressed
            ? IM_COL32(45, 145, 225, 205)
            : IM_COL32(18, 25, 38, 145);
        drawList->AddCircleFilled(center, button.radius, fill, 32);
        drawList->AddCircle(
            center,
            button.radius,
            IM_COL32(225, 235, 248, 160),
            32,
            1.5f
        );
        DrawTouchLabel(
            drawList,
            center,
            button.label,
            IM_COL32(255, 255, 255, 238)
        );
    }
#else
    (void)controls;
#endif
}

} // namespace Platina::MobileInput
