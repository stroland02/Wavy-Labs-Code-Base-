#ifdef WAVY_LMMS_CORE

#include "WavyPianoRollBar.h"
#include "../EngineAPI/EngineAPI.h"

#include "PianoRoll.h"
#include "ComboBoxModel.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QComboBox>
#include <QToolButton>
#include <QButtonGroup>
#include <QFrame>
#include <QMetaObject>
#include <QDebug>

// ---------------------------------------------------------------------------

WavyPianoRollBar::WavyPianoRollBar(EngineAPI* engine, QWidget* parent)
    : QWidget(parent)
    , m_engine(engine)
{
    setObjectName("WavyPianoRollBar");
    setFixedHeight(36);

    buildToolbar();
    applyStyle();
}

// ---------------------------------------------------------------------------

static void populateCombo(QComboBox* combo, lmms::ComboBoxModel& model)
{
    const QSignalBlocker blocker(combo);
    combo->clear();
    for (int i = 0; i < model.size(); ++i)
        combo->addItem(model.itemText(i));
    combo->setCurrentIndex(model.value());
}

static QFrame* makeSep(QWidget* parent)
{
    auto* sep = new QFrame(parent);
    sep->setFrameShape(QFrame::VLine);
    sep->setStyleSheet("color: #2a2a4a;");
    sep->setFixedWidth(1);
    return sep;
}

// ---------------------------------------------------------------------------

void WavyPianoRollBar::buildToolbar()
{
    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(8, 2, 8, 2);
    layout->setSpacing(6);

    // ── Edit mode buttons ───────────────────────────────────────────
    m_editModeGroup = new QButtonGroup(this);
    m_editModeGroup->setExclusive(true);

    m_drawBtn = new QToolButton(this);
    m_drawBtn->setText("Draw");
    m_drawBtn->setObjectName("WavyPREditMode");
    m_drawBtn->setCheckable(true);
    m_drawBtn->setChecked(true);
    m_drawBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_drawBtn, 0);
    layout->addWidget(m_drawBtn);

    m_eraseBtn = new QToolButton(this);
    m_eraseBtn->setText("Erase");
    m_eraseBtn->setObjectName("WavyPREditMode");
    m_eraseBtn->setCheckable(true);
    m_eraseBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_eraseBtn, 1);
    layout->addWidget(m_eraseBtn);

    m_selectBtn = new QToolButton(this);
    m_selectBtn->setText("Select");
    m_selectBtn->setObjectName("WavyPREditMode");
    m_selectBtn->setCheckable(true);
    m_selectBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_selectBtn, 2);
    layout->addWidget(m_selectBtn);

    connect(m_editModeGroup, &QButtonGroup::idClicked,
            this, &WavyPianoRollBar::onEditModeChanged);

    layout->addWidget(makeSep(this));

    // ── Quantize ────────────────────────────────────────────────────
    auto* qLbl = new QLabel("Q", this);
    qLbl->setStyleSheet("color: #888; font-size: 10px; font-weight: bold;");
    layout->addWidget(qLbl);

    m_quantizeCombo = new QComboBox(this);
    m_quantizeCombo->setObjectName("WavyPRCombo");
    m_quantizeCombo->setFixedWidth(85);
    m_quantizeCombo->setFixedHeight(24);
    connect(m_quantizeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &WavyPianoRollBar::onQuantizeChanged);
    layout->addWidget(m_quantizeCombo);

    // ── Note length ─────────────────────────────────────────────────
    auto* nLbl = new QLabel("Len", this);
    nLbl->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(nLbl);

    m_noteLenCombo = new QComboBox(this);
    m_noteLenCombo->setObjectName("WavyPRCombo");
    m_noteLenCombo->setFixedWidth(100);
    m_noteLenCombo->setFixedHeight(24);
    connect(m_noteLenCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &WavyPianoRollBar::onNoteLenChanged);
    layout->addWidget(m_noteLenCombo);

    layout->addWidget(makeSep(this));

    // ── Key ─────────────────────────────────────────────────────────
    auto* kLbl = new QLabel("Key", this);
    kLbl->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(kLbl);

    m_keyCombo = new QComboBox(this);
    m_keyCombo->setObjectName("WavyPRCombo");
    m_keyCombo->setFixedWidth(65);
    m_keyCombo->setFixedHeight(24);
    connect(m_keyCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &WavyPianoRollBar::onKeyChanged);
    layout->addWidget(m_keyCombo);

    // ── Scale ───────────────────────────────────────────────────────
    m_scaleCombo = new QComboBox(this);
    m_scaleCombo->setObjectName("WavyPRCombo");
    m_scaleCombo->setFixedWidth(140);
    m_scaleCombo->setFixedHeight(24);
    connect(m_scaleCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &WavyPianoRollBar::onScaleChanged);
    layout->addWidget(m_scaleCombo);

    // ── Chord ───────────────────────────────────────────────────────
    auto* cLbl = new QLabel("Chord", this);
    cLbl->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(cLbl);

    m_chordCombo = new QComboBox(this);
    m_chordCombo->setObjectName("WavyPRCombo");
    m_chordCombo->setFixedWidth(120);
    m_chordCombo->setFixedHeight(24);
    connect(m_chordCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &WavyPianoRollBar::onChordChanged);
    layout->addWidget(m_chordCombo);

    layout->addStretch();
}

