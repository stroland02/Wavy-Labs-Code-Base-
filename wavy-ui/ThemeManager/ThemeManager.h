#pragma once

#include <QString>
#include "WavyTheme.h"

class QWidget;

namespace Wavy {

class ThemeManager
{
public:
    /** Currently saved theme id (e.g. "wavy-dark", "wavy-light"). */
    static QString currentTheme();

    /** Load and apply a theme by id. Falls back to wavy-dark if not found. */
    static void applyTheme(const QString& id);

    /** Save theme id and apply it. */
    static void setTheme(const QString& id);

    /** All available theme ids for the UI. */
    static QStringList availableThemes();

    /** Returns lazy-initialized singleton WavyTheme for QML binding. */
    static WavyTheme* themeObject();

    /** Apply sidebar inline stylesheet for the given theme. Called from
        WavyShell::adoptLmmsContent() and from applyTheme() on live switches. */
    static void applySidebarStyle(QWidget* sidebar, const QString& themeId);
};

} // namespace Wavy
