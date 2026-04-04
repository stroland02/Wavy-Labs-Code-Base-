#ifdef WAVY_LMMS_CORE

#include "WavyShell.h"
#include "../EngineAPI/EngineAPI.h"
#include "../Transport/TransportBar.h"
#include "../Arrangement/WavyArrangementView.h"
#include "../Arrangement/WavyPianoRollBar.h"
#include "../QML/AIBackend.h"
#include "../QML/GenreModes.h"
#include "../ThemeManager/ThemeManager.h"

#include "MainWindow.h"
#include "GuiApplication.h"
#include "SongEditor.h"
#include "PianoRoll.h"
#include "PatternEditor.h"
#include "AutomationEditor.h"
#include "MixerView.h"

#include <QApplication>
#include <QCloseEvent>
#include <QShowEvent>
#include <QHBoxLayout>
#include <QMdiArea>
#include <QMdiSubWindow>
#include <QMenuBar>
#include <QPushButton>
#include <QSplitter>
#include <QTimer>
#include <QToolBar>
#include <QToolButton>
#include <QVBoxLayout>
#include <QDebug>
#include <QFile>
#include <QPainter>
#include <QSvgRenderer>

// Load an SVG resource and tint its strokes/fills to the given color
static QIcon colorizedSvgIcon(const QString& path, const QColor& color, int size = 20)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) return QIcon();
    QString svg = QString::fromUtf8(f.readAll());
    svg.replace("currentColor", color.name());
    QSvgRenderer renderer(svg.toUtf8());
    QPixmap pix(size, size);
    pix.fill(Qt::transparent);
    QPainter p(&pix);
    renderer.render(&p);
    return QIcon(pix);
}

// Hide all QToolBar children on a QMainWindow (used to remove LMMS editor toolbars)
static void hideToolBars(QMainWindow* win)
{
    if (!win) return;
    for (auto* tb : win->findChildren<QToolBar*>())
        tb->hide();
}

// ---------------------------------------------------------------------------

WavyShell::WavyShell(EngineAPI* engine, QWidget* parent)
    : QMainWindow(parent)
    , m_engine(engine)
{
    setWindowTitle("Wavy Labs");
    setObjectName("WavyShell");
    m_transport = new TransportBar(engine, this);
    m_arrangementView = new WavyArrangementView(engine, this);
    m_pianoRollBar = new WavyPianoRollBar(engine, this);
    buildEditorTabs();
}

// ---------------------------------------------------------------------------

void WavyShell::buildEditorTabs()
{
    m_editorBar = new QWidget(this);
    m_editorBar->setObjectName("WavyEditorBar");
    m_editorBar->setFixedHeight(34);

    auto* barLayout = new QHBoxLayout(m_editorBar);
    barLayout->setContentsMargins(0, 0, 0, 0);
    barLayout->setSpacing(0);

    static const char* LABELS[] = { "Home", "Song", "Piano Roll", "Pattern", "Automation", "Mixer" };
    for (int i = 0; i < TabCount; ++i) {
        auto* btn = new QPushButton(LABELS[i], m_editorBar);
        btn->setObjectName("WavyEditorTab");
        btn->setCheckable(true);
        btn->setChecked(i == 0);
        btn->setFlat(false);
        btn->setFixedHeight(34);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);  // fill width equally
        btn->setFocusPolicy(Qt::NoFocus);
        const int idx = i;
        connect(btn, &QPushButton::clicked, this, [this, idx]() {
            onEditorTabClicked(idx);
        });
        barLayout->addWidget(btn);
        m_editorBtns.append(btn);
    }
}

// ---------------------------------------------------------------------------

