#pragma once

#ifdef WAVY_LMMS_CORE

#include <QWidget>

class QLabel;
class QComboBox;
class QToolButton;
class QButtonGroup;
class EngineAPI;

namespace lmms::gui {
    class PianoRoll;
}

// ---------------------------------------------------------------------------
// WavyPianoRollBar — custom toolbar shown when Piano Roll tab is active.
//
// Provides edit mode toggle, zoom, quantize, key/scale, chord, and note
// length controls. Drives the LMMS PianoRoll through its public models.
// ---------------------------------------------------------------------------

class WavyPianoRollBar : public QWidget
{
    Q_OBJECT

public:
    explicit WavyPianoRollBar(EngineAPI* engine, QWidget* parent = nullptr);

    /// Connect to PianoRoll models (call after GuiApplication init).
    void connectToPianoRoll(lmms::gui::PianoRoll* editor);

private slots:
    void onEditModeChanged(int id);
    void onQuantizeChanged(int index);
    void onNoteLenChanged(int index);
    void onKeyChanged(int index);
    void onScaleChanged(int index);
    void onChordChanged(int index);

private:
    void buildToolbar();
    void populateComboFromModel(QComboBox* combo, void* model);
    void applyStyle();

    EngineAPI* m_engine;
    lmms::gui::PianoRoll* m_pianoRoll{nullptr};

    QButtonGroup* m_editModeGroup;
    QToolButton*  m_drawBtn;
    QToolButton*  m_eraseBtn;
    QToolButton*  m_selectBtn;
    QComboBox*    m_quantizeCombo;
    QComboBox*    m_noteLenCombo;
    QComboBox*    m_keyCombo;
    QComboBox*    m_scaleCombo;
    QComboBox*    m_chordCombo;
};

#endif // WAVY_LMMS_CORE
