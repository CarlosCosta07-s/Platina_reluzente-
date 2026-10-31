#include "mobile/input/virtual_touch_controls.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

using Platina::MobileInput::Point;
using Platina::MobileInput::PointerId;
using Platina::MobileInput::PointerSource;
using Platina::MobileInput::SafeAreaInsets;
using Platina::MobileInput::VirtualButtonA;
using Platina::MobileInput::VirtualButtonB;
using Platina::MobileInput::VirtualButtonDown;
using Platina::MobileInput::VirtualButtonLeft;
using Platina::MobileInput::VirtualButtonRight;
using Platina::MobileInput::VirtualButtonSelect;
using Platina::MobileInput::VirtualButtonStart;
using Platina::MobileInput::VirtualButtonUp;
using Platina::MobileInput::VirtualButtonX;
using Platina::MobileInput::VirtualButtonY;
using Platina::MobileInput::VirtualControl;
using Platina::MobileInput::VirtualTouchControls;

namespace {

void Require(bool condition, const std::string &message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

PointerId Finger(std::int64_t device, std::int64_t finger) {
    return {PointerSource::Finger, device, finger};
}

const Platina::MobileInput::VirtualControlVisual &FindVisual(
    const Platina::MobileInput::VirtualControlLayout &layout,
    VirtualControl control) {
    for (const auto &button : layout.buttons) {
        if (button.control == control) {
            return button;
        }
    }
    throw std::runtime_error("Requested virtual control visual was not found.");
}

void TestPortraitLayoutFitsInsideSafeArea() {
    VirtualTouchControls controls;
    controls.Configure(390, 844, {0, 32, 0, 28});
    const auto &layout = controls.Layout();

    Require(layout.valid, "Portrait layout was not created.");
    Require(!layout.landscape, "Portrait orientation was misdetected.");
    Require(layout.insets.top == 32 && layout.insets.bottom == 28,
            "Safe area insets were not retained.");

    const int left = layout.insets.left;
    const int top = layout.insets.top;
    const int right = 390 - layout.insets.right;
    const int bottom = 844 - layout.insets.bottom;

    Require(layout.dpadCenter.x - layout.dpadRadius >= left,
            "D-pad crosses the left safe boundary.");
    Require(layout.dpadCenter.y - layout.dpadRadius >= top,
            "D-pad crosses the top safe boundary.");
    Require(layout.dpadCenter.x + layout.dpadRadius <= right,
            "D-pad crosses the right safe boundary.");
    Require(layout.dpadCenter.y + layout.dpadRadius <= bottom,
            "D-pad crosses the bottom safe boundary.");

    for (const auto &button : layout.buttons) {
        Require(button.center.x - button.radius >= left - 1,
                "A virtual button crosses the left safe boundary.");
        Require(button.center.y - button.radius >= top - 1,
                "A virtual button crosses the top safe boundary.");
        Require(button.center.x + button.radius <= right + 1,
                "A virtual button crosses the right safe boundary.");
        Require(button.center.y + button.radius <= bottom + 1,
                "A virtual button crosses the bottom safe boundary.");
    }
}

void TestLandscapeLayoutAdaptsAndStaysInsideInsets() {
    VirtualTouchControls controls;
    controls.Configure(844, 390, {24, 12, 18, 20});
    const auto &layout = controls.Layout();

    Require(layout.valid && layout.landscape,
            "Landscape layout was not created or orientation is wrong.");
    Require(layout.dpadCenter.x - layout.dpadRadius >= 24,
            "Landscape D-pad overlaps left safe area.");
    Require(layout.dpadCenter.y - layout.dpadRadius >= 12,
            "Landscape D-pad overlaps top safe area.");
    Require(layout.dpadCenter.x + layout.dpadRadius <= 826,
            "Landscape D-pad overlaps right safe area.");
    Require(layout.dpadCenter.y + layout.dpadRadius <= 370,
            "Landscape D-pad overlaps bottom safe area.");
}

void TestActionButtonsCaptureAndRelease() {
    VirtualTouchControls controls;
    controls.Configure(390, 844);
    const auto &a = FindVisual(controls.Layout(), VirtualControl::A);
    const auto &b = FindVisual(controls.Layout(), VirtualControl::B);
    const auto aFinger = Finger(1, 10);

    Require(controls.Claims(a.center), "A button was not hit-testable.");
    Require(controls.Begin(aFinger, a.center), "A button did not capture pointer.");
    Require((controls.PressedMask() & VirtualButtonA) != 0,
            "A button did not become pressed.");

    controls.Move(aFinger, b.center);
    Require((controls.PressedMask() & VirtualButtonA) == 0,
            "A button remained pressed after dragging outside its hit area.");
    Require((controls.PressedMask() & VirtualButtonB) == 0,
            "A captured A pointer activated a neighboring B button.");

    controls.Move(aFinger, a.center);
    Require((controls.PressedMask() & VirtualButtonA) != 0,
            "Captured A pointer could not re-enter its original hit area.");
    Require(controls.End(aFinger), "A pointer did not release.");
    Require(controls.PressedMask() == 0, "A button remained pressed after release.");
}

void TestTwoPointersCanHoldIndependentButtons() {
    VirtualTouchControls controls;
    controls.Configure(390, 844);
    const auto &a = FindVisual(controls.Layout(), VirtualControl::A);
    const auto &b = FindVisual(controls.Layout(), VirtualControl::B);
    const auto aFinger = Finger(2, 1);
    const auto bFinger = Finger(2, 2);

    Require(controls.Begin(aFinger, a.center), "First action pointer was not captured.");
    Require(controls.Begin(bFinger, b.center), "Second action pointer was not captured.");
    const auto pressed = controls.PressedMask();
    Require((pressed & (VirtualButtonA | VirtualButtonB))
                == (VirtualButtonA | VirtualButtonB),
            "Independent action buttons were not held simultaneously.");

    controls.End(aFinger);
    Require((controls.PressedMask() & VirtualButtonA) == 0,
            "A remained held after its owner released.");
    Require((controls.PressedMask() & VirtualButtonB) != 0,
            "Releasing A incorrectly released B.");
    controls.End(bFinger);
    Require(controls.PressedMask() == 0,
            "Action buttons remained pressed after both pointers released.");
}

void TestDPadSupportsEightDirectionsAndDeadZone() {
    VirtualTouchControls controls;
    controls.Configure(390, 844);
    const auto center = controls.Layout().dpadCenter;
    const auto radius = controls.Layout().dpadRadius;
    const auto finger = Finger(3, 1);

    Require(controls.Begin(finger, center), "D-pad did not capture at its center.");
    Require((controls.PressedMask()
                & (VirtualButtonUp | VirtualButtonDown
                   | VirtualButtonLeft | VirtualButtonRight)) == 0,
            "D-pad dead zone generated a direction.");

    controls.Move(finger, {center.x + static_cast<int>(radius * 0.5f),
                           center.y - static_cast<int>(radius * 0.5f)});
    Require((controls.PressedMask() & (VirtualButtonUp | VirtualButtonRight))
                == (VirtualButtonUp | VirtualButtonRight),
            "D-pad did not generate a diagonal direction.");

    controls.Move(finger, {center.x - static_cast<int>(radius * 0.8f), center.y});
    Require((controls.PressedMask() & VirtualButtonLeft) != 0,
            "D-pad did not change direction during a held gesture.");
    Require((controls.PressedMask() & VirtualButtonRight) == 0,
            "D-pad retained a stale direction after movement.");

    controls.Move(finger, {center.x + static_cast<int>(radius * 2.0f), center.y});
    Require(controls.PressedMask() == 0,
            "D-pad remained active after the pointer left its hit circle.");
    controls.End(finger);
}

void TestMultiplePointersOnSameButtonUseAggregateState() {
    VirtualTouchControls controls;
    controls.Configure(390, 844);
    const auto &a = FindVisual(controls.Layout(), VirtualControl::A);
    const auto first = Finger(4, 1);
    const auto second = Finger(4, 2);

    controls.Begin(first, a.center);
    controls.Begin(second, a.center);
    controls.End(first);
    Require((controls.PressedMask() & VirtualButtonA) != 0,
            "Releasing one of two A pointers released the other pointer's hold.");
    controls.End(second);
    Require((controls.PressedMask() & VirtualButtonA) == 0,
            "A remained held after its final pointer released.");
}

void TestStartAndSelectHaveDistinctBindings() {
    VirtualTouchControls controls;
    controls.Configure(844, 390);
    const auto &start = FindVisual(controls.Layout(), VirtualControl::Start);
    const auto &select = FindVisual(controls.Layout(), VirtualControl::Select);

    const auto startFinger = Finger(5, 1);
    const auto selectFinger = Finger(5, 2);
    Require(controls.Begin(startFinger, start.center), "Start was not hit-testable.");
    Require(controls.Begin(selectFinger, select.center), "Select was not hit-testable.");
    const auto pressed = controls.PressedMask();
    Require((pressed & (VirtualButtonStart | VirtualButtonSelect))
                == (VirtualButtonStart | VirtualButtonSelect),
            "Start and Select did not retain separate button bindings.");
    controls.CancelAll();
    Require(controls.PressedMask() == 0 && controls.ActivePointerCount() == 0,
            "CancelAll did not release system buttons.");
}

void TestInvalidAndTinyViewportsAreDisabled() {
    VirtualTouchControls controls;
    controls.Configure(0, 0);
    Require(!controls.IsConfigured(), "Zero-sized viewport was accepted.");
    Require(!controls.Claims({0, 0}), "Invalid viewport claimed a touch.");

    controls.Configure(120, 140);
    Require(!controls.IsConfigured(), "Viewport too small for controls was accepted.");

    controls.Configure(390, 844, {500, 0, 0, 0});
    Require(!controls.IsConfigured(), "Insets leaving no usable width were accepted.");
}

void TestVisualStateReflectsPressedButtons() {
    VirtualTouchControls controls;
    controls.Configure(390, 844);
    const auto &x = FindVisual(controls.Layout(), VirtualControl::X);
    const auto finger = Finger(6, 1);

    controls.Begin(finger, x.center);
    const auto visuals = controls.Visuals();
    bool xWasPressed = false;
    for (const auto &visual : visuals) {
        if (visual.control == VirtualControl::X) {
            xWasPressed = visual.pressed;
        }
    }
    Require(xWasPressed, "Overlay visual state did not reflect pressed X.");
}

} // namespace

int main() {
    try {
        TestPortraitLayoutFitsInsideSafeArea();
        TestLandscapeLayoutAdaptsAndStaysInsideInsets();
        TestActionButtonsCaptureAndRelease();
        TestTwoPointersCanHoldIndependentButtons();
        TestDPadSupportsEightDirectionsAndDeadZone();
        TestMultiplePointersOnSameButtonUseAggregateState();
        TestStartAndSelectHaveDistinctBindings();
        TestInvalidAndTinyViewportsAreDisabled();
        TestVisualStateReflectsPressedButtons();
    } catch (const std::exception &error) {
        std::cerr << "VirtualTouchControls test failed: " << error.what() << '\n';
        return 1;
    }

    std::cout << "VirtualTouchControls host contract tests passed (9 scenarios).\n";
    return 0;
}
