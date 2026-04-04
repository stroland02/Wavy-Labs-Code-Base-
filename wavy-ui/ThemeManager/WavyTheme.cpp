#include "WavyTheme.h"

namespace Wavy {

// Silver palette applied in constructor so QML never sees uninitialized/black colors
WavyTheme::WavyTheme(QObject* parent)
    : QObject(parent)
{
    apply(
        QColor("#f4f2f2"),  // bg
        QColor("#e8e4e4"),  // surface
        QColor("#c0392b"),  // accent
        QColor("#1a1717"),  // fg
        QColor("#6e6464"),  // dim
        QColor("#b0acac"),  // outline
        QColor("#fceaea"),  // errorBg
        QColor("#dce8f5"),  // userBg
        QColor("#dff2e8")   // wavyBg
    );
}

void WavyTheme::apply(QColor bg, QColor surface, QColor accent, QColor fg, QColor dim,
                       QColor outline, QColor errorBg, QColor userBg, QColor wavyBg)
{
    m_bg      = bg;
    m_surface = surface;
    m_accent  = accent;
    m_fg      = fg;
    m_dim     = dim;
    m_outline = outline;
    m_errorBg = errorBg;
    m_userBg  = userBg;
    m_wavyBg  = wavyBg;
    emit changed();
}

} // namespace Wavy
