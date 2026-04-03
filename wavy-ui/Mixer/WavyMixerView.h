#pragma once

#include <QWidget>
#include <QList>

class QScrollArea;
class QTimer;
class ChannelStrip;
class EngineAPI;

// ---------------------------------------------------------------------------
// WavyMixerView — scrollable mixer panel with channel strips and VU meters.
// Reads channel state from EngineAPI; polls peaks at ~30 fps.
// ---------------------------------------------------------------------------

class WavyMixerView : public QWidget
{
    Q_OBJECT

public:
    explicit WavyMixerView(EngineAPI* engine, QWidget* parent = nullptr);

public slots:
    void rebuildStrips();

private slots:
    void onMeterTick();

private:
    EngineAPI*   m_engine;
    QScrollArea* m_scrollArea;
    QWidget*     m_stripContainer;
    QTimer*      m_meterTimer;
    QList<ChannelStrip*> m_strips;
};
