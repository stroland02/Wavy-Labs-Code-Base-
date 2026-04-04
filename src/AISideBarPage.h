#pragma once
// AISideBarPage — thin wrapper that places a pre-built QWidget page
// (extracted from AIPanel's page stack) into the LMMS left sidebar.
// Only compiled in the WAVY_LMMS_CORE build.
#ifdef WAVY_LMMS_CORE

#include "SideBarWidget.h"

// No Q_OBJECT — we add no new signals or slots beyond SideBarWidget's.
class AISideBarPage : public lmms::gui::SideBarWidget
{
public:
    AISideBarPage(const QString& title, const QPixmap& icon,
                  QWidget* content, QWidget* parent = nullptr)
        : lmms::gui::SideBarWidget(title, icon, parent)
    {
        if (content)
            addContentWidget(content);
    }
};

#endif // WAVY_LMMS_CORE
