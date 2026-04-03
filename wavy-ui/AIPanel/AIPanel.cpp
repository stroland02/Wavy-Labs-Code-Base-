#include "AIPanel.h"
#include "GenerationHistoryWidget.h"
#include "../IPC/AIClient.h"
#include "../LicenseGate/LicenseManager.h"
#include "../ModelManager/ModelManager.h"
#include "../PromptBar/PromptBar.h"
#ifdef WAVY_WEBENGINE
#  include "../CodeToMusic/CodeEditor.h"
#endif

#include <QCheckBox>
#include <QIcon>
#include <QMap>
#include <QScrollBar>
#include <QShortcut>
#include <QTimer>
#include <QToolButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QLineEdit>
#include <QListWidget>
#include <QMdiSubWindow>
#include <QMessageBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QLabel>
#include <QFont>
#include <QPlainTextEdit>
#include <QSizePolicy>
#include <QSplitter>
#include <QDateTime>
#include <QDesktopServices>
#include <QRandomGenerator>
#include <QStackedWidget>
#include <QUrl>
#include <QTextOption>

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

AIPanel::AIPanel(AIClient* client, ModelManager* modelManager, QWidget* parent)
    : QWidget(parent)
    , m_client(client)
    , m_modelManager(modelManager)
{
    buildUI();

    connect(m_client, &AIClient::connected, this, [this]() {
        onModelStatusChanged(true);
        m_modelManager->refreshStatus();
        // Delayed second refresh so apiKeyConfigured reflects the live server state
        QTimer::singleShot(3000, this, [this]() { m_modelManager->refreshStatus(); });
    });
    connect(m_client, &AIClient::disconnected,  this,
            [this]() { onModelStatusChanged(false); });
    connect(m_client, &AIClient::error, this,
            [this](const QString& msg) {
                // Suppress transient errors during connection retries
                if (!m_client->isConnected())
                    showError(msg);
            });

    // Repopulate model combo whenever model status changes (install/uninstall)
    connect(m_modelManager, &ModelManager::modelStatusChanged,
            this, &AIPanel::populateModelCombo);

    // Update free-user flag and daily counter when license tier changes
    connect(LicenseManager::instance(), &LicenseManager::tierChanged,
            this, &AIPanel::onTierChanged);

    onModelStatusChanged(m_client->isConnected());
    onTierChanged(LicenseManager::instance()->tier());  // sets m_isFreeUser + counter
    populateModelCombo();
}

// ---------------------------------------------------------------------------
// MDI wrapper
// ---------------------------------------------------------------------------

QMdiSubWindow* AIPanel::asMdiSubWindow(QWidget* mdiArea)
{
    auto* sub = new QMdiSubWindow(mdiArea);
    sub->setWidget(this);
    sub->setWindowTitle("Wavy Labs — AI");
    sub->resize(640, 480);
    sub->setAttribute(Qt::WA_DeleteOnClose, false);
    return sub;
}

void AIPanel::setPromptContext(const QVariantMap& ctx)
{
    if (m_promptBar)
        m_promptBar->setDawContext(ctx);
}

// ---------------------------------------------------------------------------
// UI construction
// ---------------------------------------------------------------------------

void AIPanel::buildUI()
{
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    // ── Header (flat, 32px, no gradient) ─────────────────────────────────
    auto* header = new QWidget(this);
    header->setObjectName("aiPanelHeader");
    header->setFixedHeight(32);
    auto* headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(10, 0, 10, 0);
    headerLayout->setSpacing(6);

    auto* titleLabel = new QLabel("Wavy Labs", header);
    titleLabel->setObjectName("aiPanelTitle");

    // Separator dot
    auto* dotLabel = new QLabel("·", header);
    dotLabel->setObjectName("aiDailyCounter");

    m_dailyCounterLabel = new QLabel(header);
    m_dailyCounterLabel->setObjectName("aiDailyCounter");

    m_statusLabel = new QLabel("●", header);
    m_statusLabel->setObjectName("aiStatusOffline");

    auto* checkStatusBtn = new QToolButton(header);
    checkStatusBtn->setObjectName("aiCheckStatusBtn");
    checkStatusBtn->setToolTip("Check AI backend status");
    checkStatusBtn->setText("Check");
    checkStatusBtn->setFixedHeight(22);
    connect(checkStatusBtn, &QToolButton::clicked, this, &AIPanel::onCheckStatusClicked);

    headerLayout->addWidget(titleLabel);
    headerLayout->addWidget(dotLabel);
    headerLayout->addWidget(m_dailyCounterLabel);
    headerLayout->addStretch();
    headerLayout->addWidget(m_statusLabel);
    headerLayout->addWidget(checkStatusBtn);
    root->addWidget(header);

    // ── Progress bar (thin, sits right below header) ──────────────────────
    m_progressBar = new QProgressBar(this);
    m_progressBar->setRange(0, 0);   // indeterminate
    m_progressBar->setVisible(false);
    m_progressBar->setObjectName("aiProgressBar");
    m_progressBar->setMaximumHeight(3);
    m_progressBar->setTextVisible(false);
    root->addWidget(m_progressBar);

    // ── Body: NavBar + PageStack ──────────────────────────────────────────
    auto* bodyWidget = new QWidget(this);
    bodyWidget->setObjectName("aiBody");
    auto* bodyLayout = new QHBoxLayout(bodyWidget);
    bodyLayout->setContentsMargins(0, 0, 0, 0);
    bodyLayout->setSpacing(0);

    // NavBar
    m_navBar = new QWidget(bodyWidget);
    m_navBar->setObjectName("aiNavBar");
    m_navBar->setFixedWidth(36);
    auto* navLayout = new QVBoxLayout(m_navBar);
    navLayout->setContentsMargins(0, 4, 0, 4);
    navLayout->setSpacing(2);

    // Button specs: {label for tooltip, resource path}
    struct NavSpec { const char* tip; const char* icon; };
    static const NavSpec specs[kPageCount] = {
        { "Generate",      ":/wavy/nav/generate.svg" },
        { "Vocal / TTS",   ":/wavy/nav/vocal.svg"    },
        { "SFX",           ":/wavy/nav/sfx.svg"      },
        { "Mix / Master",  ":/wavy/nav/mix.svg"      },
        { "Tools",         ":/wavy/nav/tools.svg"    },
        { "Chat",          ":/wavy/nav/chat.svg"     },
        { "Console",       ":/wavy/nav/log.svg"      },
    };

    for (int i = 0; i < kPageCount; ++i) {
        auto* btn = new QToolButton(m_navBar);
        btn->setObjectName("aiNavBtn");
        btn->setToolTip(specs[i].tip);
        btn->setFixedSize(36, 36);
        btn->setCheckable(true);
        btn->setAutoExclusive(false);  // we manage exclusivity manually

        const QIcon ico = QIcon(specs[i].icon);
        if (!ico.isNull()) {
            btn->setIcon(ico);
            btn->setIconSize(QSize(18, 18));
        } else {
            // Fallback: first letter of tooltip
            btn->setText(QString(specs[i].tip[0]));
        }

        connect(btn, &QToolButton::clicked, this, [this, i]() {
            const bool nowChecked = m_navBtns[i]->isChecked();
            if (!nowChecked) {
                // Clicked the already-active tab → collapse to icon strip only
                for (int j = 0; j < kPageCount; ++j)
                    if (m_navBtns[j]) m_navBtns[j]->setChecked(false);
                emit panelCollapsed();
            } else {
                // New tab selected (or re-expanding) → show content
                for (int j = 0; j < kPageCount; ++j)
                    if (m_navBtns[j]) m_navBtns[j]->setChecked(j == i);
                m_pageStack->setCurrentIndex(i);
                emit panelExpanded();
            }
        });

        navLayout->addWidget(btn);
        m_navBtns[i] = btn;
    }
    navLayout->addStretch();

    // PageStack
    m_pageStack = new QStackedWidget(bodyWidget);

    auto* musicPage   = new QWidget;
    auto* vocalPage   = new QWidget;
    auto* sfxPage     = new QWidget;
    auto* mixPage     = new QWidget;
    auto* toolsPage   = new QWidget;
    auto* promptPage  = new QWidget;
    auto* consolePage = new QWidget;

    buildMusicTab(musicPage);
    buildVocalTab(vocalPage);
    buildSFXTab(sfxPage);
    buildMixTab(mixPage);
    buildToolsTab(toolsPage);
    buildPromptTab(promptPage);
    buildConsoleTab(consolePage);

    m_pageStack->addWidget(musicPage);
    m_pageStack->addWidget(vocalPage);
    m_pageStack->addWidget(sfxPage);
    m_pageStack->addWidget(mixPage);
    m_pageStack->addWidget(toolsPage);
    m_pageStack->addWidget(promptPage);
    m_pageStack->addWidget(consolePage);

    bodyLayout->addWidget(m_navBar);           // fixed 36px (set via QSS max-width)
    bodyLayout->addWidget(m_pageStack, 1);     // takes remaining width

    root->addWidget(bodyWidget, 1);

    // Select Generate by default
    if (m_navBtns[0]) m_navBtns[0]->setChecked(true);
    m_pageStack->setCurrentIndex(0);
}

QWidget* AIPanel::detachNavBar()
{
    if (!m_navBar) return nullptr;
    // Remove from parent layout and un-parent so caller can reparent it
    if (auto* lay = m_navBar->parentWidget()
                       ? m_navBar->parentWidget()->layout() : nullptr)
        lay->removeWidget(m_navBar);
    m_navBar->setParent(nullptr);
    return m_navBar;
}

QWidget* AIPanel::takePage(int idx)
{
    if (!m_pageStack || idx < 0 || idx >= m_pageStack->count()) return nullptr;
    QWidget* w = m_pageStack->widget(idx);
    m_pageStack->removeWidget(w);
    // QStackedWidget hides non-current pages; un-hide so content is visible
    // once embedded in the SideBarWidget panel.
    w->show();
    return w;
}

QString AIPanel::currentPage() const
{
    static const QStringList names = {
        "generate", "vocal", "sfx", "mix", "tools", "chat", "console"
    };
    const int idx = m_pageStack ? m_pageStack->currentIndex() : 0;
    return (idx >= 0 && idx < names.size()) ? names[idx] : "generate";
}

void AIPanel::navigateTo(const QString& page)
{
    static const QMap<QString, int> pageMap = {
        {"generate", 0}, {"vocal", 1}, {"sfx", 2}, {"mix", 3},
        {"tools", 4},    {"chat", 5},  {"console", 6},
        // aliases
        {"code", 4}, {"prompt", 5}, {"log", 6},
    };
    const int idx = pageMap.value(page.toLower(), 0);
    for (int j = 0; j < kPageCount; ++j)
        if (m_navBtns[j]) m_navBtns[j]->setChecked(j == idx);
    m_pageStack->setCurrentIndex(idx);
    emit panelExpanded();  // ensure panel is visible if navigated programmatically
}

