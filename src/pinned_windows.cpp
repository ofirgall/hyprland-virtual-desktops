#include "pinned_windows.hpp"
#include "utils.hpp"
#include <format>
#include <hyprland/src/desktop/state/FocusState.hpp>

namespace PinnedWindows {
    std::unordered_set<PHLWINDOW> pinnedWindows;

    bool pinWindow(PHLWINDOW window) {
        if (!window) {
            printLog("Cannot pin null window", Log::WARN);
            return false;
        }

        if (pinnedWindows.contains(window)) {
            if (isVerbose())
                printLog(std::format("Window {} is already pinned", window->m_title));
            return false;
        }

        pinnedWindows.insert(window);
        if (isVerbose())
            printLog(std::format("Pinned window: {}", window->m_title));
        return true;
    }

    bool unpinWindow(PHLWINDOW window) {
        if (!window) {
            printLog("Cannot unpin null window", Log::WARN);
            return false;
        }

        if (!pinnedWindows.contains(window)) {
            if (isVerbose())
                printLog(std::format("Window {} is not pinned", window->m_title));
            return false;
        }

        pinnedWindows.erase(window);
        if (isVerbose())
            printLog(std::format("Unpinned window: {}", window->m_title));
        return true;
    }

    bool togglePinWindow(PHLWINDOW window) {
        if (!window) {
            printLog("Cannot toggle pin on null window", Log::WARN);
            return false;
        }

        if (pinnedWindows.contains(window)) {
            return unpinWindow(window);
        } else {
            return pinWindow(window);
        }
    }

    bool isWindowPinned(PHLWINDOW window) {
        return window && pinnedWindows.contains(window);
    }

    void movePinnedWindowsToActiveDesk(int targetVdeskId, const std::unordered_map<const CSharedPointer<CMonitor>, WORKSPACEID>& layout) {
        // First cleanup any invalid windows
        cleanupInvalidWindows();

        if (pinnedWindows.empty())
            return;

        if (isVerbose())
            printLog(std::format("Moving {} pinned windows to vdesk {}", pinnedWindows.size(), targetVdeskId));

        for (const auto& window : pinnedWindows) {
            if (!window || !g_pCompositor->windowExists(window))
                continue;

            // Get the monitor the window is currently on
            auto windowMonitor = window->m_monitor.lock();
            if (!windowMonitor || !windowMonitor->m_enabled)
                continue;

            // Find the workspace for this monitor in the target vdesk layout
            WORKSPACEID targetWorkspaceId = -1;
            for (const auto& [mon, wsId] : layout) {
                if (mon && mon->m_id == windowMonitor->m_id) {
                    targetWorkspaceId = wsId;
                    break;
                }
            }

            // If we couldn't find a matching monitor in the layout, skip
            if (targetWorkspaceId == -1) {
                if (isVerbose())
                    printLog(std::format("No workspace found for monitor {} in target layout", windowMonitor->m_name));
                continue;
            }

            // Check if window is already on the target workspace
            if (window->workspaceID() == targetWorkspaceId)
                continue;

            // Move the window to the target workspace silently
            auto windowPidFmt = std::format("pid:{}", window->getPID());
            std::string moveCmd = std::to_string(targetWorkspaceId) + "," + windowPidFmt;
            
            if (isVerbose())
                printLog(std::format("Moving pinned window '{}' to workspace {}", window->m_title, targetWorkspaceId));

            HyprlandAPI::invokeHyprctlCommand("dispatch", "movetoworkspacesilent " + moveCmd);
        }
    }

    void cleanupInvalidWindows() {
        std::erase_if(pinnedWindows, [](const PHLWINDOW& window) {
            return !window || !g_pCompositor->windowExists(window);
        });
    }

    PHLWINDOW getWindowFromArg(const std::string& arg) {
        if (arg.empty()) {
            // Return the focused window
            return g_pCompositor->m_lastWindow.lock();
        }
        // Get window by regex
        return g_pCompositor->getWindowByRegex(arg);
    }
}
