#ifdef WAVY_LMMS_CORE

#include "WavyArrangementView.h"
#include "../EngineAPI/EngineAPI.h"

#include "SongEditor.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QSlider>
#include <QPushButton>
#include <QToolButton>
#include <QButtonGroup>
#include <QFrame>
#include <QDebug>

// ---------------------------------------------------------------------------

WavyArrangementView::WavyArrangementView(EngineAPI* engine, QWidget* parent)
    : QWidget(parent)
    , m_engine(engine)
{
    setObjectName("WavyArrangeToolbar");
    setFixedHeight(36);

    buildToolbar();
    applyStyle();

    // Connect to EngineAPI signals
    connect(m_engine, &EngineAPI::trackListChanged,
            this, &WavyArrangementView::onTrackListChanged);
    connect(m_engine, &EngineAPI::songLengthChanged,
            this, [this](int bars) {
                m_songLenLabel->setText(QString("%1 bars").arg(bars));
            });
}

// ---------------------------------------------------------------------------

void WavyArrangementView::buildToolbar()
{
    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(8, 2, 8, 2);
    layout->setSpacing(6);

    // ── Track add buttons ───────────────────────────────────────────
    m_addPatternBtn = new QPushButton("+ Pattern", this);
    m_addPatternBtn->setObjectName("WavyArrangeAddBtn");
    m_addPatternBtn->setFixedHeight(28);
    connect(m_addPatternBtn, &QPushButton::clicked,
            this, &WavyArrangementView::onAddPatternTrack);
    layout->addWidget(m_addPatternBtn);

    m_addSampleBtn = new QPushButton("+ Sample", this);
    m_addSampleBtn->setObjectName("WavyArrangeAddBtn");
    m_addSampleBtn->setFixedHeight(28);
    connect(m_addSampleBtn, &QPushButton::clicked,
            this, &WavyArrangementView::onAddSampleTrack);
    layout->addWidget(m_addSampleBtn);

    m_addAutoBtn = new QPushButton("+ Auto", this);
    m_addAutoBtn->setObjectName("WavyArrangeAddBtn");
    m_addAutoBtn->setFixedHeight(28);
    connect(m_addAutoBtn, &QPushButton::clicked,
            this, &WavyArrangementView::onAddAutomationTrack);
    layout->addWidget(m_addAutoBtn);

    // Separator
    auto* sep1 = new QFrame(this);
    sep1->setFrameShape(QFrame::VLine);
    sep1->setStyleSheet("color: #2a2a4a;");
    sep1->setFixedWidth(1);
    layout->addWidget(sep1);

    // ── Edit mode buttons ───────────────────────────────────────────
    m_editModeGroup = new QButtonGroup(this);
    m_editModeGroup->setExclusive(true);

    m_drawModeBtn = new QToolButton(this);
    m_drawModeBtn->setText("Draw");
    m_drawModeBtn->setObjectName("WavyArrangeEditMode");
    m_drawModeBtn->setCheckable(true);
    m_drawModeBtn->setChecked(true);
    m_drawModeBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_drawModeBtn, 0);
    layout->addWidget(m_drawModeBtn);

    m_knifeModeBtn = new QToolButton(this);
    m_knifeModeBtn->setText("Knife");
    m_knifeModeBtn->setObjectName("WavyArrangeEditMode");
    m_knifeModeBtn->setCheckable(true);
    m_knifeModeBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_knifeModeBtn, 1);
    layout->addWidget(m_knifeModeBtn);

    m_selectModeBtn = new QToolButton(this);
    m_selectModeBtn->setText("Select");
    m_selectModeBtn->setObjectName("WavyArrangeEditMode");
    m_selectModeBtn->setCheckable(true);
    m_selectModeBtn->setFixedHeight(28);
    m_editModeGroup->addButton(m_selectModeBtn, 2);
    layout->addWidget(m_selectModeBtn);

    connect(m_editModeGroup, &QButtonGroup::idClicked,
            this, &WavyArrangementView::onEditModeChanged);

    // Separator
    auto* sep2 = new QFrame(this);
    sep2->setFrameShape(QFrame::VLine);
    sep2->setStyleSheet("color: #2a2a4a;");
    sep2->setFixedWidth(1);
    layout->addWidget(sep2);

    // ── Zoom ────────────────────────────────────────────────────────
    auto* zoomIcon = new QLabel("Zoom", this);
    zoomIcon->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(zoomIcon);

    m_zoomSlider = new QSlider(Qt::Horizontal, this);
    m_zoomSlider->setObjectName("WavyArrangeZoom");
    m_zoomSlider->setRange(0, 200);
    m_zoomSlider->setValue(100);
    m_zoomSlider->setFixedWidth(120);
    m_zoomSlider->setFixedHeight(20);
    connect(m_zoomSlider, &QSlider::valueChanged,
            this, &WavyArrangementView::onZoomChanged);
    layout->addWidget(m_zoomSlider);

    m_zoomLabel = new QLabel("100%", this);
    m_zoomLabel->setObjectName("WavyArrangeZoomLabel");
    m_zoomLabel->setFixedWidth(40);
    m_zoomLabel->setStyleSheet("color: #aaa; font-size: 10px;");
    layout->addWidget(m_zoomLabel);

    layout->addStretch();

    // ── Info labels ─────────────────────────────────────────────────
    m_trackCountLabel = new QLabel(this);
    m_trackCountLabel->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(m_trackCountLabel);

    auto* sep3 = new QFrame(this);
    sep3->setFrameShape(QFrame::VLine);
    sep3->setStyleSheet("color: #2a2a4a;");
    sep3->setFixedWidth(1);
    layout->addWidget(sep3);

    m_songLenLabel = new QLabel(this);
    m_songLenLabel->setStyleSheet("color: #888; font-size: 10px;");
    layout->addWidget(m_songLenLabel);

    // Initial values
    onTrackListChanged();
    m_songLenLabel->setText(QString("%1 bars").arg(m_engine->songLengthBars()));
}