void AIPanel::buildMusicTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(10);

    // ── Top bar: centered tabs (Simple | Advanced | Sounds), no Model ─────────
    auto* topBar = new QWidget(tab);
    topBar->setObjectName("aiGenerateTopBar");
    auto* topLayout = new QHBoxLayout(topBar);
    topLayout->setContentsMargins(0, 0, 0, 8);
    topLayout->setSpacing(8);

    auto* simpleTabBtn = new QPushButton("Simple", topBar);
    simpleTabBtn->setObjectName("aiGenerateTabBtn");
    simpleTabBtn->setCheckable(true);
    simpleTabBtn->setChecked(true);
    simpleTabBtn->setCursor(Qt::PointingHandCursor);
    auto* advancedTabBtn = new QPushButton("Advanced", topBar);
    advancedTabBtn->setObjectName("aiGenerateTabBtn");
    advancedTabBtn->setCheckable(true);
    advancedTabBtn->setCursor(Qt::PointingHandCursor);
    auto* soundsTabBtn = new QPushButton("Sounds", topBar);
    soundsTabBtn->setObjectName("aiGenerateTabBtn");
    soundsTabBtn->setCheckable(true);
    soundsTabBtn->setCursor(Qt::PointingHandCursor);

    topLayout->addStretch();
    topLayout->addWidget(simpleTabBtn);
    topLayout->addWidget(advancedTabBtn);
    topLayout->addWidget(soundsTabBtn);
    topLayout->addStretch();
    layout->addWidget(topBar);

    // ── Stacked content (one page per tab) ────────────────────────────────────
    m_generateTabStack = new QStackedWidget(tab);

    // ── Page 0: Simple — prompt + inspiration only ───────────────────────────
    auto* simplePage = new QWidget(tab);
    auto* simpleLayout = new QVBoxLayout(simplePage);
    simpleLayout->setContentsMargins(0, 0, 0, 0);
    simpleLayout->setSpacing(10);

    auto* promptGroup = new QGroupBox("Describe your music", simplePage);
    auto* pgl = new QVBoxLayout(promptGroup);
    m_promptEdit = new QTextEdit(promptGroup);
    m_promptEdit->setPlaceholderText(
        "e.g. \"Upbeat lo-fi hip hop with jazz chords and a smooth bass line\"");
    m_promptEdit->setMinimumHeight(52);
    m_promptEdit->setMaximumHeight(120);
    m_promptEdit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    m_promptEdit->setLineWrapMode(QTextEdit::WidgetWidth);
    m_promptEdit->setWordWrapMode(QTextOption::WordWrap);
    pgl->addWidget(m_promptEdit);

    // Bottom center: time and lyrics options (small widgets)
    auto* optionsRow = new QHBoxLayout;
    optionsRow->setSpacing(12);
    optionsRow->addStretch();
    m_promptTimeCombo = new QComboBox(promptGroup);
    m_promptTimeCombo->setObjectName("promptOptionCombo");
    m_promptTimeCombo->addItem("(auto)", 0);
    for (int s : {15, 30, 60, 90, 120, 180, 240})
        m_promptTimeCombo->addItem(QString("%1 s").arg(s), s);
    m_promptTimeCombo->setCurrentIndex(0);
    m_promptTimeCombo->setMinimumContentsLength(6);
    m_promptTimeCombo->setToolTip("Duration");
    optionsRow->addWidget(m_promptTimeCombo);

    m_promptLyricsCombo = new QComboBox(promptGroup);
    m_promptLyricsCombo->setObjectName("promptOptionCombo");
    for (const auto& l : {"(auto)", "None", "Generate", "Custom"})
        m_promptLyricsCombo->addItem(l);
    m_promptLyricsCombo->setCurrentIndex(0);
    m_promptLyricsCombo->setToolTip("Lyrics");
    optionsRow->addWidget(m_promptLyricsCombo);
    optionsRow->addStretch();
    pgl->addLayout(optionsRow);

    simpleLayout->addWidget(promptGroup);

    auto* inspoIdeasLabel = new QLabel("Inspiration", simplePage);
    inspoIdeasLabel->setObjectName("sectionHeader");
    simpleLayout->addWidget(inspoIdeasLabel);

    // Inspiration chips in a wrapping grid so full text is visible in narrow panels
    auto* inspoChipsWidget = new QWidget(simplePage);
    auto* inspoChipsGrid = new QGridLayout(inspoChipsWidget);
    inspoChipsGrid->setSpacing(6);
    inspoChipsGrid->setContentsMargins(0, 0, 0, 0);
    const QStringList ideas = {
        "Upbeat lo-fi hip hop",
        "Chill acoustic guitar",
        "Cinematic trailer",
        "Synthwave 80s",
        "Jazz piano trio",
        "Ambient electronic",
    };
    const int chipsPerRow = 2;
    for (int i = 0; i < ideas.size(); ++i) {
        const QString& idea = ideas.at(i);
        auto* chip = new QPushButton(idea, inspoChipsWidget);
        chip->setObjectName("aiInspoChip");
        chip->setFlat(true);
        chip->setCursor(Qt::PointingHandCursor);
        chip->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Fixed);
        chip->setMinimumWidth(120);
        connect(chip, &QPushButton::clicked, this, [this, idea]() {
            m_promptEdit->setPlainText(idea);
        });
        inspoChipsGrid->addWidget(chip, i / chipsPerRow, i % chipsPerRow);
    }
    simpleLayout->addWidget(inspoChipsWidget);
    simpleLayout->addStretch();
    m_generateTabStack->addWidget(simplePage);

    // ── Page 1: Advanced — Model, settings, reference, influence, advanced panel ─
    auto* advancedPage = new QWidget(tab);
    auto* advancedPageLayout = new QVBoxLayout(advancedPage);
    advancedPageLayout->setContentsMargins(0, 0, 0, 0);
    advancedPageLayout->setSpacing(10);

    auto* ctrlGroup = new QGroupBox("Settings", advancedPage);
    auto* form = new QFormLayout(ctrlGroup);
    form->setLabelAlignment(Qt::AlignRight);

    m_modelCombo = new QComboBox(ctrlGroup);
    m_modelCombo->setObjectName("aiGenerateModelCombo");
    m_modelCombo->setMinimumWidth(180);
    form->addRow("Model:", m_modelCombo);

    m_genreCombo = new QComboBox(ctrlGroup);
    for (const auto& g : {"(auto)", "Lo-Fi", "Pop", "Rock", "Jazz", "Electronic",
                           "Classical", "Hip-Hop", "Ambient", "Metal", "R&B"})
        m_genreCombo->addItem(g);
    form->addRow("Genre:", m_genreCombo);

    m_keyCombo = new QComboBox(ctrlGroup);
    for (const auto& k : {"(auto)", "C major", "G major", "D major", "A major",
                           "E major", "B major", "F# major", "C minor", "G minor",
                           "D minor", "A minor", "E minor"})
        m_keyCombo->addItem(k);
    form->addRow("Key:", m_keyCombo);

    m_tempoCombo = new QComboBox(ctrlGroup);
    m_tempoCombo->addItem("(auto)", 0);
    for (int bpm = 80; bpm <= 180; bpm += 20)
        m_tempoCombo->addItem(QString("%1 BPM").arg(bpm), bpm);
    form->addRow("Tempo:", m_tempoCombo);

    m_durationCombo = new QComboBox(ctrlGroup);
    m_durationCombo->addItem("(auto)", 0);
    for (int s : {15, 30, 60, 90, 120, 180, 240})
        m_durationCombo->addItem(QString("%1 s").arg(s), s);
    form->addRow("Duration:", m_durationCombo);

    m_lyricsCombo = new QComboBox(ctrlGroup);
    for (const auto& l : {"(auto)", "None", "Generate", "Custom"})
        m_lyricsCombo->addItem(l);
    form->addRow("Lyrics:", m_lyricsCombo);

    auto* customLyricsGroup = new QGroupBox("Type lyrics here", advancedPage);
    customLyricsGroup->setObjectName("customLyricsGroup");
    auto* cleLayout = new QVBoxLayout(customLyricsGroup);
    m_customLyricsEdit = new QTextEdit(customLyricsGroup);
    m_customLyricsEdit->setPlaceholderText(
        "Write some lyrics or a prompt — or leave blank for instrumental.");
    m_customLyricsEdit->setMaximumHeight(100);
    m_customLyricsEdit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    cleLayout->addWidget(m_customLyricsEdit);
    // Show custom lyrics section only when Lyrics is "Custom"
    auto updateCustomLyricsVisibility = [customLyricsGroup, this]() {
        customLyricsGroup->setVisible(m_lyricsCombo && m_lyricsCombo->currentText() == "Custom");
    };
    updateCustomLyricsVisibility();
    connect(m_lyricsCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, updateCustomLyricsVisibility);

    m_sectionStructureChk = new QCheckBox(ctrlGroup);
    m_sectionStructureChk->setChecked(true);
    m_sectionStructureChk->setText("Section song structure (Intro, Verse, Chorus, etc.)");
    m_sectionStructureChk->setToolTip("When on, generated track can be split into labeled sections when added to the DAW.");
    form->addRow("", m_sectionStructureChk);

    m_advancedStemGenerationCombo = new QComboBox(ctrlGroup);
    m_advancedStemGenerationCombo->setToolTip("When On, automatically split generated music into stems after generation using the stem-splitting algorithm.");
    m_advancedStemGenerationCombo->addItem("Off", 0);
    m_advancedStemGenerationCombo->addItem("On (2 stems — vocals + backing)", 2);
    m_advancedStemGenerationCombo->addItem("On (4 stems — vocals / drums / bass / other)", 4);
    m_advancedStemGenerationCombo->addItem("On (6 stems — Studio)", 6);
    form->addRow("Stem generation:", m_advancedStemGenerationCombo);

    advancedPageLayout->addWidget(ctrlGroup);
    advancedPageLayout->addWidget(customLyricsGroup);

    auto* inspoGroup = new QGroupBox("Reference tracks (Inspo)", advancedPage);
    inspoGroup->setCheckable(false);
    auto* inspoLayout = new QVBoxLayout(inspoGroup);
    inspoLayout->setSpacing(4);

    m_inspoList = new QListWidget(inspoGroup);
    m_inspoList->setMaximumHeight(60);
    inspoLayout->addWidget(m_inspoList);

    auto* inspoRow = new QHBoxLayout;
    m_inspoAddBtn = new QPushButton("+ Add", inspoGroup);
    connect(m_inspoAddBtn, &QPushButton::clicked, this, [this]() {
        if (m_inspoList->count() >= 4) return;
        const QString p = QFileDialog::getOpenFileName(
            this, "Reference Audio", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) m_inspoList->addItem(p);
    });
    auto* inspoClearBtn = new QPushButton("Clear", inspoGroup);
    connect(inspoClearBtn, &QPushButton::clicked, m_inspoList, &QListWidget::clear);
    inspoRow->addWidget(m_inspoAddBtn);
    inspoRow->addWidget(inspoClearBtn);
    inspoRow->addStretch();
    inspoLayout->addLayout(inspoRow);
    advancedPageLayout->addWidget(inspoGroup);

    auto* influenceRow = new QHBoxLayout;
    auto* influenceLbl = new QLabel("Influence:", advancedPage);
    influenceLbl->setFixedWidth(60);
    m_influenceSlider = new QSlider(Qt::Horizontal, advancedPage);
    m_influenceSlider->setRange(0, 100);
    m_influenceSlider->setValue(50);
    m_influenceLabel = new QLabel("50%", advancedPage);
    m_influenceLabel->setFixedWidth(36);
    connect(m_influenceSlider, &QSlider::valueChanged, this,
            [this](int v) { m_influenceLabel->setText(QString("%1%").arg(v)); });
    influenceRow->addWidget(influenceLbl);
    influenceRow->addWidget(m_influenceSlider, 1);
    influenceRow->addWidget(m_influenceLabel);
    advancedPageLayout->addLayout(influenceRow);

    advancedPageLayout->addStretch();
    m_generateTabStack->addWidget(advancedPage);

    // Keep prompt card time/lyrics in sync with Advanced duration/lyrics
    connect(m_promptTimeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, [this](int idx) {
                if (m_durationCombo && m_durationCombo->currentIndex() != idx) {
                    m_durationCombo->blockSignals(true);
                    m_durationCombo->setCurrentIndex(idx);
                    m_durationCombo->blockSignals(false);
                }
            });
    connect(m_durationCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, [this](int idx) {
                if (m_promptTimeCombo && m_promptTimeCombo->currentIndex() != idx) {
                    m_promptTimeCombo->blockSignals(true);
                    m_promptTimeCombo->setCurrentIndex(idx);
                    m_promptTimeCombo->blockSignals(false);
                }
            });
    connect(m_promptLyricsCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, [this](int idx) {
                if (m_lyricsCombo && m_lyricsCombo->currentIndex() != idx) {
                    m_lyricsCombo->blockSignals(true);
                    m_lyricsCombo->setCurrentIndex(idx);
                    m_lyricsCombo->blockSignals(false);
                }
            });
    connect(m_lyricsCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, [this](int idx) {
                if (m_promptLyricsCombo && m_promptLyricsCombo->currentIndex() != idx) {
                    m_promptLyricsCombo->blockSignals(true);
                    m_promptLyricsCombo->setCurrentIndex(idx);
                    m_promptLyricsCombo->blockSignals(false);
                }
            });

    // ── Page 2: Sounds — stem generation + stems (canonical controls) ──────────
    auto* soundsPage = new QWidget(tab);
    auto* soundsLayout = new QVBoxLayout(soundsPage);
    soundsLayout->setContentsMargins(0, 0, 0, 0);
    soundsLayout->setSpacing(10);

    auto* soundsStemGroup = new QGroupBox("Stem Generation", soundsPage);
    auto* ssgLayout = new QVBoxLayout(soundsStemGroup);
    ssgLayout->setSpacing(6);

    auto* ssgForm = new QFormLayout;
    m_stemCountCombo = new QComboBox(soundsStemGroup);
    m_stemCountCombo->setToolTip("Automatically split generated music into stems after generation");
    m_stemCountCombo->addItem("No split  (single track)", 0);
    m_stemCountCombo->addItem("2 stems  (vocals + backing)", 2);
    m_stemCountCombo->addItem("4 stems  (vocals / drums / bass / other)", 4);
    m_stemCountCombo->addItem("6 stems  (Studio)", 6);
    ssgForm->addRow("Stems:", m_stemCountCombo);

    m_stemTypeCombo = new QComboBox(soundsStemGroup);
    for (const auto& t : {"drums", "bass", "melody", "harmony", "full"})
        m_stemTypeCombo->addItem(t);
    ssgForm->addRow("Stem Type:", m_stemTypeCombo);
    ssgLayout->addLayout(ssgForm);

    auto* ssgRefRow = new QHBoxLayout;
    m_stemRefLabel = new QLabel("No reference file", soundsStemGroup);
    m_stemRefLabel->setWordWrap(true);
    m_stemRefBtn = new QPushButton("Browse", soundsStemGroup);
    connect(m_stemRefBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Reference Audio", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_stemRefPath = p; m_stemRefLabel->setText(p); }
    });
    ssgRefRow->addWidget(m_stemRefLabel, 1);
    ssgRefRow->addWidget(m_stemRefBtn);
    ssgLayout->addLayout(ssgRefRow);

    m_generateStemBtn = new QPushButton("Generate Stem", soundsStemGroup);
    m_generateStemBtn->setObjectName("aiGenerateBtn");
    m_generateStemBtn->setMinimumHeight(34);
    connect(m_generateStemBtn, &QPushButton::clicked, this, &AIPanel::onGenerateStemClicked);
    ssgLayout->addWidget(m_generateStemBtn);
    soundsLayout->addWidget(soundsStemGroup);

    soundsLayout->addStretch();
    m_generateTabStack->addWidget(soundsPage);

    layout->addWidget(m_generateTabStack, 1);

    // ── Create button (right above Generations) ─────────────────────────────────
    m_generateBtn = new QPushButton("\u266B  Create", tab);
    m_generateBtn->setObjectName("aiCreateBtn");
    m_generateBtn->setMinimumHeight(44);
    m_generateBtn->setToolTip("Generate music from the prompt");
    connect(m_generateBtn, &QPushButton::clicked, this, &AIPanel::onGenerateClicked);
    layout->addWidget(m_generateBtn);

    // Generations (smaller area, fixed max height)
    m_history = new GenerationHistoryWidget(tab);
    m_history->setMaximumHeight(200);
    layout->addWidget(m_history);
    connect(m_history, &GenerationHistoryWidget::entryInsertRequested,
            this, [this](const QString& audioPath, const QString& trackName, const QVariantList& sections) {
                emit insertRequested(audioPath, trackName, sections);
            });
    connect(m_history, &GenerationHistoryWidget::entryPlayRequested,
            this, [](const QString& audioPath) {
                const QFileInfo fi(audioPath);
                if (fi.exists())
                    QDesktopServices::openUrl(QUrl::fromLocalFile(fi.absoluteFilePath()));
            });

    // Wire tab buttons
    auto setGenerateTab = [this, simpleTabBtn, advancedTabBtn, soundsTabBtn](int idx) {
        m_generateTabStack->setCurrentIndex(idx);
        simpleTabBtn->setChecked(idx == 0);
        advancedTabBtn->setChecked(idx == 1);
        soundsTabBtn->setChecked(idx == 2);
    };
    connect(simpleTabBtn, &QPushButton::clicked, this, [setGenerateTab]() { setGenerateTab(0); });
    connect(advancedTabBtn, &QPushButton::clicked, this, [setGenerateTab]() { setGenerateTab(1); });
    connect(soundsTabBtn, &QPushButton::clicked, this, [setGenerateTab]() { setGenerateTab(2); });

    // When user selects "Custom" lyrics, switch to Advanced tab and focus the lyrics text area
    auto goToCustomLyrics = [this, setGenerateTab]() {
        if (m_lyricsCombo && m_lyricsCombo->currentText() == "Custom") {
            setGenerateTab(1);
            if (m_customLyricsEdit)
                m_customLyricsEdit->setFocus();
        }
    };
    connect(m_lyricsCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, goToCustomLyrics);
    connect(m_promptLyricsCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, goToCustomLyrics);
}

