#pragma once

#ifndef PINNEDWINDOWS_H
#define PINNEDWINDOWS_H

#include <string>
#include <unordered_set>
#include <hyprland/src/defines.hpp>
#include <hyprland/src/Compositor.hpp>

using namespace Hyprutils::Memory;

namespace PinnedWindows {
    // Store pinned windows by their address
    extern std::unordered_set<PHLWINDOW> pinnedWindows;

    // Pin/unpin operations
    bool pinWindow(PHLWINDOW window);
    bool unpinWindow(PHLWINDOW window);
    bool togglePinWindow(PHLWINDOW window);
    bool isWindowPinned(PHLWINDOW window);

    // Move all pinned windows to the current virtual desktop
    // Each window stays on its original monitor
    void movePinnedWindowsToActiveDesk(int targetVdeskId, const std::unordered_map<const CSharedPointer<CMonitor>, WORKSPACEID>& layout);

    // Clean up invalid (closed) windows from the pinned set
    void cleanupInvalidWindows();

    // Get the focused window or window by regex
    PHLWINDOW getWindowFromArg(const std::string& arg);
}

#endif
