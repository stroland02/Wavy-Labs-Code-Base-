#pragma once
#include <QColor>
#include <QObject>

namespace Wavy {

class WavyTheme : public QObject {
    Q_OBJECT
    Q_PROPERTY(QColor bg      READ bg      NOTIFY changed)
    Q_PROPERTY(QColor surface READ surface NOTIFY changed)
    Q_PROPERTY(QColor accent  READ accent  NOTIFY changed)
    Q_PROPERTY(QColor fg      READ fg      NOTIFY changed)
    Q_PROPERTY(QColor dim     READ dim     NOTIFY changed)
    Q_PROPERTY(QColor outline READ outline NOTIFY changed)
    Q_PROPERTY(QColor errorBg READ errorBg NOTIFY changed)
    Q_PROPERTY(QColor userBg  READ userBg  NOTIFY changed)
    Q_PROPERTY(QColor wavyBg  READ wavyBg  NOTIFY changed)
public:
    explicit WavyTheme(QObject* parent = nullptr);

    void apply(QColor bg, QColor surface, QColor accent, QColor fg, QColor dim,
               QColor outline, QColor errorBg, QColor userBg, QColor wavyBg);

    QColor bg()      const { return m_bg; }
    QColor surface() const { return m_surface; }
    QColor accent()  const { return m_accent; }
    QColor fg()      const { return m_fg; }
    QColor dim()     const { return m_dim; }
    QColor outline() const { return m_outline; }
    QColor errorBg() const { return m_errorBg; }
    QColor userBg()  const { return m_userBg; }
    QColor wavyBg()  const { return m_wavyBg; }

signals:
    void changed();

private:
    QColor m_bg, m_surface, m_accent, m_fg, m_dim,
           m_outline, m_errorBg, m_userBg, m_wavyBg;
};

} // namespace Wavy
