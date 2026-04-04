#include "VUMeter.h"

#include <QPainter>
#include <QLinearGradient>
#include <algorithm>
#include <cmath>

VUMeter::VUMeter(QWidget* parent)
    : QWidget(parent)
{
    setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    setFixedWidth(16);
}

void VUMeter::setPeaks(float left, float right)
{
    m_peakLeft  = std::clamp(left, 0.0f, 1.5f);
    m_peakRight = std::clamp(right, 0.0f, 1.5f);
    update();
}

void VUMeter::paintEvent(QPaintEvent* /*event*/)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, false);

    const int w = width();
    const int h = height();
    const int barW = (w - 2) / 2;  // 2 bars with 2px gap
    const int leftX = 0;
    const int rightX = barW + 2;

    // Background
    p.fillRect(rect(), QColor(0x12, 0x12, 0x12));

    auto drawBar = [&](int x, int bw, float peak) {
        // Clamp to 1.0 for bar height, show red above 1.0
        float norm = std::min(peak, 1.0f);
        int barH = static_cast<int>(norm * h);
        if (barH < 1) return;

        int y = h - barH;

        // Gradient: green → yellow → red
        QLinearGradient grad(0, h, 0, 0);
        grad.setColorAt(0.0, QColor(0x22, 0xc5, 0x5e));   // green
        grad.setColorAt(0.6, QColor(0xfa, 0xcc, 0x15));   // yellow
        grad.setColorAt(1.0, QColor(0xef, 0x44, 0x44));   // red

        p.fillRect(x, y, bw, barH, grad);

        // Clipping indicator (red dot at top if peak > 1.0)
        if (peak > 1.0f) {
            p.fillRect(x, 0, bw, 3, QColor(0xff, 0x00, 0x00));
        }
    };

    drawBar(leftX, barW, m_peakLeft);
    drawBar(rightX, barW, m_peakRight);
}
