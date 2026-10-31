#pragma once

#include "touch_input_router.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>

namespace Platina::MobileInput {

enum class VirtualControl : std::uint8_t {
    DPad,
    A,
    B,
    X,
    Y,
    L,
    R,
    Start,
    Select,
};

enum VirtualButtonMask : std::uint16_t {
    VirtualButtonNone   = 0,
    VirtualButtonA      = 1u << 0,
    VirtualButtonB      = 1u << 1,
    VirtualButtonX      = 1u << 2,
    VirtualButtonY      = 1u << 3,
    VirtualButtonL      = 1u << 4,
    VirtualButtonR      = 1u << 5,
    VirtualButtonUp     = 1u << 6,
    VirtualButtonDown   = 1u << 7,
    VirtualButtonLeft   = 1u << 8,
    VirtualButtonRight  = 1u << 9,
    VirtualButtonStart  = 1u << 10,
    VirtualButtonSelect = 1u << 11,
};

struct SafeAreaInsets {
    int left = 0;
    int top = 0;
    int right = 0;
    int bottom = 0;
};

struct VirtualControlVisual {
    VirtualControl control = VirtualControl::A;
    Point center;
    float radius = 0.0f;
    const char *label = "";
    bool pressed = false;
};

struct VirtualControlLayout {
    int width = 0;
    int height = 0;
    SafeAreaInsets insets;
    bool landscape = false;
    bool valid = false;
    Point dpadCenter;
    float dpadRadius = 0.0f;
    std::array<VirtualControlVisual, 8> buttons{};
};

class VirtualTouchControls {
public:
    void Configure(int width, int height, SafeAreaInsets insets = {}) {
        layout_ = {};
        layout_.width = width;
        layout_.height = height;
        layout_.insets = NormalizeInsets(width, height, insets);
        if (width <= 0 || height <= 0) {
            return;
        }

        const int usableWidth = width - layout_.insets.left - layout_.insets.right;
        const int usableHeight = height - layout_.insets.top - layout_.insets.bottom;
        if (usableWidth < 160 || usableHeight < 160) {
            return;
        }

        layout_.landscape = usableWidth >= usableHeight;
        const float shortSide = static_cast<float>(std::min(usableWidth, usableHeight));
        layout_.dpadRadius = std::clamp(shortSide * 0.135f, 28.0f, 60.0f);

        const int left = layout_.insets.left;
        const int top = layout_.insets.top;
        const int right = width - layout_.insets.right;
        const int bottom = height - layout_.insets.bottom;
        const float usableW = static_cast<float>(usableWidth);
        const float usableH = static_cast<float>(usableHeight);

        const float dpadX = ClampCenter(
            static_cast<float>(left) + usableW * 0.18f,
            static_cast<float>(left) + layout_.dpadRadius + 8.0f,
            static_cast<float>(right) - layout_.dpadRadius - 8.0f);
        const float dpadY = ClampCenter(
            static_cast<float>(top) + usableH * (layout_.landscape ? 0.70f : 0.77f),
            static_cast<float>(top) + layout_.dpadRadius + 8.0f,
            static_cast<float>(bottom) - layout_.dpadRadius - 8.0f);
        layout_.dpadCenter = {static_cast<int>(std::lround(dpadX)),
                              static_cast<int>(std::lround(dpadY))};

        const float faceRadius = std::clamp(shortSide * 0.064f, 18.0f, 31.0f);
        const float shoulderRadius = std::clamp(shortSide * 0.055f, 17.0f, 27.0f);
        const float systemRadius = std::clamp(shortSide * 0.048f, 15.0f, 23.0f);

        const float faceClusterRadius = faceRadius * 2.85f;
        const float faceCenterX = ClampCenter(
            static_cast<float>(left) + usableW * 0.82f,
            static_cast<float>(left) + faceClusterRadius + 6.0f,
            static_cast<float>(right) - faceClusterRadius - 6.0f);
        const float faceCenterY = ClampCenter(
            static_cast<float>(top) + usableH * (layout_.landscape ? 0.70f : 0.77f),
            static_cast<float>(top) + faceClusterRadius + 6.0f,
            static_cast<float>(bottom) - faceClusterRadius - 6.0f);

        const float faceOffset = faceRadius * 1.82f;
        SetButton(0, VirtualControl::A, faceCenterX, faceCenterY + faceOffset,
                  faceRadius, "A");
        SetButton(1, VirtualControl::B, faceCenterX + faceOffset, faceCenterY,
                  faceRadius, "B");
        SetButton(2, VirtualControl::X, faceCenterX - faceOffset, faceCenterY,
                  faceRadius, "X");
        SetButton(3, VirtualControl::Y, faceCenterX, faceCenterY - faceOffset,
                  faceRadius, "Y");

        const float shoulderY = static_cast<float>(top)
            + std::max(shoulderRadius + 8.0f, usableH * 0.15f);
        SetButton(4, VirtualControl::L,
                  static_cast<float>(left) + usableW * 0.17f,
                  shoulderY, shoulderRadius, "L");
        SetButton(5, VirtualControl::R,
                  static_cast<float>(right) - usableW * 0.17f,
                  shoulderY, shoulderRadius, "R");

        const float systemY = static_cast<float>(bottom)
            - std::max(systemRadius + 8.0f, usableH * 0.075f);
        SetButton(6, VirtualControl::Select,
                  static_cast<float>(left) + usableW * 0.43f,
                  systemY, systemRadius, "SELECT");
        SetButton(7, VirtualControl::Start,
                  static_cast<float>(left) + usableW * 0.57f,
                  systemY, systemRadius, "START");

        layout_.valid = true;
    }

