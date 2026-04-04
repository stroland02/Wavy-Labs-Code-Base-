#pragma once

#include <QWidget>
#include <QComboBox>
#include <QSpinBox>
#include <QLineEdit>
#include <QPushButton>
#include <QToolButton>
#include <QVBoxLayout>
#include <QScrollArea>
#include <QLabel>
#include <QFrame>
#include <QVariantList>

class AIBackend;

// ---------------------------------------------------------------------------
// GenreConfigPopup — frameless popup for editing genre production settings.
// Shows BPM, time sig, key, scale, chord/drum style, master FX, instruments.
// Persists overrides in QSettings; emits applyRequested to trigger DAW update.
// ---------------------------------------------------------------------------

class GenreConfigPopup : public QWidget
{
    Q_OBJECT

public:
    explicit GenreConfigPopup(AIBackend* backend, QWidget* parent = nullptr);

    void loadGenre(const QString& key);
    void showBelow(QWidget* anchor);

Q_SIGNALS:
    void applyRequested(const QString& genreKey);

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    void buildUI();
    void applyThemeColors();
    void saveToSettings();
    void resetToDefaults();
    void applyChanges();

    // Rebuild instrument slot widgets from m_instrumentSlots data
    void rebuildInstrumentWidgets();
    void addInstrumentSlot();
    void removeInstrumentSlot(int index);
    void addFxRow(const QString& fxName);

    AIBackend* m_backend;
    QString    m_currentGenreKey;

    // -- Production section --
    QSpinBox*   m_bpmSpin{nullptr};
    QComboBox*  m_timeSigNumCombo{nullptr};
    QComboBox*  m_timeSigDenCombo{nullptr};
    QComboBox*  m_keyCombo{nullptr};
    QComboBox*  m_scaleCombo{nullptr};
    QComboBox*  m_chordStyleCombo{nullptr};
    QComboBox*  m_drumStyleCombo{nullptr};

    // -- Master FX section --
    struct FxRow {
        QComboBox* combo{nullptr};
        QToolButton* removeBtn{nullptr};
        QWidget* container{nullptr};
    };
    QVBoxLayout* m_fxLayout{nullptr};
    QVector<FxRow> m_fxRows;
    QPushButton* m_addFxBtn{nullptr};

    // -- Instruments section --
    struct InstrSlotWidgets {
        QLineEdit* nameEdit{nullptr};
        QComboBox* pluginCombo{nullptr};
        QComboBox* presetCombo{nullptr};
        QToolButton* removeBtn{nullptr};
        QWidget* container{nullptr};
    };
    QVBoxLayout* m_instrLayout{nullptr};
    QVector<InstrSlotWidgets> m_instrWidgets;
    QPushButton* m_addInstrBtn{nullptr};

    // -- Action buttons --
    QPushButton* m_resetBtn{nullptr};
    QPushButton* m_saveBtn{nullptr};
    QPushButton* m_applyBtn{nullptr};

    // -- Header + scroll --
    QLabel* m_headerLabel{nullptr};
    QLabel* m_prodLabel{nullptr};
    QLabel* m_fxLabel{nullptr};
    QLabel* m_instrLabel{nullptr};
    QScrollArea* m_scrollArea{nullptr};
};
