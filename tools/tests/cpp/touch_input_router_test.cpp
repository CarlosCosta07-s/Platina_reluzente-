#include "mobile/input/touch_input_router.hpp"

#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using Platina::MobileInput::Point;
using Platina::MobileInput::PointerId;
using Platina::MobileInput::PointerSource;
using Platina::MobileInput::Rect;
using Platina::MobileInput::TouchInputRouter;
using Platina::MobileInput::TouchPanel;
using Platina::MobileInput::TouchTarget;

namespace {

void Require(bool condition, const std::string &message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

PointerId Finger(std::int64_t device, std::int64_t finger) {
    return {PointerSource::Finger, device, finger};
}

PointerId Mouse(std::int64_t device) {
    return {PointerSource::Mouse, device, 0};
}

TouchPanel DefaultPanel() {
    return {{100, 50, 356, 242}, 256, 192};
}

void TestOverlayHasFirstRefusal() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId finger = Finger(1, 11);

    // This point is inside the DS panel, but the overlay owns the overlapping
    // region and must capture the pointer before the DS stylus can see it.
    const auto down = router.Begin(finger, {200, 120}, panel, true);
    Require(down.target == TouchTarget::VirtualControls,
            "Overlay did not receive first refusal.");
    Require(!down.dsTouchActive, "Overlay contact leaked into DS touch.");
    Require(!router.HasStylusOwner(), "Overlay capture incorrectly claimed the stylus.");

    const auto move = router.Move(finger, {220, 140}, panel);
    Require(move.target == TouchTarget::VirtualControls,
            "Overlay pointer changed target while moving.");
    Require(!move.dsTouchActive, "Overlay pointer leaked into the DS panel on motion.");

    const auto up = router.End(finger, panel);
    Require(up.target == TouchTarget::VirtualControls && up.ended,
            "Overlay release was not routed to its original target.");
    Require(router.PointerCount() == 0, "Overlay pointer was not removed on release.");
}

void TestOverlayAndDsStylusCanBeUsedTogether() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId overlayFinger = Finger(1, 1);
    const PointerId stylusFinger = Finger(1, 2);

    const auto overlay = router.Begin(overlayFinger, {160, 100}, panel, true);
    const auto stylus = router.Begin(stylusFinger, {228, 146}, panel, false);

    Require(overlay.target == TouchTarget::VirtualControls,
            "First finger did not remain on virtual controls.");
    Require(stylus.target == TouchTarget::DsStylus && stylus.dsTouchActive,
            "Second finger did not independently become the DS stylus.");
    Require(stylus.dsX == 128 && stylus.dsY == 96,
            "DS coordinate conversion did not map the panel center correctly.");
    Require(router.IsStylusOwner(stylusFinger),
            "Stylus owner ID was not preserved independently of the overlay finger.");

    const auto overlayMove = router.Move(overlayFinger, {180, 120}, panel);
    Require(overlayMove.target == TouchTarget::VirtualControls,
            "Overlay finger was affected by the stylus finger.");
    Require(router.End(stylusFinger, panel).ended,
            "DS stylus finger could not be released.");
    Require(!router.HasStylusOwner(), "DS stylus owner remained after release.");
    Require(router.End(overlayFinger, panel).ended,
            "Overlay finger could not be released after stylus release.");
}

void TestStylusOwnershipIsStableAndExclusive() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId owner = Finger(3, 21);
    const PointerId contender = Finger(3, 22);
    const PointerId nextOwner = Finger(3, 23);

    const auto first = router.Begin(owner, {180, 100}, panel, false);
    Require(first.target == TouchTarget::DsStylus, "First DS contact did not own stylus.");

    const auto second = router.Begin(contender, {200, 120}, panel, false);
    Require(second.target == TouchTarget::Ignored,
            "A second DS contact stole an already-owned stylus.");

    const auto secondMove = router.Move(contender, {220, 140}, panel);
    Require(secondMove.target == TouchTarget::Ignored,
            "Ignored contact was promoted after moving inside the DS panel.");

    const auto outside = router.Move(owner, {400, 300}, panel);
    Require(outside.target == TouchTarget::DsStylus && !outside.dsTouchActive,
            "Stylus ownership was lost when its finger temporarily left the panel.");
    Require(router.IsStylusOwner(owner), "Stylus owner changed while outside the panel.");

    const auto reentered = router.Move(owner, {228, 146}, panel);
    Require(reentered.target == TouchTarget::DsStylus && reentered.dsTouchActive,
            "Original stylus owner could not re-enter the DS panel.");
    Require(reentered.dsX == 128 && reentered.dsY == 96,
            "DS coordinates were not restored after re-entry.");

    router.End(owner, panel);
    Require(!router.HasStylusOwner(), "Stylus ownership was not cleared on finger-up.");

    const auto third = router.Begin(nextOwner, {228, 146}, panel, false);
    Require(third.target == TouchTarget::DsStylus,
            "New contact could not acquire the released stylus.");
}