// ---------------------------------------------------------------------------

void WavyArrangementView::connectToSongEditor(lmms::gui::SongEditor* editor)
{
    if (!editor) return;
    m_songEditor = editor;

    // Sync zoom slider when SongEditor zoom changes
    connect(editor, &lmms::gui::SongEditor::pixelsPerBarChanged,
            this, [this](float ppb) {
                int sliderVal = static_cast<int>((ppb - 4.0f) / (400.0f - 4.0f) * 200.0f);
                const QSignalBlocker blocker(m_zoomSlider);
                m_zoomSlider->setValue(std::clamp(sliderVal, 0, 200));
                int pct = static_cast<int>(ppb / 128.0f * 100.0f);
                m_zoomLabel->setText(QString("%1%").arg(pct));
            });

    qDebug() << "[WavyArrangementView] Connected to SongEditor";
}

// ---------------------------------------------------------------------------

void WavyArrangementView::onAddPatternTrack()
{
    m_engine->addTrack("pattern", "New Pattern");
}

void WavyArrangementView::onAddSampleTrack()
{
    m_engine->addTrack("sample", "New Sample");
}

void WavyArrangementView::onAddAutomationTrack()
{
    m_engine->addTrack("automation", "New Automation");
}

void WavyArrangementView::onEditModeChanged(int id)
{
    if (!m_songEditor) return;

    switch (id) {
    case 0: m_songEditor->setEditModeDraw();   break;
    case 1: m_songEditor->setEditModeKnife();  break;
    case 2: m_songEditor->setEditModeSelect(); break;
    }
}

void WavyArrangementView::onZoomChanged(int value)
{
    if (!m_songEditor) return;

    // Map slider (0–200) to ppb (4–400)
    float ppb = 4.0f + (static_cast<float>(value) / 200.0f) * (400.0f - 4.0f);
    m_songEditor->setPixelsPerBar(static_cast<int>(ppb));

    int pct = static_cast<int>(ppb / 128.0f * 100.0f);
    m_zoomLabel->setText(QString("%1%").arg(pct));
}

void WavyArrangementView::onTrackListChanged()
{
    int count = m_engine->trackCount();
    m_trackCountLabel->setText(QString("%1 track%2").arg(count).arg(count == 1 ? "" : "s"));
}

// ---------------------------------------------------------------------------

void WavyArrangementView::applyStyle()
{
    setStyleSheet(
        "#WavyArrangeToolbar { background: #16213e; border-bottom: 1px solid #2a2a4a; }"
        "#WavyArrangeAddBtn { background: #1a1a2e; color: #ccc; border: 1px solid #3a3a5a;"
        "  border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
        "#WavyArrangeAddBtn:hover { background: #7c3aed; color: white; border-color: #7c3aed; }"
        "#WavyArrangeEditMode { background: #1a1a2e; color: #aaa; border: 1px solid #3a3a5a;"
        "  border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
        "#WavyArrangeEditMode:checked { background: #7c3aed; color: white; border-color: #7c3aed; }"
        "#WavyArrangeEditMode:hover { background: #2a2a4e; }"
        "#WavyArrangeZoom::groove:horizontal { background: #2a2a3e; height: 4px; border-radius: 2px; }"
        "#WavyArrangeZoom::handle:horizontal { background: #7c3aed; width: 12px; margin: -4px 0;"
        "  border-radius: 6px; }"
    );
}

#endif // WAVY_LMMS_CORE