    bool IsConfigured() const noexcept {
        return layout_.valid;
    }

    const VirtualControlLayout &Layout() const noexcept {
        return layout_;
    }

    bool Claims(const Point &position) const noexcept {
        if (!layout_.valid) {
            return false;
        }
        if (InsideCircle(position, layout_.dpadCenter, layout_.dpadRadius)) {
            return true;
        }
        for (const auto &button : layout_.buttons) {
            if (InsideCircle(position, button.center, button.radius)) {
                return true;
            }
        }
        return false;
    }

    bool Begin(const PointerId &pointer, const Point &position) {
        if (Find(pointer) != activePointers_.end()) {
            return true;
        }
        if (!layout_.valid) {
            return false;
        }

        ActivePointer active;
        active.id = pointer;
        active.position = position;

        if (InsideCircle(position, layout_.dpadCenter, layout_.dpadRadius)) {
            active.control = VirtualControl::DPad;
            activePointers_.push_back(active);
            return true;
        }

        for (const auto &button : layout_.buttons) {
            if (InsideCircle(position, button.center, button.radius)) {
                active.control = button.control;
                activePointers_.push_back(active);
                return true;
            }
        }
        return false;
    }

    bool Move(const PointerId &pointer, const Point &position) {
        auto active = Find(pointer);
        if (active == activePointers_.end()) {
            return false;
        }
        active->position = position;
        return true;
    }

    bool End(const PointerId &pointer) {
        auto active = Find(pointer);
        if (active == activePointers_.end()) {
            return false;
        }
        activePointers_.erase(active);
        return true;
    }

    void CancelAll() noexcept {
        activePointers_.clear();
    }

    std::uint16_t PressedMask() const noexcept {
        std::uint16_t result = VirtualButtonNone;
        for (const auto &active : activePointers_) {
            if (active.control == VirtualControl::DPad) {
                if (InsideCircle(active.position, layout_.dpadCenter, layout_.dpadRadius)) {
                    result = static_cast<std::uint16_t>(result | DPadMask(active.position));
                }
                continue;
            }

            const VirtualControlVisual *button = FindButton(active.control);
            if (button != nullptr
                && InsideCircle(active.position, button->center, button->radius)) {
                result = static_cast<std::uint16_t>(result | ButtonMask(active.control));
            }
        }
        return result;
    }

