#pragma once

#ifdef WAVY_LMMS_CORE

#include <QWidget>

class QLabel;
class QSlider;
class QPushButton;
class QToolButton;
class QButtonGroup;
class EngineAPI;

namespace lmms::gui {
    class SongEditor;
}

// ---------------------------------------------------------------------------
// WavyArrangementView — custom toolbar for the LMMS SongEditor.
//
// Shown above the LMMS workspace when the Song editor tab is active.
// Provides track add buttons, edit mode toggle, zoom slider, and info labels.
// Drives the SongEditor through its public API without reparenting.
//
// This is the "wrapper-first" strategy: Wavy chrome around LMMS internals.
// ---------------------------------------------------------------------------

class WavyArrangementView : public QWidget
{
    Q_OBJECT

public:
    explicit WavyArrangementView(EngineAPI* engine, QWidget* parent = nullptr);

    /// Connect to SongEditor signals (call after GuiApplication init).
    void connectToSongEditor(lmms::gui::SongEditor* editor);

    lmms::gui::SongEditor* songEditor() const { return m_songEditor; }

private slots:
    void onAddPatternTrack();
    void onAddSampleTrack();
    void onAddAutomationTrack();
    void onEditModeChanged(int id);
    void onZoomChanged(int value);
    void onTrackListChanged();

private:
    void buildToolbar();
    void applyStyle();

    EngineAPI* m_engine;
    lmms::gui::SongEditor* m_songEditor{nullptr};

    // Toolbar widgets
    QPushButton*  m_addPatternBtn;
    QPushButton*  m_addSampleBtn;
    QPushButton*  m_addAutoBtn;
    QButtonGroup* m_editModeGroup;
    QToolButton*  m_drawModeBtn;
    QToolButton*  m_knifeModeBtn;
    QToolButton*  m_selectModeBtn;
    QSlider*      m_zoomSlider;
    QLabel*       m_zoomLabel;
    QLabel*       m_trackCountLabel;
    QLabel*       m_songLenLabel;
};

#endif // WAVY_LMMS_CORE