// ---------------------------------------------------------------------------

void WavyPianoRollBar::connectToPianoRoll(lmms::gui::PianoRoll* editor)
{
    if (!editor) return;
    m_pianoRoll = editor;

    // Populate combos from PianoRoll's ComboBoxModels
    populateCombo(m_quantizeCombo, editor->quantizeModel());
    populateCombo(m_noteLenCombo, editor->noteLenModel());
    populateCombo(m_keyCombo, editor->keyModel());
    populateCombo(m_scaleCombo, editor->scaleModel());
    populateCombo(m_chordCombo, editor->chordModel());

    // Listen for model changes from LMMS side
    connect(&editor->quantizeModel(), &lmms::ComboBoxModel::dataChanged, this, [this]() {
        const QSignalBlocker b(m_quantizeCombo);
        m_quantizeCombo->setCurrentIndex(m_pianoRoll->quantizeModel().value());
    });
    connect(&editor->noteLenModel(), &lmms::ComboBoxModel::dataChanged, this, [this]() {
        const QSignalBlocker b(m_noteLenCombo);
        m_noteLenCombo->setCurrentIndex(m_pianoRoll->noteLenModel().value());
    });
    connect(&editor->keyModel(), &lmms::ComboBoxModel::dataChanged, this, [this]() {
        const QSignalBlocker b(m_keyCombo);
        m_keyCombo->setCurrentIndex(m_pianoRoll->keyModel().value());
    });
    connect(&editor->scaleModel(), &lmms::ComboBoxModel::dataChanged, this, [this]() {
        const QSignalBlocker b(m_scaleCombo);
        m_scaleCombo->setCurrentIndex(m_pianoRoll->scaleModel().value());
    });
    connect(&editor->chordModel(), &lmms::ComboBoxModel::dataChanged, this, [this]() {
        const QSignalBlocker b(m_chordCombo);
        m_chordCombo->setCurrentIndex(m_pianoRoll->chordModel().value());
    });

    qDebug() << "[WavyPianoRollBar] Connected to PianoRoll";
}

// ---------------------------------------------------------------------------

void WavyPianoRollBar::onEditModeChanged(int id)
{
    if (m_pianoRoll)
        QMetaObject::invokeMethod(m_pianoRoll, "setEditMode", Q_ARG(int, id));
}

void WavyPianoRollBar::onQuantizeChanged(int index)
{
    if (m_pianoRoll)
        m_pianoRoll->quantizeModel().setValue(index);
}

void WavyPianoRollBar::onNoteLenChanged(int index)
{
    if (m_pianoRoll)
        m_pianoRoll->noteLenModel().setValue(index);
}

void WavyPianoRollBar::onKeyChanged(int index)
{
    if (m_pianoRoll)
        m_pianoRoll->keyModel().setValue(index);
}

void WavyPianoRollBar::onScaleChanged(int index)
{
    if (m_pianoRoll)
        m_pianoRoll->scaleModel().setValue(index);
}

void WavyPianoRollBar::onChordChanged(int index)
{
    if (m_pianoRoll)
        m_pianoRoll->chordModel().setValue(index);
}

// ---------------------------------------------------------------------------

void WavyPianoRollBar::applyStyle()
{
    setStyleSheet(
        "#WavyPianoRollBar { background: #16213e; border-bottom: 1px solid #2a2a4a; }"
        "#WavyPREditMode { background: #1a1a2e; color: #aaa; border: 1px solid #3a3a5a;"
        "  border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
        "#WavyPREditMode:checked { background: #7c3aed; color: white; border-color: #7c3aed; }"
        "#WavyPREditMode:hover { background: #2a2a4e; }"
        "#WavyPRCombo { background: #1a1a2e; color: #ccc; border: 1px solid #3a3a5a;"
        "  border-radius: 3px; padding: 2px 4px; font-size: 10px; }"
        "#WavyPRCombo::drop-down { border: none; width: 16px; }"
        "#WavyPRCombo QAbstractItemView { background: #1a1a2e; color: #ccc;"
        "  selection-background-color: #7c3aed; }"
    );
}

#endif // WAVY_LMMS_CORE