void AIPanel::buildVocalTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(10);

    // Page selector
    auto* pageRow = new QHBoxLayout;
    auto* ttsPageBtn = new QPushButton("Text-to-Speech", tab);
    auto* stsPageBtn = new QPushButton("Speech-to-Speech", tab);
    auto* clonePageBtn = new QPushButton("Voice Clone", tab);
    ttsPageBtn->setCheckable(true);
    stsPageBtn->setCheckable(true);
    clonePageBtn->setCheckable(true);
    ttsPageBtn->setChecked(true);
    pageRow->addWidget(ttsPageBtn);
    pageRow->addWidget(stsPageBtn);
    pageRow->addWidget(clonePageBtn);
    layout->addLayout(pageRow);

    m_vocalStack = new QStackedWidget(tab);

    // ── Page 0: TTS ──────────────────────────────────────────────────────
    auto* ttsPage = new QWidget;
    auto* ttsLayout = new QVBoxLayout(ttsPage);
    ttsLayout->setContentsMargins(0, 8, 0, 0);

    // Persona row
    auto* personaRow = new QHBoxLayout;
    personaRow->addWidget(new QLabel("Persona:", ttsPage));
    m_personaCombo = new QComboBox(ttsPage);
    m_personaCombo->addItem("(Default)");
    personaRow->addWidget(m_personaCombo, 1);
    personaRow->addWidget(new QLabel("Save as:", ttsPage));
    m_personaNameEdit = new QLineEdit(ttsPage);
    m_personaNameEdit->setPlaceholderText("Name");
    m_personaNameEdit->setFixedWidth(90);
    personaRow->addWidget(m_personaNameEdit);
    m_personaSaveBtn = new QPushButton("Save", ttsPage);
    m_personaSaveBtn->setFixedWidth(50);
    connect(m_personaSaveBtn, &QPushButton::clicked, this, &AIPanel::onSavePersonaClicked);
    personaRow->addWidget(m_personaSaveBtn);
    ttsLayout->addLayout(personaRow);

    // Load personas from backend on first show
    m_client->loadPersonas([this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onLoadPersonasFinished(ok, res);
        }, Qt::QueuedConnection);
    });

    // Apply persona when combo changes
    connect(m_personaCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
        [this](int idx) {
            if (idx <= 0 || !m_personaCombo) return;
            const QString name = m_personaCombo->currentText();
            // find in combo's user data (stored as QVariantMap)
            const QVariant data = m_personaCombo->itemData(idx);
            if (!data.isValid()) return;
            const QVariantMap persona = data.toMap();
            // Apply settings
            if (m_voiceCombo) {
                int vi = m_voiceCombo->findData(persona.value("voice_id").toString());
                if (vi >= 0) m_voiceCombo->setCurrentIndex(vi);
            }
            if (m_stabilitySlider)
                m_stabilitySlider->setValue(qRound(persona.value("stability", 0.5).toDouble() * 100));
            if (m_similaritySlider)
                m_similaritySlider->setValue(qRound(persona.value("similarity", 0.75).toDouble() * 100));
        });

    m_ttsTextEdit = new QTextEdit(ttsPage);
    m_ttsTextEdit->setPlaceholderText("Enter text to convert to speech ...");
    m_ttsTextEdit->setFixedHeight(80);
    ttsLayout->addWidget(m_ttsTextEdit);

    auto* ttsForm = new QFormLayout;
    m_voiceCombo = new QComboBox(ttsPage);
    m_voiceCombo->addItem("George (Default)", "JBFqnCBsd6RMkjVDRZzb");
    ttsForm->addRow("Voice:", m_voiceCombo);

    m_ttsModelCombo = new QComboBox(ttsPage);
    m_ttsModelCombo->addItem("Multilingual v2 (Recommended)", "eleven_multilingual_v2");
    m_ttsModelCombo->addItem("Flash v2.5", "eleven_flash_v2_5");
    m_ttsModelCombo->addItem("English v1", "eleven_monolingual_v1");
    ttsForm->addRow("Model:", m_ttsModelCombo);

    auto* stabRow = new QHBoxLayout;
    m_stabilitySlider = new QSlider(Qt::Horizontal, ttsPage);
    m_stabilitySlider->setRange(0, 100);
    m_stabilitySlider->setValue(50);
    auto* stabLabel = new QLabel("0.50", ttsPage);
    stabLabel->setFixedWidth(36);
    connect(m_stabilitySlider, &QSlider::valueChanged, ttsPage,
            [stabLabel](int v) { stabLabel->setText(QString::number(v / 100.0, 'f', 2)); });
    stabRow->addWidget(m_stabilitySlider);
    stabRow->addWidget(stabLabel);
    ttsForm->addRow("Stability:", stabRow);

    auto* simRow = new QHBoxLayout;
    m_similaritySlider = new QSlider(Qt::Horizontal, ttsPage);
    m_similaritySlider->setRange(0, 100);
    m_similaritySlider->setValue(75);
    auto* simLabel = new QLabel("0.75", ttsPage);
    simLabel->setFixedWidth(36);
    connect(m_similaritySlider, &QSlider::valueChanged, ttsPage,
            [simLabel](int v) { simLabel->setText(QString::number(v / 100.0, 'f', 2)); });
    simRow->addWidget(m_similaritySlider);
    simRow->addWidget(simLabel);
    ttsForm->addRow("Similarity:", simRow);

    ttsLayout->addLayout(ttsForm);

    m_ttsBtn = new QPushButton("Generate Speech", ttsPage);
    m_ttsBtn->setObjectName("aiGenerateBtn");
    m_ttsBtn->setMinimumHeight(40);
    connect(m_ttsBtn, &QPushButton::clicked, this, &AIPanel::onTTSClicked);
    ttsLayout->addWidget(m_ttsBtn);
    ttsLayout->addStretch();
    m_vocalStack->addWidget(ttsPage);

    // ── Page 1: Speech-to-Speech ─────────────────────────────────────────
    auto* stsPage = new QWidget;
    auto* stsLayout = new QVBoxLayout(stsPage);
    stsLayout->setContentsMargins(0, 8, 0, 0);

    auto* stsBrowseRow = new QHBoxLayout;
    m_stsFileLabel = new QLabel("No file selected.", stsPage);
    m_stsFileLabel->setWordWrap(true);
    auto* stsBrowseBtn = new QPushButton("Browse ...", stsPage);
    connect(stsBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Source Audio", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_stsFilePath = p; m_stsFileLabel->setText(p); }
    });
    stsBrowseRow->addWidget(m_stsFileLabel, 1);
    stsBrowseRow->addWidget(stsBrowseBtn);
    stsLayout->addLayout(stsBrowseRow);

    auto* stsForm = new QFormLayout;
    m_stsVoiceCombo = new QComboBox(stsPage);
    m_stsVoiceCombo->addItem("George (Default)", "JBFqnCBsd6RMkjVDRZzb");
    stsForm->addRow("Target Voice:", m_stsVoiceCombo);
    stsLayout->addLayout(stsForm);

    m_stsBtn = new QPushButton("Convert Voice", stsPage);
    m_stsBtn->setObjectName("aiGenerateBtn");
    m_stsBtn->setMinimumHeight(40);
    connect(m_stsBtn, &QPushButton::clicked, this, &AIPanel::onSTSClicked);
    stsLayout->addWidget(m_stsBtn);
    stsLayout->addStretch();
    m_vocalStack->addWidget(stsPage);

    // ── Page 2: Voice Clone ──────────────────────────────────────────────
    auto* clonePage = new QWidget;
    auto* cloneLayout = new QVBoxLayout(clonePage);
    cloneLayout->setContentsMargins(0, 8, 0, 0);

    auto* cloneForm = new QFormLayout;
    m_cloneNameEdit = new QLineEdit(clonePage);
    m_cloneNameEdit->setPlaceholderText("My Cloned Voice");
    cloneForm->addRow("Voice Name:", m_cloneNameEdit);
    cloneLayout->addLayout(cloneForm);

    m_cloneFileList = new QListWidget(clonePage);
    m_cloneFileList->setMaximumHeight(80);
    cloneLayout->addWidget(m_cloneFileList);

    auto* cloneAddBtn = new QPushButton("+ Add Audio Sample", clonePage);
    connect(cloneAddBtn, &QPushButton::clicked, this, [this]() {
        const QStringList files = QFileDialog::getOpenFileNames(
            this, "Voice Samples", {}, "Audio (*.wav *.mp3 *.flac)");
        for (const auto& f : files)
            m_cloneFileList->addItem(f);
    });
    cloneLayout->addWidget(cloneAddBtn);

    m_cloneBtn = new QPushButton("Clone Voice", clonePage);
    m_cloneBtn->setObjectName("aiGenerateBtn");
    m_cloneBtn->setMinimumHeight(40);
    connect(m_cloneBtn, &QPushButton::clicked, this, &AIPanel::onVoiceCloneClicked);
    cloneLayout->addWidget(m_cloneBtn);

    m_cloneResultLabel = new QLabel(clonePage);
    m_cloneResultLabel->setWordWrap(true);
    cloneLayout->addWidget(m_cloneResultLabel);
    cloneLayout->addStretch();
    m_vocalStack->addWidget(clonePage);

    layout->addWidget(m_vocalStack, 1);

    // Wire page buttons
    connect(ttsPageBtn, &QPushButton::clicked, this, [this, ttsPageBtn, stsPageBtn, clonePageBtn]() {
        m_vocalStack->setCurrentIndex(0);
        ttsPageBtn->setChecked(true); stsPageBtn->setChecked(false); clonePageBtn->setChecked(false);
    });
    connect(stsPageBtn, &QPushButton::clicked, this, [this, ttsPageBtn, stsPageBtn, clonePageBtn]() {
        m_vocalStack->setCurrentIndex(1);
        ttsPageBtn->setChecked(false); stsPageBtn->setChecked(true); clonePageBtn->setChecked(false);
    });
    connect(clonePageBtn, &QPushButton::clicked, this, [this, ttsPageBtn, stsPageBtn, clonePageBtn]() {
        m_vocalStack->setCurrentIndex(2);
        ttsPageBtn->setChecked(false); stsPageBtn->setChecked(false); clonePageBtn->setChecked(true);
    });

    // Populate voice combos from ElevenLabs
    populateVoiceCombo();
}