void WavyShell::adoptLmmsContent(lmms::gui::MainWindow* lmmsWin)
{
    m_lmmsWin = lmmsWin;

    // ── Take LMMS central widget (sidebar splitter + workspace) ──────────
    QWidget* lmmsContent = lmmsWin->takeCentralWidget();
    if (!lmmsContent) {
        qWarning() << "[WavyShell] Failed to take LMMS central widget";
        return;
    }
    m_lmmsContent = lmmsContent;   // keep ref so setAIPanel() can find the splitter

    // ── Custom unified header: menu bar + transport in one row ────────────
    // Avoids setCornerWidget() fragility where Qt hides the corner widget when
    // it calculates insufficient space during the initial show/maximize pass.
    QMenuBar* lmmsMenuBar = lmmsWin->menuBar();
    lmmsMenuBar->setParent(nullptr);   // detach from lmmsWin before reparenting
    m_header = new QWidget(this);
    m_header->setObjectName("WavyHeader");
    m_header->setFixedHeight(44);
    auto* hdrLayout = new QHBoxLayout(m_header);
    hdrLayout->setContentsMargins(0, 0, 0, 0);
    hdrLayout->setSpacing(0);
    hdrLayout->addWidget(lmmsMenuBar, 0, Qt::AlignVCenter);  // menu bar vertically centred
    hdrLayout->addWidget(m_transport, 1);                    // transport stretches to fill the rest

    // ── Build central layout: header + editor tabs + LMMS workspace ──────
    QWidget* container = new QWidget(this);
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    layout->addWidget(m_header);
    layout->addWidget(m_editorBar);
    layout->addWidget(m_arrangementView);      // visible only when Song tab active
    layout->addWidget(m_pianoRollBar);          // visible only when Piano Roll tab active
    m_pianoRollBar->setVisible(false);

    // Wrap LMMS content in a QStackedWidget so dashboard and editors can alternate
    m_workStack = new QStackedWidget(container);
    m_workStack->addWidget(lmmsContent);       // index 0: LMMS editors
    layout->addWidget(m_workStack, 1);
    // dashboard added later via setDashboard()

    setCentralWidget(container);

    // ── Track editor switches via workspace signals ──────────────────────
    auto* workspace = lmmsWin->workspace();
    connect(workspace, &QMdiArea::subWindowActivated,
            this, &WavyShell::onSubWindowActivated);
    // Retile when the workspace is resized (catches main-window resize)
    workspace->installEventFilter(this);

    // ── Force clean layout ───────────────────────────────────────────────
    // Hide all MDI subwindows, then show + maximize only Song Editor.
    for (auto* sub : workspace->subWindowList())
        sub->hide();

    auto* gui = lmms::gui::getGUI();
    auto* songEditor = gui->songEditor();
    auto* songParent = songEditor->parentWidget();
    if (songParent) {
        songParent->show();
        songParent->showMaximized();
    }

    // Wire project buttons in transport bar to LMMS MainWindow
    m_transport->setMainWindow(lmmsWin);

    // Connect arrangement toolbar to the actual SongEditor (inside SongEditorWindow)
    m_arrangementView->connectToSongEditor(songEditor->m_editor);
    m_arrangementView->setVisible(false);   // hidden — native toolbars used instead
    m_pianoRollBar->setVisible(false);       // hidden — native toolbars used instead

    // Set "Home" button as active (dashboard shows on launch)
    if (!m_editorBtns.isEmpty())
        m_editorBtns[EditorTab::Home]->setChecked(true);

    // Connect piano roll toolbar to the actual PianoRoll editor
    m_pianoRollBar->connectToPianoRoll(gui->pianoRoll()->editor());

    // All editors keep their native LMMS toolbars inside their MDI pane.

    // Hide LMMS MainWindow's global toolbar (tempo, master vol, etc.)
    if (auto* globalToolbar = lmmsWin->toolBar())
        globalToolbar->hide();

    // ── Style the LMMS sidebar with Wavy theme ────────────────────────
    // Find the SideBar (QToolBar) via findChild — it's private on MainWindow
    if (auto* sideBar = lmmsContent->findChild<QToolBar*>()) {
        sideBar->setObjectName("WavySideBar");
        sideBar->setAutoFillBackground(true);
        // Apply sidebar color now — applyTheme() ran before this widget existed.
        // ThemeManager::applyTheme() will also re-apply on live theme switches.
        Wavy::ThemeManager::applySidebarStyle(sideBar,
            Wavy::ThemeManager::currentTheme());

        // Force sidebar to exact width so splitter respects our size.
        sideBar->setFixedWidth(48);  // Icon bar — 20px icons + padding
        sideBar->setMinimumWidth(48);
        sideBar->setMaximumWidth(48);
        sideBar->setIconSize(QSize(22, 22));
        sideBar->setContentsMargins(0, 0, 0, 0);
        if (auto* lay = sideBar->layout()) {
            lay->setContentsMargins(0, 0, 0, 0);
            lay->setSpacing(0);
        }
        for (QToolButton* btn : sideBar->findChildren<QToolButton*>()) {
            btn->setMinimumWidth(0);
            btn->setMaximumWidth(48);
            btn->setContentsMargins(0, 0, 0, 0);
            btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
            btn->setToolButtonStyle(Qt::ToolButtonIconOnly);
        }
    }

    // ── Hide LMMS MainWindow ─────────────────────────────────────────────
    lmmsWin->hide();

    qDebug() << "[WavyShell] Adopted LMMS content, MainWindow hidden";
}

