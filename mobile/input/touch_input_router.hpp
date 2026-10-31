#pragma once

#include <algorithm>
#include <cstdint>
#include <vector>

namespace Platina::MobileInput {

enum class PointerSource : std::uint8_t {
    Finger,
    Mouse,
};

struct PointerId {
    PointerSource source = PointerSource::Finger;
    std::int64_t deviceId = 0;
    std::int64_t pointerId = 0;

    bool operator==(const PointerId &other) const noexcept {
        return source == other.source
            && deviceId == other.deviceId
            && pointerId == other.pointerId;
    }

    bool operator!=(const PointerId &other) const noexcept {
        return !(*this == other);
    }
};

struct Point {
    int x = 0;
    int y = 0;
};

struct Rect {
    int left = 0;
    int top = 0;
    int right = 0;
    int bottom = 0;

    bool IsValid() const noexcept {
        return right > left && bottom > top;
    }

    bool Contains(const Point &point) const noexcept {
        return IsValid()
            && point.x >= left && point.x <= right
            && point.y >= top && point.y <= bottom;
    }
};

struct TouchPanel {
    Rect bounds;
    int screenWidth = 0;
    int screenHeight = 0;

    bool IsValid() const noexcept {
        return bounds.IsValid() && screenWidth > 0 && screenHeight > 0;
    }
};

enum class TouchTarget : std::uint8_t {
    Ignored,
    VirtualControls,
    DsStylus,
};

// Describes one routed pointer update in window coordinates. dsTouchActive is
// true only while the current DS stylus owner is inside the existing DS panel
// rectangle. Ownership itself is retained until End() or CancelAll().
struct TouchUpdate {
    PointerId pointer;
    TouchTarget target = TouchTarget::Ignored;
    Point windowPosition;
    bool dsTouchActive = false;
    int dsX = -1;
    int dsY = -1;
    bool ended = false;
};

class TouchInputRouter {
public:
    // overlayClaimsTouch must be the result of the virtual-control layer's hit
    // test. Overlay capture has priority even when its hit area overlaps the DS
    // panel. The chosen target is immutable for the lifetime of this pointer.
    TouchUpdate Begin(
        const PointerId &pointer,
        const Point &position,
        const TouchPanel &panel,
        bool overlayClaimsTouch
    ) {
        ActivePointer *existing = Find(pointer);
        if (existing != nullptr) {
            existing->position = position;
            return MakeUpdate(*existing, panel);
        }

        TouchTarget target = TouchTarget::Ignored;
        if (overlayClaimsTouch) {
            target = TouchTarget::VirtualControls;
        } else if (!hasStylusOwner_
                   && (pointer.source == PointerSource::Mouse
                       || (panel.IsValid() && panel.bounds.Contains(position)))) {
            // Desktop mouse interaction historically began on any mouse-down,
            // then became a DS touch whenever the pointer crossed the lower
            // screen bounds. Preserve that drag-into-panel behavior.
            target = TouchTarget::DsStylus;
            stylusOwner_ = pointer;
            hasStylusOwner_ = true;
        }

        activePointers_.push_back({pointer, target, position});
        return MakeUpdate(activePointers_.back(), panel);
    }

    // A pointer never changes target after Begin(). In particular, an ignored
    // contact cannot slide into the DS panel and steal the stylus, and an
    // overlay contact cannot leak into the game when dragged off its control.
    TouchUpdate Move(
        const PointerId &pointer,
        const Point &position,
        const TouchPanel &panel
    ) {
        ActivePointer *active = Find(pointer);
        if (active == nullptr) {
            return {pointer, TouchTarget::Ignored, position, false, -1, -1, false};
        }

        active->position = position;
        return MakeUpdate(*active, panel);
    }

    TouchUpdate End(const PointerId &pointer, const TouchPanel &panel) {
        for (auto iterator = activePointers_.begin(); iterator != activePointers_.end(); ++iterator) {
            if (iterator->id != pointer) {
                continue;
            }

            TouchUpdate update = MakeUpdate(*iterator, panel);
            update.dsTouchActive = false;
            update.ended = true;

            if (hasStylusOwner_ && stylusOwner_ == pointer) {
                hasStylusOwner_ = false;
                stylusOwner_ = {};
            }

            activePointers_.erase(iterator);
            return update;
        }

        return {pointer, TouchTarget::Ignored, {}, false, -1, -1, true};
    }

    // Lifecycle/focus cancellation must release every captured source, not
    // merely forget the DS stylus. The caller forwards ended updates to the
    // overlay and resets the native DS touch state before discarding the list.
    std::vector<TouchUpdate> CancelAll(const TouchPanel &panel) {
        std::vector<TouchUpdate> cancelled;
        cancelled.reserve(activePointers_.size());
        for (const ActivePointer &active : activePointers_) {
            TouchUpdate update = MakeUpdate(active, panel);
            update.dsTouchActive = false;
            update.ended = true;
            cancelled.push_back(update);
        }

        activePointers_.clear();
        hasStylusOwner_ = false;
        stylusOwner_ = {};
        return cancelled;
    }

    bool HasStylusOwner() const noexcept {
        return hasStylusOwner_;
    }

    bool IsStylusOwner(const PointerId &pointer) const noexcept {
        return hasStylusOwner_ && stylusOwner_ == pointer;
    }

    std::size_t PointerCount() const noexcept {
        return activePointers_.size();
    }

private:
    struct ActivePointer {
        PointerId id;
        TouchTarget target;
        Point position;
    };

    ActivePointer *Find(const PointerId &pointer) noexcept {
        for (ActivePointer &active : activePointers_) {
            if (active.id == pointer) {
                return &active;
            }
        }
        return nullptr;
    }

    TouchUpdate MakeUpdate(const ActivePointer &active, const TouchPanel &panel) const noexcept {
        TouchUpdate update;
        update.pointer = active.id;
        update.target = active.target;
        update.windowPosition = active.position;

        if (active.target != TouchTarget::DsStylus
            || !panel.IsValid()
            || !panel.bounds.Contains(active.position)) {
            return update;
        }

        update.dsTouchActive = true;
        update.dsX = MapToScreen(
            active.position.x, panel.bounds.left, panel.bounds.right, panel.screenWidth);
        update.dsY = MapToScreen(
            active.position.y, panel.bounds.top, panel.bounds.bottom, panel.screenHeight);
        return update;
    }

    static int MapToScreen(int value, int minimum, int maximum, int dimension) noexcept {
        const std::int64_t offset = static_cast<std::int64_t>(value) - minimum;
        const std::int64_t span = static_cast<std::int64_t>(maximum) - minimum;
        const std::int64_t scaled = (offset * dimension) / span;
        return static_cast<int>(std::clamp<std::int64_t>(scaled, 0, dimension - 1));
    }

    std::vector<ActivePointer> activePointers_;
    PointerId stylusOwner_{};
    bool hasStylusOwner_ = false;
};

} // namespace Platina::MobileInput
