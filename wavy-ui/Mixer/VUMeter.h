#pragma once

#include <QWidget>

// ---------------------------------------------------------------------------
// VUMeter — stereo peak meter rendered via QPainter.
// ---------------------------------------------------------------------------

class VUMeter : public QWidget
{
    Q_OBJECT

public:
    explicit VUMeter(QWidget* parent = nullptr);

    void setPeaks(float left, float right);

    QSize sizeHint() const override { return {16, 120}; }
    QSize minimumSizeHint() const override { return {12, 60}; }

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    float m_peakLeft{0.0f};
    float m_peakRight{0.0f};
};