// ---------------------------------------------------------------------------

void WavyShell::onEditorTabClicked(int index)
{
    if (!m_lmmsWin) return;

    if (index == EditorTab::Home) {
        // Show dashboard, uncheck all editor buttons
        if (m_workStack) m_workStack->setCurrentIndex(1);
        for (int j = EditorTab::Song; j < TabCount; ++j)
            m_editorBtns[j]->setChecked(false);
        m_editorBtns[EditorTab::Home]->setChecked(true);
        return;
    }

    // Show LMMS workspace
    if (m_workStack) m_workStack->setCurrentIndex(0);
    m_editorBtns[EditorTab::Home]->setChecked(false);

    auto* gui = lmms::gui::getGUI();
    if (!gui) return;

    const bool nowOpen = m_editorBtns[index]->isChecked();

    // Map tab index → editor widget (index 0 = Home has no MDI editor)
    QWidget* editors[TabCount] = {
        nullptr,                    // Home — no MDI editor
        gui->songEditor(),
        gui->pianoRoll(),
        gui->patternEditor(),
        gui->automationEditor(),
        gui->mixerView()
    };

    // Show or hide that editor's MDI subwindow directly
    if (QWidget* ed = editors[index]) {
        if (auto* sub = qobject_cast<QMdiSubWindow*>(ed->parentWidget())) {
            if (nowOpen)
                sub->show();
            else
                sub->hide();
        }
    }

    tileVisibleEditors();
}

// ---------------------------------------------------------------------------

void WavyShell::tileVisibleEditors()
{
    if (!m_lmmsWin) return;
    auto* gui = lmms::gui::getGUI();
    if (!gui) return;

    auto* workspace = m_lmmsWin->workspace();

    // Collect open subwindows in tab order (index 0 = Home has no MDI editor)
    QWidget* editors[TabCount] = {
        nullptr,
        gui->songEditor(),
        gui->pianoRoll(),
        gui->patternEditor(),
        gui->automationEditor(),
        gui->mixerView()
    };

    QList<QMdiSubWindow*> visible;
    for (int i = 1; i < TabCount; ++i) {  // start at 1, skip Home
        if (!m_editorBtns[i]->isChecked() || !editors[i]) continue;
        if (auto* sub = qobject_cast<QMdiSubWindow*>(editors[i]->parentWidget()))
            visible.append(sub);
    }

    // Hide any subwindow not in the open set
    for (auto* sub : workspace->subWindowList()) {
        if (!visible.contains(sub))
            sub->hide();
    }

    // Release geometry locks from previous tile pass
    m_isTiling = true;
    for (auto it = m_tiledGeoms.begin(); it != m_tiledGeoms.end(); ++it)
        it.key()->removeEventFilter(this);
    m_tiledGeoms.clear();

    if (visible.isEmpty()) { m_isTiling = false; return; }

    const int W = workspace->width();
    const int H = workspace->height();
    const int n = visible.size();
    constexpr int kGap = 2;   // px separator line shown between panels

    auto lockSub = [&](QMdiSubWindow* sub, const QRect& geom) {
        sub->setWindowFlags(Qt::SubWindow | Qt::FramelessWindowHint);
        sub->show();
        sub->setGeometry(geom);
        // Lock: install event filter so any user-initiated move/resize is snapped back
        m_tiledGeoms[sub] = geom;
        sub->installEventFilter(this);
    };

    if (n == 1) {
        lockSub(visible[0], QRect(0, 0, W, H));
    } else {
        const int w = (W - kGap * (n - 1)) / n;
        for (int i = 0; i < n; ++i)
            lockSub(visible[i], QRect(i * (w + kGap), 0, w, H));
    }

    m_isTiling = false;
}