void AIPanel::buildMixTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(12);

    auto* proNotice = new QLabel(
        "🔒  AI Mix/Master requires <b>Pro</b> ($9.99/mo).", tab);
    proNotice->setObjectName("proGate");
    proNotice->setWordWrap(true);
    layout->addWidget(proNotice);

    m_mixInputLabel = new QLabel("No audio selected.", tab);
    m_mixInputLabel->setWordWrap(true);
    layout->addWidget(m_mixInputLabel);

    auto* btnRow = new QHBoxLayout;
    m_analyzeBtn = new QPushButton("🔬  Analyze Mix", tab);
    m_masterBtn  = new QPushButton("🏆  Master Audio", tab);
    m_analyzeBtn->setMinimumHeight(36);
    m_masterBtn->setMinimumHeight(36);
    connect(m_analyzeBtn, &QPushButton::clicked, this, &AIPanel::onAnalyzeClicked);
    connect(m_masterBtn,  &QPushButton::clicked, this, &AIPanel::onMasterClicked);
    btnRow->addWidget(m_analyzeBtn);
    btnRow->addWidget(m_masterBtn);
    layout->addLayout(btnRow);

    m_mixResultLabel = new QLabel(tab);
    m_mixResultLabel->setWordWrap(true);
    m_mixResultLabel->setObjectName("mixResultLabel");
    layout->addWidget(m_mixResultLabel);

    // ── AI Auto-Mix ───────────────────────────────────────────────────────────
    auto* autoMixRow = new QHBoxLayout;
    m_autoMixBtn = new QPushButton("\u2728  AI Auto-Mix", tab);
    m_autoMixBtn->setMinimumHeight(36);
    m_autoMixBtn->setToolTip("Analyze all tracks and automatically apply gain/pan corrections");
    connect(m_autoMixBtn, &QPushButton::clicked, this, &AIPanel::onAutoMixClicked);
    m_autoMixResultLabel = new QLabel("\u2014", tab);
    m_autoMixResultLabel->setWordWrap(true);
    autoMixRow->addWidget(m_autoMixBtn);
    autoMixRow->addWidget(m_autoMixResultLabel, 1);
    layout->addLayout(autoMixRow);

    layout->addStretch();
}

void AIPanel::buildSFXTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(10);

    auto* proNotice = new QLabel(
        "SFX Generation requires <b>Pro</b> ($9.99/mo).", tab);
    proNotice->setObjectName("proGate");
    proNotice->setWordWrap(true);
    layout->addWidget(proNotice);

    auto* promptGroup = new QGroupBox("Describe the sound effect", tab);
    auto* pgl = new QVBoxLayout(promptGroup);
    m_sfxPromptEdit = new QTextEdit(promptGroup);
    m_sfxPromptEdit->setPlaceholderText(
        "e.g. \"Thunder crash with rain\", \"Sci-fi laser beam\", \"Footsteps on gravel\"");
    m_sfxPromptEdit->setFixedHeight(72);
    pgl->addWidget(m_sfxPromptEdit);
    layout->addWidget(promptGroup);

    auto* form = new QFormLayout;
    auto* durRow = new QHBoxLayout;
    m_sfxDurationSlider = new QSlider(Qt::Horizontal, tab);
    m_sfxDurationSlider->setRange(1, 30);
    m_sfxDurationSlider->setValue(5);
    m_sfxDurationLabel = new QLabel("5 s", tab);
    m_sfxDurationLabel->setFixedWidth(40);
    connect(m_sfxDurationSlider, &QSlider::valueChanged, this,
            [this](int v) { m_sfxDurationLabel->setText(QString("%1 s").arg(v)); });
    durRow->addWidget(m_sfxDurationSlider);
    durRow->addWidget(m_sfxDurationLabel);
    form->addRow("Duration:", durRow);
    layout->addLayout(form);

    m_sfxBtn = new QPushButton("Generate SFX", tab);
    m_sfxBtn->setObjectName("aiGenerateBtn");
    m_sfxBtn->setMinimumHeight(40);
    connect(m_sfxBtn, &QPushButton::clicked, this, &AIPanel::onSFXClicked);
    layout->addWidget(m_sfxBtn);
    layout->addStretch();
}

void AIPanel::buildToolsTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(10);

    // Page selector
    auto* pageRow = new QHBoxLayout;
    auto* isolatePageBtn    = new QPushButton("Voice Isolator", tab);
    auto* transcribePageBtn = new QPushButton("Transcribe", tab);
    auto* alignPageBtn      = new QPushButton("Alignment", tab);
    auto* dubPageBtn        = new QPushButton("AI Dubbing", tab);
    auto* replacePageBtn    = new QPushButton("Replace Section", tab);
    auto* a2mPageBtn        = new QPushButton("Audio→MIDI", tab);
    isolatePageBtn->setCheckable(true);
    transcribePageBtn->setCheckable(true);
    alignPageBtn->setCheckable(true);
    dubPageBtn->setCheckable(true);
    replacePageBtn->setCheckable(true);
    a2mPageBtn->setCheckable(true);
    isolatePageBtn->setChecked(true);
    pageRow->addWidget(isolatePageBtn);
    pageRow->addWidget(transcribePageBtn);
    pageRow->addWidget(alignPageBtn);
    pageRow->addWidget(dubPageBtn);
    pageRow->addWidget(replacePageBtn);
    pageRow->addWidget(a2mPageBtn);
    layout->addLayout(pageRow);

    m_toolsStack = new QStackedWidget(tab);

    // ── Page 0: Voice Isolator ───────────────────────────────────────────
    auto* isolatePage = new QWidget;
    auto* isoLayout = new QVBoxLayout(isolatePage);
    isoLayout->setContentsMargins(0, 8, 0, 0);

    auto* isoBrowseRow = new QHBoxLayout;
    m_isolateFileLabel = new QLabel("No file selected.", isolatePage);
    m_isolateFileLabel->setWordWrap(true);
    auto* isoBrowseBtn = new QPushButton("Browse ...", isolatePage);
    connect(isoBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio to Isolate", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_isolateFilePath = p; m_isolateFileLabel->setText(p); }
    });
    isoBrowseRow->addWidget(m_isolateFileLabel, 1);
    isoBrowseRow->addWidget(isoBrowseBtn);
    isoLayout->addLayout(isoBrowseRow);

    m_isolateBtn = new QPushButton("Isolate Vocals", isolatePage);
    m_isolateBtn->setObjectName("aiGenerateBtn");
    m_isolateBtn->setMinimumHeight(40);
    connect(m_isolateBtn, &QPushButton::clicked, this, &AIPanel::onVoiceIsolateClicked);
    isoLayout->addWidget(m_isolateBtn);
    isoLayout->addStretch();
    m_toolsStack->addWidget(isolatePage);

    // ── Page 1: Transcribe ───────────────────────────────────────────────
    auto* transcribePage = new QWidget;
    auto* trLayout = new QVBoxLayout(transcribePage);
    trLayout->setContentsMargins(0, 8, 0, 0);

    auto* trBrowseRow = new QHBoxLayout;
    m_transcribeFileLabel = new QLabel("No file selected.", transcribePage);
    m_transcribeFileLabel->setWordWrap(true);
    auto* trBrowseBtn = new QPushButton("Browse ...", transcribePage);
    connect(trBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio to Transcribe", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_transcribeFilePath = p; m_transcribeFileLabel->setText(p); }
    });
    trBrowseRow->addWidget(m_transcribeFileLabel, 1);
    trBrowseRow->addWidget(trBrowseBtn);
    trLayout->addLayout(trBrowseRow);

    auto* trForm = new QFormLayout;
    m_transcribeLangCombo = new QComboBox(transcribePage);
    for (const auto& lang : {"en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"})
        m_transcribeLangCombo->addItem(lang);
    trForm->addRow("Language:", m_transcribeLangCombo);
    trLayout->addLayout(trForm);

    m_transcribeBtn = new QPushButton("Transcribe", transcribePage);
    m_transcribeBtn->setObjectName("aiGenerateBtn");
    m_transcribeBtn->setMinimumHeight(40);
    connect(m_transcribeBtn, &QPushButton::clicked, this, &AIPanel::onTranscribeClicked);
    trLayout->addWidget(m_transcribeBtn);

    m_transcribeResult = new QTextEdit(transcribePage);
    m_transcribeResult->setReadOnly(true);
    m_transcribeResult->setPlaceholderText("Transcription will appear here ...");
    trLayout->addWidget(m_transcribeResult, 1);
    m_toolsStack->addWidget(transcribePage);

    // ── Page 2: Forced Alignment ─────────────────────────────────────────
    auto* alignPage = new QWidget;
    auto* alLayout = new QVBoxLayout(alignPage);
    alLayout->setContentsMargins(0, 8, 0, 0);

    auto* alBrowseRow = new QHBoxLayout;
    m_alignFileLabel = new QLabel("No file selected.", alignPage);
    m_alignFileLabel->setWordWrap(true);
    auto* alBrowseBtn = new QPushButton("Browse ...", alignPage);
    connect(alBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio for Alignment", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_alignFilePath = p; m_alignFileLabel->setText(p); }
    });
    alBrowseRow->addWidget(m_alignFileLabel, 1);
    alBrowseRow->addWidget(alBrowseBtn);
    alLayout->addLayout(alBrowseRow);

    m_alignTextEdit = new QTextEdit(alignPage);
    m_alignTextEdit->setPlaceholderText("Enter text to align with the audio ...");
    m_alignTextEdit->setFixedHeight(72);
    alLayout->addWidget(m_alignTextEdit);

    m_alignBtn = new QPushButton("Align", alignPage);
    m_alignBtn->setObjectName("aiGenerateBtn");
    m_alignBtn->setMinimumHeight(40);
    connect(m_alignBtn, &QPushButton::clicked, this, &AIPanel::onForcedAlignClicked);
    alLayout->addWidget(m_alignBtn);

    m_alignResultLabel = new QLabel(alignPage);
    m_alignResultLabel->setWordWrap(true);
    alLayout->addWidget(m_alignResultLabel);
    alLayout->addStretch();
    m_toolsStack->addWidget(alignPage);

    // ── Page 3: AI Dubbing ───────────────────────────────────────────────
    auto* dubPage = new QWidget;
    auto* dubLayout = new QVBoxLayout(dubPage);
    dubLayout->setContentsMargins(0, 8, 0, 0);

    auto* dubBrowseRow = new QHBoxLayout;
    m_dubFileLabel = new QLabel("No file selected.", dubPage);
    m_dubFileLabel->setWordWrap(true);
    auto* dubBrowseBtn = new QPushButton("Browse ...", dubPage);
    connect(dubBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio to Dub", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_dubFilePath = p; m_dubFileLabel->setText(p); }
    });
    dubBrowseRow->addWidget(m_dubFileLabel, 1);
    dubBrowseRow->addWidget(dubBrowseBtn);
    dubLayout->addLayout(dubBrowseRow);

    auto* dubForm = new QFormLayout;
    m_dubSourceLangCombo = new QComboBox(dubPage);
    m_dubTargetLangCombo = new QComboBox(dubPage);
    for (const auto& lang : {"en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh",
                              "ar", "hi", "ru", "pl", "nl", "sv", "tr"}) {
        m_dubSourceLangCombo->addItem(lang);
        m_dubTargetLangCombo->addItem(lang);
    }
    m_dubTargetLangCombo->setCurrentIndex(1);  // default target: es
    dubForm->addRow("Source:", m_dubSourceLangCombo);
    dubForm->addRow("Target:", m_dubTargetLangCombo);
    dubLayout->addLayout(dubForm);

    m_dubBtn = new QPushButton("Dub Audio", dubPage);
    m_dubBtn->setObjectName("aiGenerateBtn");
    m_dubBtn->setMinimumHeight(40);
    connect(m_dubBtn, &QPushButton::clicked, this, &AIPanel::onDubClicked);
    dubLayout->addWidget(m_dubBtn);
    dubLayout->addStretch();
    m_toolsStack->addWidget(dubPage);

    // ── Page 4: Replace Section ──────────────────────────────────────────
    auto* replacePage = new QWidget;
    auto* replLayout = new QVBoxLayout(replacePage);
    replLayout->setContentsMargins(0, 8, 0, 0);

    auto* replBrowseRow = new QHBoxLayout;
    m_replaceFileLabel = new QLabel("No file selected.", replacePage);
    m_replaceFileLabel->setWordWrap(true);
    auto* replBrowseBtn = new QPushButton("Browse ...", replacePage);
    connect(replBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio to Edit", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_replaceFilePath = p; m_replaceFileLabel->setText(p); }
    });
    replBrowseRow->addWidget(m_replaceFileLabel, 1);
    replBrowseRow->addWidget(replBrowseBtn);
    replLayout->addLayout(replBrowseRow);

    auto* replTimeForm = new QFormLayout;
    m_replaceStartSpin = new QDoubleSpinBox(replacePage);
    m_replaceStartSpin->setRange(0, 3600);
    m_replaceStartSpin->setValue(0.0);
    m_replaceStartSpin->setSuffix(" s");
    m_replaceStartSpin->setSingleStep(0.5);
    replTimeForm->addRow("Start:", m_replaceStartSpin);

    m_replaceEndSpin = new QDoubleSpinBox(replacePage);
    m_replaceEndSpin->setRange(0, 3600);
    m_replaceEndSpin->setValue(5.0);
    m_replaceEndSpin->setSuffix(" s");
    m_replaceEndSpin->setSingleStep(0.5);
    replTimeForm->addRow("End:", m_replaceEndSpin);
    replLayout->addLayout(replTimeForm);

    m_replacePromptEdit = new QTextEdit(replacePage);
    m_replacePromptEdit->setPlaceholderText("Describe the replacement sound...");
    m_replacePromptEdit->setFixedHeight(64);
    replLayout->addWidget(m_replacePromptEdit);

    m_replaceBtn = new QPushButton("Replace Section", replacePage);
    m_replaceBtn->setObjectName("aiGenerateBtn");
    m_replaceBtn->setMinimumHeight(40);
    connect(m_replaceBtn, &QPushButton::clicked, this, &AIPanel::onReplaceSectionClicked);
    replLayout->addWidget(m_replaceBtn);
    replLayout->addStretch();
    m_toolsStack->addWidget(replacePage);

    // ── Page 5: Audio to MIDI ────────────────────────────────────────────
    auto* a2mPage = new QWidget;
    auto* a2mLayout = new QVBoxLayout(a2mPage);
    a2mLayout->setContentsMargins(0, 8, 0, 0);

    auto* a2mBrowseRow = new QHBoxLayout;
    m_a2mFileLabel = new QLabel("No file selected.", a2mPage);
    m_a2mFileLabel->setWordWrap(true);
    auto* a2mBrowseBtn = new QPushButton("Browse ...", a2mPage);
    connect(a2mBrowseBtn, &QPushButton::clicked, this, [this]() {
        const QString p = QFileDialog::getOpenFileName(
            this, "Audio to Convert", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
        if (!p.isEmpty()) { m_a2mFilePath = p; m_a2mFileLabel->setText(p); }
    });
    a2mBrowseRow->addWidget(m_a2mFileLabel, 1);
    a2mBrowseRow->addWidget(a2mBrowseBtn);
    a2mLayout->addLayout(a2mBrowseRow);

    m_a2mBtn = new QPushButton("Convert to MIDI", a2mPage);
    m_a2mBtn->setObjectName("aiGenerateBtn");
    m_a2mBtn->setMinimumHeight(40);
    connect(m_a2mBtn, &QPushButton::clicked, this, &AIPanel::onAudioToMidiClicked);
    a2mLayout->addWidget(m_a2mBtn);

    m_a2mResultLabel = new QLabel("\u2014", a2mPage);
    m_a2mResultLabel->setWordWrap(true);
    a2mLayout->addWidget(m_a2mResultLabel);
    a2mLayout->addStretch();
    m_toolsStack->addWidget(a2mPage);

    layout->addWidget(m_toolsStack, 1);

    // Wire page buttons
    auto setToolsPage = [this,
                         isolatePageBtn, transcribePageBtn, alignPageBtn, dubPageBtn,
                         replacePageBtn, a2mPageBtn](int idx) {
        m_toolsStack->setCurrentIndex(idx);
        isolatePageBtn->setChecked(idx == 0);
        transcribePageBtn->setChecked(idx == 1);
        alignPageBtn->setChecked(idx == 2);
        dubPageBtn->setChecked(idx == 3);
        replacePageBtn->setChecked(idx == 4);
        a2mPageBtn->setChecked(idx == 5);
    };
    connect(isolatePageBtn,    &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(0); });
    connect(transcribePageBtn, &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(1); });
    connect(alignPageBtn,      &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(2); });
    connect(dubPageBtn,        &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(3); });
    connect(replacePageBtn,    &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(4); });
    connect(a2mPageBtn,        &QPushButton::clicked, this, [setToolsPage]() { setToolsPage(5); });
}