void TestPointerIdsIncludeSourceAndTouchDevice() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId fingerOnDeviceA = Finger(10, 7);
    const PointerId fingerOnDeviceB = Finger(11, 7);
    const PointerId mouse = Mouse(0);

    router.Begin(fingerOnDeviceA, {150, 100}, panel, true);
    router.Begin(fingerOnDeviceB, {228, 146}, panel, false);
    router.Begin(mouse, {210, 130}, panel, true);

    Require(router.PointerCount() == 3,
            "Pointer IDs collided across touch devices or input sources.");
    Require(router.Move(fingerOnDeviceA, {152, 102}, panel).target
                == TouchTarget::VirtualControls,
            "Device A finger state was overwritten.");
    Require(router.Move(fingerOnDeviceB, {230, 148}, panel).target
                == TouchTarget::DsStylus,
            "Device B finger state was overwritten.");
    Require(router.Move(mouse, {212, 132}, panel).target
                == TouchTarget::VirtualControls,
            "Mouse pointer state collided with a finger ID.");
}

void TestDesktopMouseCanDragIntoDsPanel() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId mouse = Mouse(0);

    const auto downOutside = router.Begin(mouse, {20, 20}, panel, false);
    Require(downOutside.target == TouchTarget::DsStylus,
            "Desktop mouse-down outside the DS panel did not retain stylus ownership.");
    Require(!downOutside.dsTouchActive,
            "Desktop mouse-down outside the DS panel activated a DS coordinate.");
    Require(router.HasStylusOwner(),
            "Desktop mouse-down outside the panel did not retain the pointer.");

    const auto draggedIntoPanel = router.Move(mouse, {228, 146}, panel);
    Require(draggedIntoPanel.target == TouchTarget::DsStylus
                && draggedIntoPanel.dsTouchActive,
            "Desktop mouse drag into the DS panel no longer activates touch.");
    Require(draggedIntoPanel.dsX == 128 && draggedIntoPanel.dsY == 96,
            "Desktop mouse drag did not map into DS screen coordinates.");

    const auto draggedOut = router.Move(mouse, {20, 20}, panel);
    Require(draggedOut.target == TouchTarget::DsStylus
                && !draggedOut.dsTouchActive,
            "Desktop mouse drag out of the DS panel did not release the DS contact.");
    Require(router.End(mouse, panel).ended,
            "Desktop mouse-up did not release its pointer capture.");
    Require(!router.HasStylusOwner(),
            "Desktop mouse-up did not clear stylus ownership.");
}

void TestPanelMappingClampsInclusiveEdges() {
    TouchInputRouter router;
    const TouchPanel panel{{0, 0, 256, 192}, 256, 192};
    const PointerId finger = Finger(1, 9);

    const auto topLeft = router.Begin(finger, {0, 0}, panel, false);
    Require(topLeft.dsTouchActive && topLeft.dsX == 0 && topLeft.dsY == 0,
            "Top-left panel coordinate did not map to DS origin.");

    const auto bottomRight = router.Move(finger, {256, 192}, panel);
    Require(bottomRight.dsTouchActive && bottomRight.dsX == 255 && bottomRight.dsY == 191,
            "Inclusive panel edge was not clamped to valid DS coordinates.");
    router.End(finger, panel);

    const TouchPanel invalidPanel{{0, 0, 0, 192}, 256, 192};
    const auto ignored = router.Begin(Finger(1, 10), {0, 10}, invalidPanel, false);
    Require(ignored.target == TouchTarget::Ignored,
            "Invalid touch panel bounds were accepted.");
}

void TestCancellationReleasesEveryCapturedPointer() {
    TouchInputRouter router;
    const TouchPanel panel = DefaultPanel();
    const PointerId overlay = Finger(4, 1);
    const PointerId stylus = Finger(4, 2);
    const PointerId ignored = Finger(4, 3);

    router.Begin(overlay, {150, 90}, panel, true);
    router.Begin(stylus, {228, 146}, panel, false);
    router.Begin(ignored, {240, 150}, panel, false);

    const std::vector<Platina::MobileInput::TouchUpdate> cancelled = router.CancelAll(panel);
    Require(cancelled.size() == 3, "Cancellation did not report every active pointer.");
    Require(!router.HasStylusOwner(), "Cancellation left a DS stylus owner behind.");
    Require(router.PointerCount() == 0, "Cancellation did not clear captured pointers.");

    int overlayReleases = 0;
    int stylusReleases = 0;
    for (const auto &update : cancelled) {
        Require(update.ended, "Cancelled pointer was not marked ended.");
        if (update.target == TouchTarget::VirtualControls) ++overlayReleases;
        if (update.target == TouchTarget::DsStylus) {
            ++stylusReleases;
            Require(!update.dsTouchActive, "Cancelled stylus was still reported as touching.");
        }
    }
    Require(overlayReleases == 1 && stylusReleases == 1,
            "Cancellation lost overlay or stylus release notification.");

    const auto reused = router.Begin(stylus, {228, 146}, panel, false);
    Require(reused.target == TouchTarget::DsStylus,
            "Pointer ID could not be reused after cancellation.");
}

} // namespace

int main() {
    try {
        TestOverlayHasFirstRefusal();
        TestOverlayAndDsStylusCanBeUsedTogether();
        TestStylusOwnershipIsStableAndExclusive();
        TestPointerIdsIncludeSourceAndTouchDevice();
        TestDesktopMouseCanDragIntoDsPanel();
        TestPanelMappingClampsInclusiveEdges();
        TestCancellationReleasesEveryCapturedPointer();
    } catch (const std::exception &error) {
        std::cerr << "TouchInputRouter test failed: " << error.what() << '\n';
        return 1;
    }

    std::cout << "TouchInputRouter host contract tests passed (7 scenarios).\n";
    return 0;
}