// ---------------------------------------------------------------------------

bool WavyShell::eventFilter(QObject* obj, QEvent* e)
{
    if (!m_isTiling) {
        // Snap tiled subwindows back if the user drags or resizes them
        if (e->type() == QEvent::Move || e->type() == QEvent::Resize) {
            auto* sub = qobject_cast<QMdiSubWindow*>(obj);
            if (sub) {
                auto it = m_tiledGeoms.find(sub);
                if (it != m_tiledGeoms.end()) {
                    m_isTiling = true;
                    sub->setGeometry(it.value());
                    m_isTiling = false;
                    return true;   // consume — do not propagate
                }
            }
        }

        // Retile when the MDI workspace itself is resized (e.g. main window resize
        // or splitter drag) so subwindows always fill the available area.
        if (e->type() == QEvent::Resize && m_lmmsWin
                && obj == m_lmmsWin->workspace()) {
            QTimer::singleShot(0, this, [this]() { tileVisibleEditors(); });
        }
    }
    return QMainWindow::eventFilter(obj, e);
}

// ---------------------------------------------------------------------------

void WavyShell::onSubWindowActivated(QMdiSubWindow* sub)
{
    Q_UNUSED(sub);
    // Native LMMS toolbars are used inside each MDI pane — nothing extra to sync.
}

// ---------------------------------------------------------------------------

void WavyShell::cleanupMdiWindows()
{
    if (!m_lmmsWin) return;

    auto* gui = lmms::gui::getGUI();
    if (!gui) return;

    auto* workspace = m_lmmsWin->workspace();
    auto* songEditor = gui->songEditor();

    // Hide every MDI subwindow except the Song Editor
    for (auto* sub : workspace->subWindowList()) {
        if (sub->widget() == songEditor) {
            sub->showMaximized();
        } else {
            sub->hide();
        }
    }
}

// ---------------------------------------------------------------------------

void WavyShell::setAIPanel(QWidget* panel)
{
    if (!panel) return;
    m_aiPanel = panel;

    // lmmsContent is a plain QWidget wrapping an hbox that contains the splitter.
    // Use findChild to reach the QSplitter regardless of nesting depth.
    QSplitter* splitter = nullptr;
    if (m_lmmsContent) {
        splitter = qobject_cast<QSplitter*>(m_lmmsContent);          // direct
        if (!splitter)
            splitter = m_lmmsContent->findChild<QSplitter*>();        // nested
    }

    if (splitter) {
        // LMMS splitter layout (default config):
        //   [0] SideBar icons   [1..N-1] SideBarWidgets (hidden)   [N] workspace
        // Insert at index 1 → [icons | AI panel | hidden widgets | workspace]
        panel->setMinimumWidth(240);
        splitter->insertWidget(1, panel);
        m_splitter = splitter;   // cache for panel toggle resize

        // Set comfortable widths after layout is settled.
        // setSizes must supply a value for every item in the splitter.
        // Use a helper lambda so we can call it both from the timer and from showEvent.
        m_splitterSizesDone = false;
        auto applySizes = [this, splitter]() {
            if (m_splitterSizesDone) return;
            const int totalW = splitter->width();
            if (totalW < 100) return;   // window not laid out yet — wait for resize
            m_splitterSizesDone = true;
            const int n = splitter->count();
            QList<int> sz(n, 0);
            sz[0] = 48;                               // sidebar icon bar
            sz[1] = 326;                              // AI panel
            sz[n - 1] = qMax(600, totalW - 374);      // workspace gets the rest
            splitter->setSizes(sz);
            QTimer::singleShot(0, this, [this]() { tileVisibleEditors(); });
        };
        m_applySplitterSizes = applySizes;   // store so showEvent can call it

        // Fire at 300 ms (enough time for showMaximized to complete on slow machines).
        QTimer::singleShot(300, this, [applySizes]() { applySizes(); });
        return;
    }

    qWarning() << "[WavyShell] setAIPanel: splitter not found — using left dock fallback";
    auto* dock = new QDockWidget("AI", this);
    dock->setObjectName("WavyAIDock");
    dock->setWidget(panel);
    dock->setFeatures(QDockWidget::DockWidgetMovable | QDockWidget::DockWidgetFloatable);
    dock->setMinimumWidth(300);
    addDockWidget(Qt::LeftDockWidgetArea, dock);
}