void AIPanel::buildCodeTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(0, 0, 0, 0);

#ifdef WAVY_WEBENGINE
    m_codeEditor = new CodeEditor(m_client, tab);
    layout->addWidget(m_codeEditor, 1);

    // Forward code track events to the AIPanel signal so src/main.cpp can
    // wire them to EngineAPI without knowing about CodeEditor.
    connect(m_codeEditor, &CodeEditor::tracksReady,
            this,         &AIPanel::onCodeTracksReady);
#else
    // ── QPlainTextEdit fallback when Qt WebEngine is not available ────────────

    // Toolbar
    auto* toolbar = new QWidget(tab);
    toolbar->setObjectName("codeEditorToolbar");
    auto* tl = new QHBoxLayout(toolbar);
    tl->setContentsMargins(12, 6, 12, 6);
    tl->setSpacing(8);

    m_codeModeCombo = new QComboBox(toolbar);
    m_codeModeCombo->addItem("Wavy DSL",  "dsl");
    m_codeModeCombo->addItem("Python",    "python");
    m_codeModeCombo->addItem("CSV Data",  "csv");
    m_codeModeCombo->addItem("JSON Data", "json_data");

    m_codeRunBtn = new QPushButton("▶  Run", toolbar);
    m_codeRunBtn->setObjectName("codeRunBtn");
    m_codeRunBtn->setFixedWidth(80);
    connect(m_codeRunBtn, &QPushButton::clicked, this, &AIPanel::onPlainCodeRunClicked);

    m_codeStatusLabel = new QLabel(toolbar);
    m_codeStatusLabel->setObjectName("codeStatusLabel");

    auto* studioNote = new QLabel("Studio tier", toolbar);
    studioNote->setObjectName("tierBadgeStudio");

    tl->addWidget(new QLabel("Mode:", toolbar));
    tl->addWidget(m_codeModeCombo);
    tl->addStretch();
    tl->addWidget(m_codeStatusLabel);
    tl->addWidget(m_codeRunBtn);
    tl->addWidget(studioNote);
    layout->addWidget(toolbar);

    // Editor + output splitter
    auto* splitter = new QSplitter(Qt::Vertical, tab);

    m_codePlainEdit = new QPlainTextEdit(splitter);
    m_codePlainEdit->setObjectName("codeEditorPlain");
    QFont monoFont("Courier New", 11);
    monoFont.setFixedPitch(true);
    m_codePlainEdit->setFont(monoFont);
    m_codePlainEdit->setPlainText(
        "# Wavy Labs DSL example\ntempo(128)\nkey(\"C minor\")\n\n"
        "track(\"drums\").pattern([1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,1,0], bpm=128)\n"
        "track(\"bass\").melody([\"C2\",\"G2\",\"Bb2\",\"C3\",\"Eb3\"], duration=\"eighth\")\n"
        "track(\"synth\").generate(\"lush ambient pad, C minor\", key=\"C minor\")\n");
    splitter->addWidget(m_codePlainEdit);

    auto* outPanel = new QWidget(splitter);
    auto* opl = new QVBoxLayout(outPanel);
    opl->setContentsMargins(8, 4, 8, 4);
    auto* outHeader = new QLabel("Output Tracks", outPanel);
    outHeader->setObjectName("sectionHeader");
    opl->addWidget(outHeader);
    m_codeOutputList = new QListWidget(outPanel);
    opl->addWidget(m_codeOutputList);
    splitter->addWidget(outPanel);
    splitter->setSizes({320, 160});

    layout->addWidget(splitter, 1);

    // Load example when mode changes (DSL_EXAMPLE/PYTHON_EXAMPLE are constexpr — no capture needed)
    connect(m_codeModeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, [this](int idx) {
                if (!m_codePlainEdit) return;
                if      (idx == 0) m_codePlainEdit->setPlainText(
                    "# Wavy Labs DSL example\ntempo(128)\nkey(\"C minor\")\n\n"
                    "track(\"drums\").pattern([1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,1,0], bpm=128)\n"
                    "track(\"bass\").melody([\"C2\",\"G2\",\"Bb2\",\"C3\",\"Eb3\"], duration=\"eighth\")\n"
                    "track(\"synth\").generate(\"lush ambient pad, C minor\", key=\"C minor\")\n");
                else if (idx == 1) m_codePlainEdit->setPlainText(
                    "# Python code-to-music example\n"
                    "track(\"drums\").pattern([1,0,0,1,0,0,1,0], bpm=140)\n"
                    "track(\"bass\").melody([C3, E3, G3, C4], duration=\"quarter\")\n"
                    "track(\"synth\").generate(\"ambient pad\", key=\"C minor\")\n");
                else               m_codePlainEdit->clear();
            });
#endif
}

// ---------------------------------------------------------------------------
// Slots — Code-to-Music
// ---------------------------------------------------------------------------

void AIPanel::onCodeTracksReady(const QVariantList& trackDefs,
                                const QString& /*midiPath*/,
                                const QStringList& audioPaths)
{
    if (audioPaths.isEmpty())
        return;

    // Build track names from trackDefs; fall back to index-based names.
    QStringList names;
    for (int i = 0; i < audioPaths.size(); ++i) {
        QString name;
        if (i < trackDefs.size())
            name = trackDefs.at(i).toMap().value("track").toString();
        if (name.isEmpty())
            name = QString("Code Track %1").arg(i + 1);
        names << name;
    }

    emit codeTracksReady(audioPaths, names);
}

#ifndef WAVY_WEBENGINE
void AIPanel::onPlainCodeRunClicked()
{
    if (!m_codePlainEdit || !m_codeRunBtn) return;

    m_codeRunBtn->setEnabled(false);
    m_codeRunBtn->setText("⏳ Running …");
    if (m_codeOutputList)   m_codeOutputList->clear();
    if (m_codeStatusLabel)  m_codeStatusLabel->setText("Running…");

    const QString code = m_codePlainEdit->toPlainText();
    const QString mode = m_codeModeCombo ? m_codeModeCombo->currentData().toString()
                                         : "dsl";
    QVariantMap params;
    params["code"] = code;
    params["mode"] = mode;

    m_client->codeToMusic(params, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            onPlainCodeConvertFinished(ok, result);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onPlainCodeConvertFinished(bool ok, const QVariantMap& result)
{
    if (m_codeRunBtn) {
        m_codeRunBtn->setEnabled(true);
        m_codeRunBtn->setText("▶  Run");
    }
    if (!ok) {
        if (m_codeStatusLabel)
            m_codeStatusLabel->setText("⚠ " + result.value("error").toString());
        return;
    }

    const QString      midiPath  = result.value("midi_path").toString();
    const QVariantList tracks    = result.value("track_defs").toList();
    const QVariantList audioVar  = result.value("audio_paths").toList();

    QStringList audioPaths;
    for (const QVariant& ap : audioVar)
        audioPaths << ap.toString();

    if (m_codeOutputList) {
        if (!midiPath.isEmpty())
            m_codeOutputList->addItem("\U0001f3b5 MIDI: " + midiPath);
        for (const QVariant& t : tracks) {
            const QVariantMap tm = t.toMap();
            m_codeOutputList->addItem(
                QString("  \u2713  Track: %1 (%2)")
                    .arg(tm.value("track").toString(),
                         tm.value("type").toString()));
        }
        for (const QString& ap : audioPaths) {
            m_codeOutputList->addItem(
                "  \U0001f3a7  Audio: " + QFileInfo(ap).fileName());
        }
    }
    if (m_codeStatusLabel)
        m_codeStatusLabel->setText(QString("\u2713  %1 tracks").arg(tracks.size()));

    onCodeTracksReady(tracks, midiPath, audioPaths);
}
#endif

// ---------------------------------------------------------------------------
// Prompt tab
// ---------------------------------------------------------------------------

void AIPanel::buildPromptTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(6);

    // ── Chat history display ─────────────────────────────────────────────────
    m_chatDisplay = new QTextEdit(tab);
    m_chatDisplay->setReadOnly(true);
    m_chatDisplay->setObjectName("aiChatDisplay");
    m_chatDisplay->setAcceptRichText(true);
    m_chatDisplay->document()->setDefaultStyleSheet(
        "body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }"
        ".user    { background:#2a3a52; border-radius:8px; padding:8px 12px; "
        "           margin:4px 32px 4px 4px; color:#e8f0fe; }"
        ".wavy    { background:#1e2d1e; border-radius:8px; padding:8px 12px; "
        "           margin:4px 4px 4px 32px; color:#c8f0c8; }"
        ".actions { background:#2d2a18; border-radius:6px; padding:4px 8px; "
        "           margin:2px 4px 4px 40px; color:#f0e0a0; font-size:11px; }"
        ".ts      { color:#666; font-size:10px; }"
    );
    m_chatDisplay->setPlaceholderText(
        "Chat with Wavy — your LMMS expert AI.\n\n"
        "Ask questions, get production tips, or say things like:\n"
        "  \"Set tempo to 140\"\n"
        "  \"How do I sidechain in LMMS?\"\n"
        "  \"Add a beat track called Drums\"\n"
        "  \"What instruments work well for lo-fi hip hop?\"");
    layout->addWidget(m_chatDisplay, 1);

    // ── Input row ────────────────────────────────────────────────────────────
    auto* inputRow = new QHBoxLayout;
    inputRow->setSpacing(6);

    m_chatInput = new QLineEdit(tab);
    m_chatInput->setObjectName("aiChatInput");
    m_chatInput->setPlaceholderText("Ask Wavy anything…  (Enter to send)");
    m_chatInput->setMinimumHeight(36);
    connect(m_chatInput, &QLineEdit::returnPressed, this, &AIPanel::onChatSend);
    inputRow->addWidget(m_chatInput, 1);

    m_chatSendBtn = new QPushButton("Send", tab);
    m_chatSendBtn->setObjectName("aiChatSend");
    m_chatSendBtn->setFixedSize(64, 36);
    connect(m_chatSendBtn, &QPushButton::clicked, this, &AIPanel::onChatSend);
    inputRow->addWidget(m_chatSendBtn);

    auto* clearBtn = new QPushButton("Clear", tab);
    clearBtn->setObjectName("aiChatClear");
    clearBtn->setFixedSize(52, 36);
    connect(clearBtn, &QPushButton::clicked, this, [this]() {
        m_chatDisplay->clear();
        m_chatHistory.clear();
    });
    inputRow->addWidget(clearBtn);

    layout->addLayout(inputRow);

    // Ctrl+K focuses the chat input
    auto* shortcut = new QShortcut(QKeySequence("Ctrl+K"), tab);
    connect(shortcut, &QShortcut::activated, m_chatInput, [this]() {
        m_chatInput->setFocus();
        m_chatInput->selectAll();
    });

    // Welcome message
    appendChatBubble("wavy",
        "Hey! I'm Wavy, your LMMS production assistant. "
        "I can control the DAW, answer music theory questions, "
        "give mixing tips, and help you build tracks. What are we making today?");
}

void AIPanel::appendChatBubble(const QString& role, const QString& text)
{
    QTextCursor cursor = m_chatDisplay->textCursor();
    cursor.movePosition(QTextCursor::End);
    m_chatDisplay->setTextCursor(cursor);

    const QString escaped = text.toHtmlEscaped().replace("\n", "<br>");
    QString html;
    if (role == "user") {
        html = QString("<div class='user'><b>You</b><br>%1</div>").arg(escaped);
    } else {
        html = QString("<div class='wavy'><b>✦ Wavy</b><br>%1</div>").arg(escaped);
    }
    m_chatDisplay->append(html);
    // Scroll to bottom
    auto* sb = m_chatDisplay->verticalScrollBar();
    sb->setValue(sb->maximum());
}

void AIPanel::onChatSend()
{
    const QString text = m_chatInput->text().trimmed();
    if (text.isEmpty()) return;

    m_chatInput->clear();
    m_chatInput->setEnabled(false);
    m_chatSendBtn->setEnabled(false);

    appendChatBubble("user", text);

    // Add user turn to history
    QVariantMap userTurn;
    userTurn["role"]    = "user";
    userTurn["content"] = text;
    m_chatHistory.append(userTurn);

    // Send to backend — pass full history minus the last user turn
    // (backend appends the current prompt itself)
    QVariantList historyToSend;
    for (int i = 0; i < m_chatHistory.size() - 1; ++i)
        historyToSend.append(m_chatHistory[i]);

    m_client->promptCommand(text, QVariantMap{}, historyToSend,
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onChatFinished(ok, result);
            }, Qt::QueuedConnection);
        });
}

