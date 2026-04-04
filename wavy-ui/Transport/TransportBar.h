#pragma once

#include <QEvent>
#include <QList>
#include <QResizeEvent>
#include <QWidget>

class QComboBox;
class QFrame;
class QLabel;
class QToolButton;
class QSpinBox;
class QTimer;
class MiniKnob;
class WavyLogoLabel;
class EngineAPI;
class AIBackend;
class GenreConfigPopup;

#ifdef WAVY_LMMS_CORE
namespace lmms::gui { class MainWindow; }
#endif

// ---------------------------------------------------------------------------
// TransportBar — compact single-row transport bar for WavyShell.
//
//  [New|Open|Save] | ─stretch─ | [BPM LCD] [POS LCD] [4/4] [WAVY LABS] | ─stretch─ | CPU | 🔊 knob nn% | 🎵 knob n st
// ---------------------------------------------------------------------------

class TransportBar : public QWidget
{
    Q_OBJECT

public:
    explicit TransportBar(EngineAPI* engine, QWidget* parent = nullptr);
    bool eventFilter(QObject* obj, QEvent* event) override;
    void resizeEvent(QResizeEvent* e) override;

#ifdef WAVY_LMMS_CORE
    void setMainWindow(lmms::gui::MainWindow* win);
#endif

    // Sync combo display without re-emitting genreModeRequested
    void setGenreMode(const QString& displayName);

    // Wire backend for genre config popup
    void setBackend(AIBackend* backend);

Q_SIGNALS:
    void genreModeRequested(const QString& modeKey);  // internal key, not display name

private slots:
    void onBpmChanged(int bpm);
    void updatePosition();   // 100 ms timer: position + timesig + CPU

private:
    void buildUI();
    void applyThemeColors();

    EngineAPI* m_engine;

    // Project buttons (segmented group)
    QToolButton* m_newBtn{nullptr};
    QToolButton* m_openBtn{nullptr};
    QToolButton* m_saveBtn{nullptr};

    // LCD BPM area
    QLabel*   m_bpmValueLabel{nullptr};
    QSpinBox* m_bpmSpin{nullptr};
    QFrame*   m_bpmFrame{nullptr};

    // Playback position
    QLabel* m_posLabel{nullptr};

    // Time signature (polled by updatePosition)
    QLabel* m_timeSigLabel{nullptr};
    int     m_lastTimeSigNum{-1};
    int     m_lastTimeSigDen{-1};

    // CPU meter
    QLabel* m_cpuLabel{nullptr};

    // Wavy Labs animated logo
    WavyLogoLabel* m_wavyLogo{nullptr};

    // Master Volume knob
    MiniKnob* m_volumeKnob{nullptr};
    QLabel*   m_volumeLabel{nullptr};

    // Master Pitch knob (0..24 internally, -12..+12 semitones exposed)
    MiniKnob* m_pitchKnob{nullptr};
    QLabel*   m_pitchLabel{nullptr};

    // Genre Mode selector
    QComboBox* m_genreCombo{nullptr};
    QToolButton* m_genreSettingsBtn{nullptr};
    GenreConfigPopup* m_genrePopup{nullptr};
    AIBackend* m_backend{nullptr};

    // Position update timer (100 ms)
    QTimer* m_posTimer{nullptr};

    // Theme-adaptive display refs (promoted from buildUI locals)
    QLabel*        m_volIconLabel{nullptr};
    QLabel*        m_pitchIconLabel{nullptr};
    QFrame*        m_volFrame{nullptr};
    QFrame*        m_pitchFrame{nullptr};
    QFrame*        m_posFrame{nullptr};
    QFrame*        m_cpuFrame{nullptr};
    QLabel*        m_posSubLabel{nullptr};
    QLabel*        m_bpmSubLabel{nullptr};
    QLabel*        m_cpuSubLabel{nullptr};
    QList<QFrame*> m_separators;
};