    std::array<VirtualControlVisual, 9> Visuals() const noexcept {
        std::array<VirtualControlVisual, 9> result{};
        const std::uint16_t pressed = PressedMask();
        result[0] = {VirtualControl::DPad, layout_.dpadCenter,
                     layout_.dpadRadius, "D-PAD",
                     HasDPadPointer()};
        for (std::size_t index = 0; index < layout_.buttons.size(); ++index) {
            result[index + 1] = layout_.buttons[index];
            result[index + 1].pressed =
                (pressed & ButtonMask(layout_.buttons[index].control)) != 0;
        }
        return result;
    }

    std::size_t ActivePointerCount() const noexcept {
        return activePointers_.size();
    }

private:
    struct ActivePointer {
        PointerId id;
        VirtualControl control = VirtualControl::A;
        Point position;
    };

    static SafeAreaInsets NormalizeInsets(
        int width, int height, SafeAreaInsets insets) noexcept {
        insets.left = std::clamp(insets.left, 0, std::max(0, width));
        insets.right = std::clamp(insets.right, 0, std::max(0, width - insets.left));
        insets.top = std::clamp(insets.top, 0, std::max(0, height));
        insets.bottom = std::clamp(insets.bottom, 0, std::max(0, height - insets.top));
        return insets;
    }

    static float ClampCenter(float value, float minimum, float maximum) noexcept {
        if (minimum > maximum) {
            return (minimum + maximum) * 0.5f;
        }
        return std::clamp(value, minimum, maximum);
    }

    static bool InsideCircle(
        const Point &point, const Point &center, float radius) noexcept {
        const float dx = static_cast<float>(point.x - center.x);
        const float dy = static_cast<float>(point.y - center.y);
        return dx * dx + dy * dy <= radius * radius;
    }

    static std::uint16_t ButtonMask(VirtualControl control) noexcept {
        switch (control) {
        case VirtualControl::A: return VirtualButtonA;
        case VirtualControl::B: return VirtualButtonB;
        case VirtualControl::X: return VirtualButtonX;
        case VirtualControl::Y: return VirtualButtonY;
        case VirtualControl::L: return VirtualButtonL;
        case VirtualControl::R: return VirtualButtonR;
        case VirtualControl::Start: return VirtualButtonStart;
        case VirtualControl::Select: return VirtualButtonSelect;
        case VirtualControl::DPad: return VirtualButtonNone;
        }
        return VirtualButtonNone;
    }

    std::uint16_t DPadMask(const Point &position) const noexcept {
        const float dx = static_cast<float>(position.x - layout_.dpadCenter.x);
        const float dy = static_cast<float>(position.y - layout_.dpadCenter.y);
        const float deadZone = layout_.dpadRadius * 0.22f;
        std::uint16_t result = VirtualButtonNone;
        if (dx <= -deadZone) result |= VirtualButtonLeft;
        if (dx >= deadZone) result |= VirtualButtonRight;
        if (dy <= -deadZone) result |= VirtualButtonUp;
        if (dy >= deadZone) result |= VirtualButtonDown;
        return result;
    }

    bool HasDPadPointer() const noexcept {
        for (const auto &active : activePointers_) {
            if (active.control == VirtualControl::DPad) {
                return true;
            }
        }
        return false;
    }

    const VirtualControlVisual *FindButton(VirtualControl control) const noexcept {
        for (const auto &button : layout_.buttons) {
            if (button.control == control) {
                return &button;
            }
        }
        return nullptr;
    }

    void SetButton(std::size_t index, VirtualControl control,
                   float x, float y, float radius, const char *label) noexcept {
        layout_.buttons[index] = {
            control,
            {static_cast<int>(std::lround(x)), static_cast<int>(std::lround(y))},
            radius,
            label,
            false,
        };
    }

    auto Find(const PointerId &pointer) noexcept {
        return std::find_if(activePointers_.begin(), activePointers_.end(),
            [&pointer](const ActivePointer &active) { return active.id == pointer; });
    }

    VirtualControlLayout layout_;
    std::vector<ActivePointer> activePointers_;
};

} // namespace Platina::MobileInput