// ---------------------------------------------------------------------------

void WavyShell::addAINavButtons(AIBackend* backend)
{
    if (!backend) return;

    // Find the sidebar QToolBar (styled as "WavySideBar" in adoptLmmsContent)
    auto* sideBar = findChild<QToolBar*>("WavySideBar");
    if (!sideBar) {
        qWarning() << "[WavyShell] addAINavButtons: WavySideBar not found";
        return;
    }

    // Reference action for insertion (insert before the first existing LMMS tab)
    QAction* insertBefore = sideBar->actions().isEmpty() ? nullptr
                                                         : sideBar->actions().first();

    static const struct { const char* label; const char* tip; const char* icon; int page; } NAV[] = {
        {"Gen",  "Generate",     ":/wavy/sidebar/gen.svg",     0},
        {"Chat", "Chat",         ":/wavy/sidebar/chat.svg",    1},
        {"Lib",  "Library",      ":/wavy/sidebar/library.svg", 2},
        {"Vox",  "Vocal / SFX",  ":/wavy/sidebar/vox.svg",     3},
        {"Mix",  "Mix / Master", ":/wavy/sidebar/mix.svg",     4},
        {"Tool", "Tools",        ":/wavy/sidebar/tool.svg",    5},
        {"Log",  "Console",      ":/wavy/sidebar/log.svg",     6},
    };

    // Determine icon colors based on theme luminance
    const QString themeId = Wavy::ThemeManager::currentTheme();
    const bool isDark = (themeId == "wavy-ruby" || themeId == "wavy-midnight" || themeId == "wavy-sunset");
    const QColor normalColor = isDark ? QColor("#AAA8B0") : QColor("#6B6060");
    const QColor activeColor = isDark ? QColor("#FFFFFF") : QColor("#D4736C");

    // Insert buttons in forward order before the same anchor → they appear 0–6
    for (int i = 0; i < 7; ++i) {
        auto* btn = new QToolButton(sideBar);

        // Build multi-state icon: normal + checked/active
        QIcon icon;
        QPixmap normalPix = colorizedSvgIcon(NAV[i].icon, normalColor, 20).pixmap(20, 20);
        QPixmap activePix = colorizedSvgIcon(NAV[i].icon, activeColor, 20).pixmap(20, 20);
        icon.addPixmap(normalPix, QIcon::Normal, QIcon::Off);
        icon.addPixmap(activePix, QIcon::Normal, QIcon::On);
        icon.addPixmap(activePix, QIcon::Active, QIcon::On);
        icon.addPixmap(activePix, QIcon::Selected, QIcon::On);

        btn->setIcon(icon);
        btn->setIconSize(QSize(20, 20));
        btn->setToolTip(NAV[i].tip);
        btn->setObjectName("WavyAINavBtn");
        btn->setCheckable(true);
        btn->setChecked(false);   // panel starts hidden; no button pre-checked
        btn->setFixedHeight(36);
        btn->setMinimumWidth(0);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        btn->setToolButtonStyle(Qt::ToolButtonIconOnly);

        const int idx = i;
        const int page = NAV[i].page;
        connect(btn, &QToolButton::clicked, this, [this, backend, page, idx](bool checked) {
            if (!checked) {
                // User clicked the active button → close AI panel
                setAIPanelVisible(false);
                // Leave currentPage as-is (so reopening lands on same tab)
            } else {
                // User clicked a new button → open panel on that page
                setAIPanelVisible(true);
                backend->setCurrentPage(page);
                // Uncheck all other AI nav buttons (exclusive selection)
                for (int j = 0; j < m_aiNavButtons.size(); ++j) {
                    if (j != idx) m_aiNavButtons[j]->setChecked(false);
                }
            }
        });

        m_aiNavButtons.append(btn);
        sideBar->insertWidget(insertBefore, btn);
    }

    // Add a separator between AI nav buttons and existing LMMS sidebar tabs
    if (insertBefore)
        sideBar->insertSeparator(insertBefore);

    // Start with Generate (index 0) highlighted; panel is already visible on launch
    if (!m_aiNavButtons.isEmpty())
        m_aiNavButtons[0]->setChecked(true);

    // Sync checked state when page changes programmatically (not from button clicks)
    connect(backend, &AIBackend::currentPageChanged, this, [this](int page) {
        for (int i = 0; i < m_aiNavButtons.size(); ++i)
            m_aiNavButtons[i]->setChecked(i == page);
    });

    // ── Genre Mode wiring: transport combo → backend → DAW + session ctx ──
    connect(m_transport, &TransportBar::genreModeRequested,
            backend,     &AIBackend::setGenreMode);
    // Sync combo display when mode changes externally (e.g. from QML)
    connect(backend, &AIBackend::activeGenreChanged,
            this, [this](const QString& key) {
                const GenreModeCfg* cfg = findGenreMode(key);
                if (cfg) m_transport->setGenreMode(QString(cfg->displayName));
                // Also handle "custom" which has no static entry
                if (key == QStringLiteral("custom"))
                    m_transport->setGenreMode(QStringLiteral("Custom"));
            });

    // Wire backend to transport for genre config popup
    m_transport->setBackend(backend);
}

