#include "ChannelStrip.h"
#include "VUMeter.h"
#include "../EngineAPI/EngineAPI.h"

#include <QLabel>
#include <QSlider>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <cmath>

// Volume model range: 0.0 – 2.0 (1.0 = unity).
// Fader slider: 0 – 200 (int, maps to 0.0 – 2.0).

ChannelStrip::ChannelStrip(int channelIndex, EngineAPI* engine, QWidget* parent)
    : QFrame(parent)
    , m_channelIndex(channelIndex)
    , m_engine(engine)
{
    setObjectName("WavyChannelStrip");
    setFrameShape(QFrame::StyledPanel);
    setFixedWidth(64);

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(4, 6, 4, 6);
    layout->setSpacing(4);

    // ── Channel name ────────────────────────────────────────────────
    m_nameLabel = new QLabel(this);
    m_nameLabel->setObjectName("WavyMixerChName");
    m_nameLabel->setAlignment(Qt::AlignCenter);
    m_nameLabel->setWordWrap(true);
    m_nameLabel->setMaximumHeight(28);
    QFont nameFont = m_nameLabel->font();
    nameFont.setPointSize(7);
    m_nameLabel->setFont(nameFont);
    layout->addWidget(m_nameLabel);

    // ── Meter + Fader side by side ──────────────────────────────────
    auto* meterFaderRow = new QHBoxLayout;
    meterFaderRow->setSpacing(2);

    m_meter = new VUMeter(this);
    meterFaderRow->addWidget(m_meter);

    m_fader = new QSlider(Qt::Vertical, this);
    m_fader->setObjectName("WavyMixerFader");
    m_fader->setRange(0, 200);
    m_fader->setValue(100);
    m_fader->setFixedWidth(20);
    meterFaderRow->addWidget(m_fader);

    layout->addLayout(meterFaderRow, 1);

    // ── dB readout ──────────────────────────────────────────────────
    m_dbLabel = new QLabel("0.0 dB", this);
    m_dbLabel->setObjectName("WavyMixerDbLabel");
    m_dbLabel->setAlignment(Qt::AlignCenter);
    QFont dbFont = m_dbLabel->font();
    dbFont.setPointSize(7);
    m_dbLabel->setFont(dbFont);
    layout->addWidget(m_dbLabel);

    // ── Mute / Solo buttons ─────────────────────────────────────────
    auto* btnRow = new QHBoxLayout;
    btnRow->setSpacing(2);

    m_muteBtn = new QPushButton("M", this);
    m_muteBtn->setObjectName("WavyMixerMuteBtn");
    m_muteBtn->setFixedSize(24, 20);
    m_muteBtn->setCheckable(true);
    btnRow->addWidget(m_muteBtn);

    m_soloBtn = new QPushButton("S", this);
    m_soloBtn->setObjectName("WavyMixerSoloBtn");
    m_soloBtn->setFixedSize(24, 20);
    m_soloBtn->setCheckable(true);
    btnRow->addWidget(m_soloBtn);

    layout->addLayout(btnRow);

    // ── Connections ─────────────────────────────────────────────────
    connect(m_fader, &QSlider::valueChanged, this, &ChannelStrip::onFaderChanged);
    connect(m_muteBtn, &QPushButton::clicked, this, &ChannelStrip::onMuteClicked);
    connect(m_soloBtn, &QPushButton::clicked, this, &ChannelStrip::onSoloClicked);

    // Initial state
    refresh();
}

void ChannelStrip::refresh()
{
    // Name
    QString name = m_engine->mixerChannelName(m_channelIndex);
    m_nameLabel->setText(name.isEmpty() ? QString::number(m_channelIndex) : name);

    // Color strip at top
    QColor color = m_engine->mixerChannelColor(m_channelIndex);
    if (color.isValid()) {
        m_nameLabel->setStyleSheet(
            QString("background: %1; color: %2; border-radius: 2px; padding: 1px;")
                .arg(color.name(),
                     color.lightness() > 128 ? "#000" : "#fff"));
    } else {
        m_nameLabel->setStyleSheet(QString());
    }

    // Volume fader
    float vol = m_engine->mixerChannelVolume(m_channelIndex);
    {
        const QSignalBlocker blocker(m_fader);
        m_fader->setValue(static_cast<int>(vol * 100.0f));
    }

    // dB readout
    float db = (vol > 0.0001f) ? 20.0f * std::log10(vol) : -60.0f;
    m_dbLabel->setText(QString::number(db, 'f', 1) + " dB");

    // Mute/Solo
    {
        const QSignalBlocker b1(m_muteBtn);
        m_muteBtn->setChecked(m_engine->mixerChannelMuted(m_channelIndex));
    }
    {
        const QSignalBlocker b2(m_soloBtn);
        m_soloBtn->setChecked(m_engine->mixerChannelSoloed(m_channelIndex));
    }
    updateMuteButtonStyle();
    updateSoloButtonStyle();

    updatePeaks();
}

void ChannelStrip::updatePeaks()
{
    m_meter->setPeaks(
        m_engine->mixerChannelPeakLeft(m_channelIndex),
        m_engine->mixerChannelPeakRight(m_channelIndex));
}

void ChannelStrip::onFaderChanged(int value)
{
    float vol = static_cast<float>(value) / 100.0f;
    m_engine->setMixerChannelVolume(m_channelIndex, vol);

    float db = (vol > 0.0001f) ? 20.0f * std::log10(vol) : -60.0f;
    m_dbLabel->setText(QString::number(db, 'f', 1) + " dB");
}

void ChannelStrip::onMuteClicked()
{
    m_engine->setMixerChannelMuted(m_channelIndex, m_muteBtn->isChecked());
    updateMuteButtonStyle();
}

void ChannelStrip::onSoloClicked()
{
    m_engine->setMixerChannelSoloed(m_channelIndex, m_soloBtn->isChecked());
    updateSoloButtonStyle();
}

void ChannelStrip::updateMuteButtonStyle()
{
    if (m_muteBtn->isChecked()) {
        m_muteBtn->setStyleSheet("QPushButton { background: #ef4444; color: white; font-weight: bold; border: none; border-radius: 2px; }");
    } else {
        m_muteBtn->setStyleSheet("QPushButton { background: #2a2a3e; color: #888; font-weight: bold; border: 1px solid #444; border-radius: 2px; }");
    }
}

void ChannelStrip::updateSoloButtonStyle()
{
    if (m_soloBtn->isChecked()) {
        m_soloBtn->setStyleSheet("QPushButton { background: #facc15; color: black; font-weight: bold; border: none; border-radius: 2px; }");
    } else {
        m_soloBtn->setStyleSheet("QPushButton { background: #2a2a3e; color: #888; font-weight: bold; border: 1px solid #444; border-radius: 2px; }");
    }
}
