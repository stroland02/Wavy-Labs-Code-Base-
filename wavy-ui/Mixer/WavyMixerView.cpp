#include "WavyMixerView.h"
#include "ChannelStrip.h"
#include "../EngineAPI/EngineAPI.h"

#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QScrollArea>
#include <QTimer>
#include <QLabel>

WavyMixerView::WavyMixerView(EngineAPI* engine, QWidget* parent)
    : QWidget(parent)
    , m_engine(engine)
{
    setObjectName("WavyMixerView");

    auto* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // ── Header ──────────────────────────────────────────────────────
    auto* header = new QWidget(this);
    header->setObjectName("WavyMixerHeader");
    header->setFixedHeight(28);
    auto* headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(8, 0, 8, 0);
    auto* title = new QLabel("Mixer", header);
    title->setStyleSheet("font-weight: bold; font-size: 12px; color: #e0e0e0;");
    headerLayout->addWidget(title);
    headerLayout->addStretch();
    mainLayout->addWidget(header);

    // ── Scrollable strip area ───────────────────────────────────────
    m_scrollArea = new QScrollArea(this);
    m_scrollArea->setObjectName("WavyMixerScrollArea");
    m_scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    m_scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_scrollArea->setWidgetResizable(true);
    m_scrollArea->setFrameShape(QFrame::NoFrame);

    m_stripContainer = new QWidget;
    m_stripContainer->setObjectName("WavyMixerStripContainer");
    auto* stripLayout = new QHBoxLayout(m_stripContainer);
    stripLayout->setContentsMargins(4, 4, 4, 4);
    stripLayout->setSpacing(2);
    stripLayout->addStretch();

    m_scrollArea->setWidget(m_stripContainer);
    mainLayout->addWidget(m_scrollArea, 1);

    // ── Meter refresh timer (33ms ≈ 30 fps) ─────────────────────────
    m_meterTimer = new QTimer(this);
    m_meterTimer->setInterval(33);
    connect(m_meterTimer, &QTimer::timeout, this, &WavyMixerView::onMeterTick);
    m_meterTimer->start();

    // ── Listen for channel count changes ────────────────────────────
    connect(m_engine, &EngineAPI::mixerChannelCountChanged,
            this, &WavyMixerView::rebuildStrips);

    // Build initial strips
    rebuildStrips();

}

void WavyMixerView::rebuildStrips()
{
    // Clear existing strips
    for (auto* strip : m_strips)
        strip->deleteLater();
    m_strips.clear();

    auto* layout = m_stripContainer->layout();

    // Remove the stretch item
    while (layout->count() > 0) {
        auto* item = layout->takeAt(0);
        delete item;
    }

    // Create channel strips
    int count = m_engine->mixerChannelCount();
    for (int i = 0; i < count; ++i) {
        auto* strip = new ChannelStrip(i, m_engine, m_stripContainer);
        static_cast<QHBoxLayout*>(layout)->addWidget(strip);
        m_strips.append(strip);
    }

    // Trailing stretch
    static_cast<QHBoxLayout*>(layout)->addStretch();
}

void WavyMixerView::onMeterTick()
{
    if (!isVisible()) return;

    for (auto* strip : m_strips)
        strip->updatePeaks();
}
