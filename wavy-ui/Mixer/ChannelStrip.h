#pragma once

#include <QFrame>

class QLabel;
class QSlider;
class QPushButton;
class VUMeter;
class EngineAPI;

// ---------------------------------------------------------------------------
// ChannelStrip — single mixer channel: name, VU meter, fader, mute/solo.
// ---------------------------------------------------------------------------

class ChannelStrip : public QFrame
{
    Q_OBJECT

public:
    explicit ChannelStrip(int channelIndex, EngineAPI* engine, QWidget* parent = nullptr);

    int channelIndex() const { return m_channelIndex; }

    void refresh();               // re-read state from EngineAPI
    void updatePeaks();           // fast path: peaks only

    QSize sizeHint() const override { return {64, 280}; }

private slots:
    void onFaderChanged(int value);
    void onMuteClicked();
    void onSoloClicked();

private:
    void updateMuteButtonStyle();
    void updateSoloButtonStyle();

    int          m_channelIndex;
    EngineAPI*   m_engine;

    QLabel*      m_nameLabel;
    VUMeter*     m_meter;
    QSlider*     m_fader;
    QLabel*      m_dbLabel;
    QPushButton* m_muteBtn;
    QPushButton* m_soloBtn;
};