// ---------------------------------------------------------------------------

void WavyShell::setAIPanelVisible(bool visible)
{
    if (!m_aiPanel || !m_splitter) return;
    // No-op if already in the requested state — avoids stealing workspace
    // space on every tab click when the panel is already visible.
    if (m_aiPanel->isVisible() == visible) return;
    const int idx = m_splitter->indexOf(m_aiPanel);
    if (idx < 0) return;

    QList<int> sz = m_splitter->sizes();
    const int n    = sz.size();
    const int last = n - 1;   // workspace is always the last splitter child

    if (!visible) {
        // Save width so we can restore it on reopen
        if (sz[idx] > 0)
            m_aiPanelWidth = sz[idx];

        // Hide FIRST — QSplitter only enforces minimum sizes for visible widgets.
        // Calling setSizes({...,0,...}) while visible gets clamped by the 280px min.
        m_aiPanel->hide();

        // Collapse all slots except sidebar (0) and workspace (last) to 0,
        // then give everything freed to the workspace — avoids phantom gaps
        // left by intermediate hidden LMMS sidebar-widgets.
        int freed = 0;
        for (int i = 1; i < last; ++i) freed += sz[i];
        for (int i = 1; i < last; ++i) sz[i] = 0;
        sz[last] += freed;
        m_splitter->setSizes(sz);
    } else {
        // Show first, then give it its width back.
        m_aiPanel->show();
        const int give = qMin(m_aiPanelWidth, qMax(0, sz[last] - 400));
        sz[last] -= give;
        sz[idx]   = give;
        m_splitter->setSizes(sz);
    }

    // Defer tiling so the splitter finishes its relayout first —
    // workspace->width() is still stale at this point.
    QTimer::singleShot(0, this, [this]() {
        tileVisibleEditors();
    });
}

// ---------------------------------------------------------------------------

void WavyShell::setDashboard(QWidget* dash)
{
    if (!dash || !m_workStack) return;
    m_workStack->addWidget(dash);          // index 1
    m_workStack->setCurrentIndex(1);       // show dashboard on launch
}

void WavyShell::activateEditorTab(int idx)
{
    if (idx < 0 || idx >= TabCount) return;
    m_editorBtns[idx]->setChecked(true);
    onEditorTabClicked(idx);
}

// ---------------------------------------------------------------------------

void WavyShell::showEvent(QShowEvent* event)
{
    QMainWindow::showEvent(event);
    // After show(), the window will receive resize events as it settles into its
    // final geometry (e.g. after showMaximized). The applySizes lambda checks
    // the real width and applies sizes once it's non-trivial (>100px).
    // Firing it here also handles the case where the 300 ms timer is too late.
    if (m_applySplitterSizes)
        QTimer::singleShot(50, this, [this]() { m_applySplitterSizes(); });
}

void WavyShell::closeEvent(QCloseEvent* event)
{
    if (m_lmmsWin) {
        // Forward close to LMMS MainWindow — it handles save prompts.
        QCloseEvent lmmsClose;
        QApplication::sendEvent(m_lmmsWin, &lmmsClose);
        if (!lmmsClose.isAccepted()) {
            event->ignore();
            return;
        }
    }
    event->accept();
}

#endif // WAVY_LMMS_CORE