void AIPanel::onChatFinished(bool ok, const QVariantMap& result)
{
    m_chatInput->setEnabled(true);
    m_chatSendBtn->setEnabled(true);
    m_chatInput->setFocus();

    if (!ok) {
        const QString err = result.value("error").toString();
        appendChatBubble("wavy", "⚠ " + (err.isEmpty() ? "Backend error." : err));
        return;
    }

    const QString explanation = result.value("explanation").toString();
    const QVariantList actions = result.value("actions").toList();

    if (!explanation.isEmpty())
        appendChatBubble("wavy", explanation);

    // Show action summary as a small note under the reply
    if (!actions.isEmpty()) {
        QStringList actionNames;
        for (const QVariant& a : actions) {
            const QString t = a.toMap().value("type").toString();
            if (!t.isEmpty()) actionNames << t;
        }
        QTextCursor cursor = m_chatDisplay->textCursor();
        cursor.movePosition(QTextCursor::End);
        const QString actHtml = QString(
            "<div class='actions'>⚡ Actions: %1</div>")
            .arg(actionNames.join(", ").toHtmlEscaped());
        m_chatDisplay->append(actHtml);
        auto* sb = m_chatDisplay->verticalScrollBar();
        sb->setValue(sb->maximum());
    }

    // Add assistant reply to history
    QVariantMap assistantTurn;
    assistantTurn["role"]    = "assistant";
    assistantTurn["content"] = explanation;
    m_chatHistory.append(assistantTurn);

    // Dispatch DAW actions
    if (!actions.isEmpty())
        emit actionsReady(actions);
}

// ---------------------------------------------------------------------------
// Console tab
// ---------------------------------------------------------------------------

void AIPanel::buildConsoleTab(QWidget* tab)
{
    auto* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    auto* toolbar = new QHBoxLayout;
    auto* clearBtn = new QPushButton("Clear", tab);
    clearBtn->setFixedWidth(60);
    toolbar->addStretch();
    toolbar->addWidget(clearBtn);
    layout->addLayout(toolbar);

    m_consoleEdit = new QPlainTextEdit(tab);
    m_consoleEdit->setReadOnly(true);
    m_consoleEdit->setMaximumBlockCount(1000);
    m_consoleEdit->setFont(QFont("Consolas", 9));
    m_consoleEdit->setObjectName("aiConsole");
    layout->addWidget(m_consoleEdit, 1);

    connect(clearBtn, &QPushButton::clicked,
            m_consoleEdit, &QPlainTextEdit::clear);
}

void AIPanel::appendLog(const QString& msg)
{
    if (!m_consoleEdit) return;
    QMetaObject::invokeMethod(m_consoleEdit, [this, msg]() {
        m_consoleEdit->appendPlainText(
            QDateTime::currentDateTime().toString("[hh:mm:ss] ") + msg);
    }, Qt::QueuedConnection);
}

// ---------------------------------------------------------------------------
// Slots — music generation
// ---------------------------------------------------------------------------

void AIPanel::onGenerateClicked()
{
    auto* lm = LicenseManager::instance();
    const QString model = m_modelCombo->currentData().toString();

    // ElevenLabs music model has its own per-feature limit
    if (model == "elevenlabs_music") {
        if (!lm->canElevenLabsMusic()) {
            const int r = lm->elFeatureRemaining("music");
            showError(r <= 0 ? "ElevenLabs Music daily limit reached."
                             : "Music generation limit reached.");
            return;
        }
    } else if (!lm->canGenerate()) {
        showError("Daily generation limit reached. Configure your API keys in Edit → Settings to continue.");
        return;
    }

    const QString prompt = m_promptEdit->toPlainText().trimmed();
    if (prompt.isEmpty()) {
        showError("Please enter a music description.");
        return;
    }

    setGenerating(true);

    QVariantMap params = collectMusicParams();
    m_client->generateMusic(params,
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onGenerationFinished(ok, result);
            }, Qt::QueuedConnection);
        });
}

QVariantMap AIPanel::collectMusicParams() const
{
    QVariantMap p;
    p["prompt"]   = m_promptEdit->toPlainText().trimmed();
    p["model"]    = m_modelCombo->currentData().toString();
    p["tier"]     = LicenseManager::instance()->isPro() ? "pro" : "free";

    const int durationSec = m_durationCombo->currentData().toInt();
    if (durationSec > 0)
        p["duration"] = static_cast<double>(durationSec);

    const int tempoBpm = m_tempoCombo->currentData().toInt();
    if (tempoBpm > 0)
        p["tempo"] = tempoBpm;

    const QString genre = m_genreCombo->currentText();
    if (genre != "(auto)")
        p["genre"] = genre;

    const QString key = m_keyCombo->currentText();
    if (key != "(auto)")
        p["key"] = key;

    const QString lyrics = m_lyricsCombo->currentText();
    if (lyrics != "(auto)") {
        if (lyrics == "Custom" && m_customLyricsEdit) {
            p["lyrics"] = "custom";
            const QString customText = m_customLyricsEdit->toPlainText().trimmed();
            if (!customText.isEmpty())
                p["custom_lyrics"] = customText;
        } else {
            p["lyrics"] = lyrics;
        }
    }

    if (m_sectionStructureChk && m_sectionStructureChk->isChecked())
        p["section_structure"] = true;

    // Inspo paths
    if (m_inspoList && m_inspoList->count() > 0) {
        QVariantList inspo;
        for (int i = 0; i < m_inspoList->count(); ++i)
            inspo.append(m_inspoList->item(i)->text());
        p["inspo_paths"] = inspo;
    }

    // Audio influence (0.0 – 1.0)
    if (m_influenceSlider)
        p["influence"] = m_influenceSlider->value() / 100.0;

    return p;
}

void AIPanel::onGenerationFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        showError(result.value("error").toString());
        return;
    }

    const QString path     = result.value("audio_path").toString();
    const double  duration = result.value("duration").toDouble();
    const QString prompt   = m_promptEdit->toPlainText().trimmed();

    m_lastAudioPath = path;
    const QVariantList sections = result.value("sections").toList();
    m_history->addEntry(prompt, path, duration, sections);

    auto* lm = LicenseManager::instance();
    const QString modelUsed = result.value("model_used").toString();
    if (modelUsed.startsWith("elevenlabs"))
        lm->recordElevenLabsCall("music");
    else
        lm->recordGeneration(modelUsed);
    updateDailyCounter(lm->dailyGenerationsRemaining());

    // Auto-split: each stem becomes its own track instead of one combined track
    int numStems = 0;
    if (m_stemCountCombo && m_stemCountCombo->currentData().toInt() > 0)
        numStems = m_stemCountCombo->currentData().toInt();
    else if (m_advancedStemGenerationCombo && m_advancedStemGenerationCombo->currentData().toInt() > 0)
        numStems = m_advancedStemGenerationCombo->currentData().toInt();

    if (numStems > 0) {
        m_statusLabel->setText(QString("Splitting into %1 stems…").arg(numStems));
        setGenerating(true);
        QVariantMap p;
        p["audio_path"] = path;
        p["stems"]      = numStems;
        m_client->splitStems(p, [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onStemFinished(ok, r);
            }, Qt::QueuedConnection);
        });
        return;
    }

    emit audioReady("AI Generated", path, duration);
}

// ---------------------------------------------------------------------------
// Slot — multi-attempt generation ("Best of 3")
// ---------------------------------------------------------------------------

void AIPanel::onGenerateMultiClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->isPro() && lm->dailyGenerationsRemaining() < 3) {
        showError(QString(
            "Best of 3 requires 3 daily generations (%1 remaining). "
            "Configure your API keys in Edit → Settings.")
            .arg(lm->dailyGenerationsRemaining()));
        return;
    }

    const QString prompt = m_promptEdit->toPlainText().trimmed();
    if (prompt.isEmpty()) {
        showError("Please enter a music description.");
        return;
    }

    setGenerating(true);
    m_multiResults.clear();
    m_multiPending.storeRelaxed(3);

    QVariantMap baseParams = collectMusicParams();

    for (int i = 0; i < 3; ++i) {
        QVariantMap p = baseParams;
        // Vary the seed so each attempt produces a distinct result.
        p["seed"] = static_cast<int>(QRandomGenerator::global()->bounded(100000u));

        m_client->generateMusic(p,
            [this](bool ok, const QVariantMap& result) {
                // Queue everything on the main thread — no mutex needed.
                QMetaObject::invokeMethod(this, [this, ok, result]() {
                    if (ok)
                        m_multiResults.append(result);

                    if (m_multiPending.fetchAndSubRelaxed(1) == 1) {
                        // All 3 callbacks have now completed.
                        setGenerating(false);
                        if (m_multiResults.isEmpty()) {
                            showError("All 3 generation attempts failed. "
                                      "Check the AI backend connection.");
                            return;
                        }
                        showMultiPickDialog();
                    }
                }, Qt::QueuedConnection);
            });
    }
}

// ---------------------------------------------------------------------------
// showMultiPickDialog — comparison dialog; user picks one result to insert
// ---------------------------------------------------------------------------

void AIPanel::showMultiPickDialog()
{
    auto* dlg = new QDialog(this);
    dlg->setWindowTitle("Best of 3 — Pick a Generation");
    dlg->setMinimumWidth(680);
    dlg->setAttribute(Qt::WA_DeleteOnClose);

    auto* root = new QVBoxLayout(dlg);

    auto* intro = new QLabel(
        QString("<b>%1 variation(s) generated.</b>  Preview each one and "
                "choose the track to insert into your project.")
            .arg(m_multiResults.size()), dlg);
    intro->setWordWrap(true);
    root->addWidget(intro);

    // ── Result cards (one per successful generation) ───────────────────────
    auto* cardsRow = new QHBoxLayout;

    for (int i = 0; i < m_multiResults.size(); ++i) {
        const QVariantMap res  = m_multiResults[i];
        const QString     path = res.value("audio_path").toString();
        const double      dur  = res.value("duration", 0.0).toDouble();

        auto* card = new QGroupBox(QString("Variation %1").arg(i + 1), dlg);
        auto* cl   = new QVBoxLayout(card);

        auto* durLabel = new QLabel(
            QString("Duration: %1 s").arg(dur, 0, 'f', 1), card);
        cl->addWidget(durLabel);

        auto* pathLabel = new QLabel(path, card);
        pathLabel->setWordWrap(true);
        pathLabel->setObjectName("aiPathLabel");
        cl->addWidget(pathLabel);

        cl->addStretch();

        auto* previewBtn = new QPushButton("▶  Preview", card);
        previewBtn->setToolTip("Open in default audio player");
        connect(previewBtn, &QPushButton::clicked, card, [path]() {
            QDesktopServices::openUrl(QUrl::fromLocalFile(path));
        });
        cl->addWidget(previewBtn);

        auto* insertBtn = new QPushButton("✓  Insert This Track", card);
        insertBtn->setObjectName("aiGenerateBtn");
        insertBtn->setMinimumHeight(36);
        connect(insertBtn, &QPushButton::clicked, dlg,
            [this, dlg, res, path, dur]() {
                m_lastAudioPath = path;
                m_history->addEntry(
                    m_promptEdit->toPlainText().trimmed(), path, dur,
                    res.value("sections").toList());

                // Record 3 generations consumed (one per backend call).
                auto* lm = LicenseManager::instance();
                for (int n = 0; n < 3; ++n)
                    lm->recordGeneration(res.value("model_used").toString());
                updateDailyCounter(lm->dailyGenerationsRemaining());

                emit audioReady("AI Generated (Best of 3)", path, dur);
                dlg->accept();
            });
        cl->addWidget(insertBtn);

        cardsRow->addWidget(card);
    }

    root->addLayout(cardsRow);

    // ── Footer ─────────────────────────────────────────────────────────────
    auto* footerRow = new QHBoxLayout;
    footerRow->addStretch();

    auto* discardBtn = new QPushButton("Discard All", dlg);
    discardBtn->setToolTip("Close without inserting any track");
    connect(discardBtn, &QPushButton::clicked, dlg, [this, dlg]() {
        // Still count the 3 spent generations on discard (work was done).
        auto* lm = LicenseManager::instance();
        for (int n = 0; n < 3; ++n)
            lm->recordGeneration();
        updateDailyCounter(lm->dailyGenerationsRemaining());
        dlg->reject();
    });
    footerRow->addWidget(discardBtn);
    root->addLayout(footerRow);

    dlg->open();
}

// ---------------------------------------------------------------------------
// Slots — stem split / mix
// ---------------------------------------------------------------------------

void AIPanel::onStemSplitClicked()
{
    const QString path = QFileDialog::getOpenFileName(
        this, "Select Audio File", {},
        "Audio Files (*.wav *.mp3 *.flac *.ogg *.aiff)");
    if (path.isEmpty()) return;

    setGenerating(true);
    QVariantMap p;
    p["audio_path"] = path;
    p["stems"]      = m_isFreeUser ? 2 : 4;

    m_client->splitStems(p,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onStemFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onStemFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) {
        m_statusLabel->setText("Stem split failed.");
        showError(result.value("error").toString());
        return;
    }

    const QVariantMap stems = result.value("stems").toMap();
    QStringList paths, names;
    for (auto it = stems.begin(); it != stems.end(); ++it) {
        names << it.key();
        paths << it.value().toString();
    }
    emit stemsReady(paths, names);
    m_mixResultLabel->setText(
        QString("Split into %1 stems: %2")
            .arg(names.size()).arg(names.join(", ")));
}

void AIPanel::onAnalyzeClicked()
{
    if (!LicenseManager::instance()->canMaster()) {
        showError("AI Mix Analysis requires an ElevenLabs API key. Configure keys in Edit → Settings.");
        return;
    }
    const QString path = QFileDialog::getOpenFileName(
        this, "Select Audio to Analyze", {},
        "Audio Files (*.wav *.mp3 *.flac)");
    if (path.isEmpty()) return;

    setGenerating(true);
    m_mixResultLabel->setText("Analyzing …");

    QVariantMap p;
    p["track_paths"] = QVariantList{path};   // mixer.analyze() takes a list

    m_client->analyzeTrack(p,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onAnalyzeFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onAnalyzeFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) {
        m_mixResultLabel->setText("Analysis failed.");
        showError(result.value("error").toString());
        return;
    }
    // Build a human-readable summary of track gains / headroom.
    const QVariantList tracks = result.value("suggestions").toList();
    QStringList lines;
    for (const QVariant& t : tracks) {
        const QVariantMap tm = t.toMap();
        lines << QString("%1: RMS %2 dB, gain suggestion %3 dB")
                     .arg(tm.value("track", "?").toString())
                     .arg(tm.value("rms_db", 0.0).toDouble(), 0, 'f', 1)
                     .arg(tm.value("gain_db", 0.0).toDouble(), 0, 'f', 1);
    }
    m_mixResultLabel->setText(lines.isEmpty()
        ? result.value("summary", "Analysis complete.").toString()
        : lines.join("\n"));
}

void AIPanel::onMasterClicked()
{
    if (!LicenseManager::instance()->canMaster()) {
        showError("AI Mastering requires an ElevenLabs API key. Configure keys in Edit → Settings.");
        return;
    }
    const QString path = QFileDialog::getOpenFileName(
        this, "Select Audio to Master", {},
        "Audio Files (*.wav *.mp3 *.flac)");
    if (path.isEmpty()) return;

    setGenerating(true);
    QVariantMap p;
    p["audio_path"]   = path;
    p["target_lufs"]  = -14.0;

    m_client->masterAudio(p,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onMasterFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onMasterFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) { showError(result.value("error").toString()); return; }
    const QString out = result.value("output_path").toString();
    m_mixResultLabel->setText("Mastered audio saved: " + out);
    emit audioReady("Mastered", out, 0.0);
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs TTS
// ---------------------------------------------------------------------------

void AIPanel::onTTSClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsTTS()) {
        const int r = lm->elFeatureRemaining("tts");
        showError(r <= 0 ? "TTS daily limit reached."
                         : "ElevenLabs TTS requires Pro ($9.99/mo).");
        return;
    }
    const QString text = m_ttsTextEdit->toPlainText().trimmed();
    if (text.isEmpty()) { showError("Please enter text to convert to speech."); return; }

    setGenerating(true);
    QVariantMap params;
    params["text"]             = text;
    params["voice_id"]         = m_voiceCombo->currentData().toString();
    params["model"]            = m_ttsModelCombo->currentData().toString();
    params["stability"]        = m_stabilitySlider->value() / 100.0;
    params["similarity_boost"] = m_similaritySlider->value() / 100.0;

    m_client->elevenLabsTTS(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onTTSFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onTTSFinished(bool ok, const QVariantMap& result)
{
    finishElevenLabsAudio(ok, result, "ElevenLabs TTS", "tts");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs Speech-to-Speech
// ---------------------------------------------------------------------------

void AIPanel::onSTSClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsSTS()) {
        const int r = lm->elFeatureRemaining("sts");
        showError(r <= 0 ? "Speech-to-Speech daily limit reached."
                         : "Speech-to-Speech requires Pro ($9.99/mo).");
        return;
    }
    if (m_stsFilePath.isEmpty()) { showError("Please select a source audio file."); return; }

    setGenerating(true);
    QVariantMap params;
    params["audio_path"] = m_stsFilePath;
    params["voice_id"]   = m_stsVoiceCombo->currentData().toString();

    m_client->elevenLabsSTS(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onSTSFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onSTSFinished(bool ok, const QVariantMap& result)
{
    finishElevenLabsAudio(ok, result, "Voice Converted", "sts");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs Voice Clone
// ---------------------------------------------------------------------------

void AIPanel::onVoiceCloneClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsVoiceClone()) {
        const int r = lm->elFeatureRemaining("voice_clone");
        showError(r <= 0 ? "Voice Clone daily limit reached (5/day Studio)."
                         : "Voice Cloning requires Studio ($24.99/mo).");
        return;
    }
    const QString name = m_cloneNameEdit->text().trimmed();
    if (name.isEmpty()) { showError("Please enter a name for the cloned voice."); return; }
    if (m_cloneFileList->count() == 0) { showError("Please add at least one audio sample."); return; }

    setGenerating(true);
    QVariantMap params;
    params["name"] = name;
    QStringList paths;
    for (int i = 0; i < m_cloneFileList->count(); ++i)
        paths << m_cloneFileList->item(i)->text();
    params["audio_paths"] = paths;

    m_client->elevenLabsVoiceClone(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onVoiceCloneFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onVoiceCloneFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) { showError(result.value("error").toString()); return; }
    const QString voiceId = result.value("voice_id").toString();
    m_cloneResultLabel->setText(QString("Voice cloned! ID: %1").arg(voiceId));
    LicenseManager::instance()->recordElevenLabsCall("voice_clone");
    // Refresh voice combos to include the new voice
    populateVoiceCombo();
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs SFX
// ---------------------------------------------------------------------------

void AIPanel::onSFXClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsSFX()) {
        const int r = lm->elFeatureRemaining("sfx");
        showError(r <= 0 ? "SFX daily limit reached."
                         : "SFX Generation requires Pro ($9.99/mo).");
        return;
    }
    const QString text = m_sfxPromptEdit->toPlainText().trimmed();
    if (text.isEmpty()) { showError("Please describe the sound effect."); return; }

    setGenerating(true);
    QVariantMap params;
    params["text"]             = text;
    params["duration_seconds"] = static_cast<double>(m_sfxDurationSlider->value());

    m_client->elevenLabsSFX(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onSFXFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onSFXFinished(bool ok, const QVariantMap& result)
{
    finishElevenLabsAudio(ok, result, "Sound Effect", "sfx");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs Voice Isolator
// ---------------------------------------------------------------------------

void AIPanel::onVoiceIsolateClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsIsolate()) {
        const int r = lm->elFeatureRemaining("voice_isolate");
        showError(r <= 0 ? "Voice Isolation daily limit reached."
                         : "Voice Isolation requires Pro ($9.99/mo).");
        return;
    }
    if (m_isolateFilePath.isEmpty()) { showError("Please select an audio file."); return; }

    setGenerating(true);
    QVariantMap params;
    params["audio_path"] = m_isolateFilePath;

    m_client->elevenLabsVoiceIsolate(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onVoiceIsolateFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onVoiceIsolateFinished(bool ok, const QVariantMap& result)
{
    finishElevenLabsAudio(ok, result, "Isolated Vocals", "voice_isolate");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs Transcribe
// ---------------------------------------------------------------------------

void AIPanel::onTranscribeClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsTranscribe()) {
        const int r = lm->elFeatureRemaining("transcribe");
        showError(r <= 0 ? "Transcription daily limit reached."
                         : "Transcription requires Pro ($9.99/mo).");
        return;
    }
    if (m_transcribeFilePath.isEmpty()) { showError("Please select an audio file."); return; }

    setGenerating(true);
    QVariantMap params;
    params["audio_path"]    = m_transcribeFilePath;
    params["language_code"] = m_transcribeLangCombo->currentText();

    m_client->elevenLabsTranscribe(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onTranscribeFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onTranscribeFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) { showError(result.value("error").toString()); return; }
    m_transcribeResult->setPlainText(result.value("text").toString());
    LicenseManager::instance()->recordElevenLabsCall("transcribe");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs Forced Alignment
// ---------------------------------------------------------------------------

void AIPanel::onForcedAlignClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsAlign()) {
        const int r = lm->elFeatureRemaining("forced_align");
        showError(r <= 0 ? "Forced Alignment daily limit reached (10/day Studio)."
                         : "Forced Alignment requires Studio ($24.99/mo).");
        return;
    }
    if (m_alignFilePath.isEmpty()) { showError("Please select an audio file."); return; }
    const QString text = m_alignTextEdit->toPlainText().trimmed();
    if (text.isEmpty()) { showError("Please enter text to align."); return; }

    setGenerating(true);
    QVariantMap params;
    params["audio_path"]    = m_alignFilePath;
    params["text"]          = text;
    params["language_code"] = "en";

    m_client->elevenLabsForcedAlign(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onForcedAlignFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onForcedAlignFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok) { showError(result.value("error").toString()); return; }
    const QVariantList alignment = result.value("alignment").toList();
    QStringList lines;
    for (const auto& w : alignment) {
        const QVariantMap wm = w.toMap();
        lines << QString("%1: %2s - %3s")
                     .arg(wm.value("word").toString())
                     .arg(wm.value("start").toDouble(), 0, 'f', 2)
                     .arg(wm.value("end").toDouble(), 0, 'f', 2);
    }
    m_alignResultLabel->setText(lines.join("\n"));
    LicenseManager::instance()->recordElevenLabsCall("forced_align");
}

// ---------------------------------------------------------------------------
// Slots — ElevenLabs AI Dubbing
// ---------------------------------------------------------------------------

void AIPanel::onDubClicked()
{
    auto* lm = LicenseManager::instance();
    if (!lm->canElevenLabsDub()) {
        const int r = lm->elFeatureRemaining("dub");
        showError(r <= 0 ? "AI Dubbing daily limit reached (5/day Studio)."
                         : "AI Dubbing requires Studio ($24.99/mo).");
        return;
    }
    if (m_dubFilePath.isEmpty()) { showError("Please select an audio file."); return; }

    setGenerating(true);
    QVariantMap params;
    params["audio_path"]      = m_dubFilePath;
    params["source_language"] = m_dubSourceLangCombo->currentText();
    params["target_language"] = m_dubTargetLangCombo->currentText();

    m_client->elevenLabsDub(params,
        [this](bool ok, const QVariantMap& r) {
            QMetaObject::invokeMethod(this, [this, ok, r]() {
                onDubFinished(ok, r); }, Qt::QueuedConnection);
        });
}

void AIPanel::onDubFinished(bool ok, const QVariantMap& result)
{
    finishElevenLabsAudio(ok, result, "Dubbed Audio", "dub");
}

// ---------------------------------------------------------------------------
// Voice combo population from ElevenLabs
// ---------------------------------------------------------------------------

void AIPanel::populateVoiceCombo()
{
    m_client->elevenLabsListVoices(
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                if (!ok) return;
                const QVariantList voices = result.value("voices").toList();
                if (voices.isEmpty()) return;

                // Populate all voice combos
                for (auto* combo : {m_voiceCombo, m_stsVoiceCombo}) {
                    if (!combo) continue;
                    const QString current = combo->currentData().toString();
                    combo->clear();
                    for (const auto& v : voices) {
                        const QVariantMap vm = v.toMap();
                        combo->addItem(
                            vm.value("name").toString(),
                            vm.value("voice_id").toString());
                    }
                    int idx = combo->findData(current);
                    combo->setCurrentIndex(idx >= 0 ? idx : 0);
                }
            }, Qt::QueuedConnection);
        });
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Shared helper — ElevenLabs slots that return a single audio_path
// ---------------------------------------------------------------------------

void AIPanel::finishElevenLabsAudio(bool ok, const QVariantMap& result,
                                    const QString& trackName, const QString& elFeature)
{
    setGenerating(false);
    if (!ok) { showError(result.value("error").toString()); return; }
    LicenseManager::instance()->recordElevenLabsCall(elFeature);
    emit audioReady(trackName, result.value("audio_path").toString(),
                    result.value("duration").toDouble());
}

void AIPanel::setGenerating(bool busy)
{
    m_progressBar->setVisible(busy);
    m_generateBtn->setEnabled(!busy);
    if (m_generateMultiBtn)   m_generateMultiBtn->setEnabled(!busy);
    if (m_ttsBtn)           m_ttsBtn->setEnabled(!busy);
    if (m_stsBtn)           m_stsBtn->setEnabled(!busy);
    if (m_cloneBtn)         m_cloneBtn->setEnabled(!busy);
    if (m_sfxBtn)           m_sfxBtn->setEnabled(!busy);
    if (m_generateStemBtn)  m_generateStemBtn->setEnabled(!busy);
    if (m_extendBtn)        m_extendBtn->setEnabled(!busy);
    if (m_replaceBtn)       m_replaceBtn->setEnabled(!busy);
    if (m_a2mBtn)           m_a2mBtn->setEnabled(!busy);
    if (m_autoMixBtn)       m_autoMixBtn->setEnabled(!busy);
    if (m_analyzeBtn)       m_analyzeBtn->setEnabled(!busy);
    if (m_masterBtn)        m_masterBtn->setEnabled(!busy);
    m_generateBtn->setText(busy ? "Generating …" : "\u266B  Create");
}

void AIPanel::showError(const QString& msg)
{
    QMessageBox::warning(this, "Wavy Labs AI", msg);
}

void AIPanel::onModelStatusChanged(bool connected)
{
    m_statusLabel->setText(connected ? "● Ready" : "● Offline");
    m_statusLabel->setObjectName(connected ? "aiStatusOk" : "aiStatusOffline");
    m_generateBtn->setEnabled(connected);
}

void AIPanel::onCheckStatusClicked()
{
    m_statusLabel->setText("● Checking…");
    m_statusLabel->setObjectName("aiStatusOffline");
    m_statusLabel->style()->unpolish(m_statusLabel);
    m_statusLabel->style()->polish(m_statusLabel);

    m_client->checkStatus([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            onModelStatusChanged(ok);
            if (ok) {
                appendLog(QString("Status: Ready — backend OK"));
            } else {
                const QString err = result.value("error").toString();
                appendLog(QString("Status: Offline — %1").arg(err.isEmpty() ? "is wavy-ai/server.py running?" : err));
            }
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onTierChanged(Tier newTier)
{
    m_isFreeUser = (newTier == Tier::Free);
    updateDailyCounter(LicenseManager::instance()->dailyGenerationsRemaining());
}

void AIPanel::populateModelCombo()
{
    const QString current = m_modelCombo->currentData().toString();
    m_modelCombo->clear();

    for (const auto& m : m_modelManager->models()) {
        // ElevenLabs music — always show (primary default)
        if (m.name == "elevenlabs_music") {
            QString label = m.displayName;
            if (!m.apiKeyConfigured) label += " (no key)";
            m_modelCombo->addItem(label, m.name);
        }

    }

    // If combo is empty, add ElevenLabs as default
    if (m_modelCombo->count() == 0)
        m_modelCombo->addItem("ElevenLabs Music (Cloud)", "elevenlabs_music");

    // Restore previous selection
    int idx = m_modelCombo->findData(current);
    m_modelCombo->setCurrentIndex(idx >= 0 ? idx : 0);
}

void AIPanel::updateDailyCounter(int remaining)
{
    auto* lm = LicenseManager::instance();
    const int elRemaining = lm->elevenLabsDailyRemaining();
    if (lm->isStudio()) {
        m_dailyCounterLabel->setText(
            QString("Studio | %1/100 EL remaining").arg(elRemaining));
    } else if (lm->isPro()) {
        m_dailyCounterLabel->setText(
            QString("Pro | %1/30 EL remaining").arg(elRemaining));
    } else {
        m_dailyCounterLabel->setText(
            QString("Free: %1/5 gen | %2/3 EL").arg(remaining).arg(elRemaining));
    }
}

// ---------------------------------------------------------------------------
// Slots — Stem Generation
// ---------------------------------------------------------------------------

void AIPanel::onGenerateStemClicked()
{
    const QString prompt = m_promptEdit->toPlainText().trimmed();
    if (prompt.isEmpty()) { showError("Please enter a description for the stem."); return; }

    setGenerating(true);
    QVariantMap p;
    p["prompt"]         = prompt;
    p["stem_type"]      = m_stemTypeCombo ? m_stemTypeCombo->currentText() : QString("full");
    p["reference_path"] = m_stemRefPath;
    const int durSec = m_durationCombo ? m_durationCombo->currentData().toInt() : 0;
    p["duration"]       = durSec > 0 ? static_cast<double>(durSec) : 15.0;
    p["influence"]      = m_influenceSlider ? m_influenceSlider->value() / 100.0 : 0.5;
    const int tempoBpm = m_tempoCombo ? m_tempoCombo->currentData().toInt() : 0;
    p["tempo"]          = tempoBpm > 0 ? tempoBpm : 120;
    p["tier"]           = LicenseManager::instance()->isPro() ? "pro" : "free";

    m_client->generateStem(p, [this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onGenerateStemFinished(ok, res);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onGenerateStemFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        showError(result.value("error", "Stem generation failed.").toString());
        return;
    }
    const QString path = result.value("audio_path").toString();
    const QString name = (m_stemTypeCombo ? m_stemTypeCombo->currentText() : QString("stem")) + " stem";
    m_lastAudioPath = path;
    emit audioReady(name, path, result.value("duration").toDouble());
}

// ---------------------------------------------------------------------------
// Slots — Replace Section
// ---------------------------------------------------------------------------

void AIPanel::onReplaceSectionClicked()
{
    if (m_replaceFilePath.isEmpty()) { showError("Please select an audio file."); return; }
    const QString prompt = m_replacePromptEdit ? m_replacePromptEdit->toPlainText().trimmed() : QString();
    if (prompt.isEmpty()) { showError("Please describe the replacement sound."); return; }

    setGenerating(true);
    QVariantMap p;
    p["audio_path"] = m_replaceFilePath;
    p["start_sec"]  = m_replaceStartSpin ? m_replaceStartSpin->value() : 0.0;
    p["end_sec"]    = m_replaceEndSpin   ? m_replaceEndSpin->value()   : 5.0;
    p["prompt"]     = prompt;
    p["tempo"]      = m_tempoCombo ? (m_tempoCombo->currentData().toInt() > 0 ? m_tempoCombo->currentData().toInt() : 120) : 120;
    p["tier"]       = LicenseManager::instance()->isPro() ? "pro" : "free";

    m_client->replaceSection(p, [this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onReplaceSectionFinished(ok, res);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onReplaceSectionFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        showError(result.value("error", "Replace section failed.").toString());
        return;
    }
    const QString path = result.value("audio_path").toString();
    m_lastAudioPath = path;
    emit audioReady("Replaced Section", path, 0.0);
}

// ---------------------------------------------------------------------------
// Slots — Audio to MIDI
// ---------------------------------------------------------------------------

void AIPanel::onAudioToMidiClicked()
{
    if (m_a2mFilePath.isEmpty()) { showError("Please select an audio file."); return; }

    setGenerating(true);
    if (m_a2mResultLabel) m_a2mResultLabel->setText("Converting…");

    QVariantMap p;
    p["audio_path"] = m_a2mFilePath;

    m_client->audioToMidi(p, [this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onAudioToMidiFinished(ok, res);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onAudioToMidiFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        if (m_a2mResultLabel) m_a2mResultLabel->setText("Failed.");
        showError(result.value("error", "Audio to MIDI failed.").toString());
        return;
    }
    const QString path      = result.value("midi_path").toString();
    const int     noteCount = result.value("note_count").toInt();
    if (m_a2mResultLabel)
        m_a2mResultLabel->setText(QString("%1 notes \u2192 %2")
            .arg(noteCount).arg(QFileInfo(path).fileName()));
    emit midiFileReady(path);
}

// ---------------------------------------------------------------------------
// Slots — Extend Music
// ---------------------------------------------------------------------------

void AIPanel::onExtendMusicClicked()
{
    if (m_lastAudioPath.isEmpty()) {
        showError("Generate a track first, then use Extend to append more audio.");
        return;
    }
    setGenerating(true);
    QVariantMap p;
    p["audio_path"]      = m_lastAudioPath;
    p["extend_seconds"]  = m_extendSecSpin ? static_cast<double>(m_extendSecSpin->value()) : 15.0;
    p["prompt"]          = m_promptEdit ? m_promptEdit->toPlainText().trimmed() : QString("continuation, same style");
    p["tempo"]           = m_tempoCombo ? (m_tempoCombo->currentData().toInt() > 0 ? m_tempoCombo->currentData().toInt() : 120) : 120;
    p["tier"]            = LicenseManager::instance()->isPro() ? "pro" : "free";

    m_client->extendMusic(p, [this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onExtendMusicFinished(ok, res);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onExtendMusicFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        showError(result.value("error", "Extend failed.").toString());
        return;
    }
    const QString path = result.value("audio_path").toString();
    m_lastAudioPath = path;
    emit audioReady("Extended Track", path, result.value("duration").toDouble());
}

// ---------------------------------------------------------------------------
// Slots — Voice Personas
// ---------------------------------------------------------------------------

void AIPanel::onSavePersonaClicked()
{
    const QString name = m_personaNameEdit ? m_personaNameEdit->text().trimmed() : QString();
    if (name.isEmpty()) { showError("Enter a name for the persona."); return; }

    QVariantMap p;
    p["name"]        = name;
    p["voice_id"]    = m_voiceCombo     ? m_voiceCombo->currentData().toString()       : QString();
    p["stability"]   = m_stabilitySlider  ? m_stabilitySlider->value() / 100.0         : 0.5;
    p["similarity"]  = m_similaritySlider ? m_similaritySlider->value() / 100.0        : 0.75;

    m_client->savePersona(p, [this, name](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res, name]() {
            if (!ok || res.contains("error")) {
                showError(res.value("error", "Save persona failed.").toString());
                return;
            }
            // Reload personas
            m_client->loadPersonas([this](bool ok2, const QVariantMap& r2) {
                QMetaObject::invokeMethod(this, [this, ok2, r2]() {
                    onLoadPersonasFinished(ok2, r2);
                }, Qt::QueuedConnection);
            });
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onLoadPersonasFinished(bool ok, const QVariantMap& result)
{
    if (!ok || !m_personaCombo) return;
    const QVariantList personas = result.value("personas").toList();

    const QString current = m_personaCombo->currentText();
    m_personaCombo->clear();
    m_personaCombo->addItem("(Default)");

    for (const QVariant& pv : personas) {
        const QVariantMap pm = pv.toMap();
        m_personaCombo->addItem(pm.value("name").toString(), pm);
    }

    // Restore selection
    int idx = m_personaCombo->findText(current);
    m_personaCombo->setCurrentIndex(idx >= 0 ? idx : 0);
}

// ---------------------------------------------------------------------------
// Slots — AI Auto-Mix
// ---------------------------------------------------------------------------

void AIPanel::onAutoMixClicked()
{
    if (!LicenseManager::instance()->canMaster()) {
        showError("AI Auto-Mix requires an ElevenLabs API key. Configure keys in Edit → Settings.");
        return;
    }

    // Collect audio paths: last generated + any the user has browsed
    QVariantList paths;
    if (!m_lastAudioPath.isEmpty())
        paths.append(m_lastAudioPath);

    if (paths.isEmpty()) {
        showError("Generate or select audio tracks first.");
        return;
    }

    setGenerating(true);
    if (m_autoMixResultLabel) m_autoMixResultLabel->setText("Analyzing…");

    QVariantMap p;
    p["audio_paths"] = paths;

    m_client->analyzeTrack(p, [this](bool ok, const QVariantMap& res) {
        QMetaObject::invokeMethod(this, [this, ok, res]() {
            onAutoMixFinished(ok, res);
        }, Qt::QueuedConnection);
    });
}

void AIPanel::onAutoMixFinished(bool ok, const QVariantMap& result)
{
    setGenerating(false);
    if (!ok || result.contains("error")) {
        if (m_autoMixResultLabel) m_autoMixResultLabel->setText("Failed.");
        showError(result.value("error", "Auto-Mix failed.").toString());
        return;
    }

    const QVariantList suggestions = result.value("suggestions").toList();
    if (m_autoMixResultLabel)
        m_autoMixResultLabel->setText(
            QString("Applied %1 correction(s)").arg(suggestions.size()));

    emit autoMixReady(suggestions);
}
