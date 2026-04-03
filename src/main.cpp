#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIcon>
#include <QSplashScreen>
#include <QPixmap>
#include <QStandardPaths>
#include <QDebug>
#include <QTimer>
#include <QMenu>
#include <QActionGroup>
#include <QMenuBar>
#include <QPushButton>
#include <cmath>
#include <cstdio>
#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <mmsystem.h>
#endif

// ── File-based Qt message handler (captures qDebug/qWarning from QML + C++) ──
static FILE* g_logFile = nullptr;
static void wavyMessageHandler(QtMsgType, const QMessageLogContext&, const QString& msg)
{
    if (!g_logFile) return;
    fprintf(g_logFile, "%s\n", msg.toUtf8().constData());
    fflush(g_logFile);
}
static void installWavyLogger(const char* argv0)
{
    // Resolve log path relative to the executable directory
    QFileInfo exe(QString::fromLocal8Bit(argv0));
    const QString logPath = exe.absolutePath() + "/wavy_debug.log";
    g_logFile = fopen(logPath.toStdString().c_str(), "w");
    if (g_logFile) qInstallMessageHandler(wavyMessageHandler);
}


#include "IPC/AIClient.h"
#include "IPC/BackendLauncher.h"

#ifdef WAVY_LMMS_CORE
// ── Full LMMS + Wavy build ────────────────────────────────────────────────────
#include <QThread>
#include "MainApplication.h"
#include "ConfigManager.h"
#include "Engine.h"
#include "Mixer.h"
#include "GuiApplication.h"
#include "MainWindow.h"
#include "Song.h"
#include "NotePlayHandle.h"
#include "SongEditor.h"
#include "AutomationEditor.h"
#include "PatternEditor.h"
#include "PianoRoll.h"
#include <QMdiSubWindow>
// Wavy UI components embedded in LMMS window
#include "AIPanel/AIPanel.h"
#include "ThemeManager/ThemeManager.h"
#include "AISideBarPage.h"
#include "Dialogs/OnboardingWizard.h"
#include "EngineAPI/LmmsEngine.h"
#include "Shell/WavyShell.h"
#include "LicenseGate/LicenseManager.h"
#include "LicenseGate/LoginDialog.h"
#include "LicenseGate/ApiKeySettings.h"
#include "ModelManager/ModelManager.h"
#include "QML/AIBackend.h"
#include <QQuickWidget>
#include <QQmlContext>
#include <QQuickStyle>
#else
// ── Standalone dev harness (no LMMS core) ────────────────────────────────────
#include <QApplication>
#include <QDockWidget>
#include <QFileInfo>
#include <QLabel>
#include <QListWidget>
#include <QMainWindow>
#include <QTabWidget>
#include <QThread>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFrame>
#include <QWidget>
#include "AIPanel/AIPanel.h"
#include "ThemeManager/ThemeManager.h"
#include "Dialogs/OnboardingWizard.h"
#include "EngineAPI/StubEngine.h"
#include "LicenseGate/LicenseManager.h"
#include "LicenseGate/LoginDialog.h"
#include "ModelManager/ModelManager.h"
#endif

// ---------------------------------------------------------------------------

static void applyTheme(QApplication& app)
{
    (void)app;
    Wavy::ThemeManager::applyTheme(Wavy::ThemeManager::currentTheme());
}

static void ensureDataDirs()
{
    const QString dataPath = QStandardPaths::writableLocation(
        QStandardPaths::AppDataLocation);
    QDir().mkpath(dataPath + "/models");
    QDir().mkpath(dataPath + "/generations");
}

// ---------------------------------------------------------------------------

int main(int argc, char* argv[])
{
    installWavyLogger(argv[0]);
    qDebug() << "[main] Wavy starting up";

#ifdef WAVY_LMMS_CORE
    // ── LMMS + Wavy integrated launch ────────────────────────────────────────
    //
    // MainApplication is a QApplication subclass that handles macOS file-open
    // events and Win32 native event filtering.
    lmms::gui::MainApplication app(argc, argv);
    app.setApplicationName("Wavy Labs");
    app.setApplicationVersion(WAVY_VERSION);
    app.setOrganizationName("Wavy Labs");
    app.setOrganizationDomain("wavylab.net");

    // Ensure Qt finds plugin DLLs (sqldrivers, platforms, etc.) next to the exe
    QCoreApplication::addLibraryPath(QCoreApplication::applicationDirPath());

    ensureDataDirs();

    // Initialize LMMS memory managers (normally done in lmms-core main.cpp)
    lmms::NotePlayHandleManager::init();

    // ── AI backend — start server.py before GuiApplication is created ─────────
    // GuiApplication() → MainWindow constructor → m_aiClient->connectToBackend()
    // BackendLauncher retries connection, so starting it here gives server.py
    // time to come up while LMMS engine initialises inside GuiApplication().
    AIClient*        aiClient = AIClient::instance();
    BackendLauncher* launcher = new BackendLauncher(aiClient, &app);

    QObject::connect(launcher, &BackendLauncher::logLine,
                     &app, [](const QString& line) { qDebug().noquote() << line; });

    QObject::connect(&app, &QApplication::aboutToQuit,
                     launcher, &BackendLauncher::stop);

    launcher->start();   // non-blocking — fires ready/failed signals asynchronously

    // ── LMMS config ────────────────────────────────────────────────────────────
    // loadConfigFile("") uses the default config location (~/.lmmsrc.xml on Linux,
    // %APPDATA%/LMMS/.lmmsrc.xml on Windows).
    lmms::ConfigManager::inst()->loadConfigFile({});

    // Auto-configure soundfont: if defaultsf2 is not set, look for the bundled
    // GeneralUser GS sf2 in our AppLocalData directory and wire it up silently.
    // This covers both fresh installs (installer places the file there) and dev
    // builds (file already present from manual setup).
#ifdef LMMS_HAVE_FLUIDSYNTH
    {
        auto* cfg = lmms::ConfigManager::inst();
        if (cfg->sf2File().isEmpty()) {
            const QString sf2Path =
                QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)
                + "/GeneralUser_GS.sf2";
            if (QFile::exists(sf2Path)) {
                cfg->setSF2File(sf2Path);
                cfg->saveConfigFile();
                qDebug() << "[main] Auto-configured soundfont:" << sf2Path;
            }
        }
    }
#endif

    // Default to SDL audio so we don't get the "Audio device setup failed"
    // dialog when JACK isn't installed (most Windows users).
    if (lmms::ConfigManager::inst()->value("audioengine", "audiodev").isEmpty())
        lmms::ConfigManager::inst()->setValue("audioengine", "audiodev", "SDL (Simple DirectMedia Layer)");


    // ── Override LMMS splash with Wavy branding ──────────────────────────────
    // GuiApplication loads splash from "artwork:splash". We prepend our data
    // dir to the artwork search path so our splash.png takes priority.
    {
        QString wavyData = QCoreApplication::applicationDirPath() + "/../data";
        if (!QDir(wavyData).exists())
            wavyData = QCoreApplication::applicationDirPath() + "/data";
        QDir::addSearchPath("artwork", wavyData + "/icons");
    }

    // ── Add lmms-core data dir to Qt "data:" search path ─────────────────────
    // build/data/ is empty — presets live in lmms-core/data/. Add it so that
    // loadXpfPreset() can open "data:/presets/BitInvader/toy_piano.xpf" etc.
    {
        const QString appDir = QCoreApplication::applicationDirPath();
        // Dev build: lmms.exe is in build/, lmms-core/data/ is one level up
        const QString coreData = appDir + "/../lmms-core/data/";
        if (QDir(coreData).exists())
            QDir::addSearchPath("data", coreData);
        else {
            // Installed / release build: look for data/ sibling to exe
            const QString relData = appDir + "/data/";
            if (QDir(relData + "presets").exists())
                QDir::addSearchPath("data", relData);
        }
    }

    // ── Create LMMS GUI ────────────────────────────────────────────────────────
    // GuiApplication() manages its own splash screen, initialises the Engine,
    // creates MainWindow (with Wavy patches applied), and all MDI sub-windows.
    // The constructor blocks until the splash has finished.
    new lmms::gui::GuiApplication();

    // Apply Wavy theme AFTER GuiApplication so we override LmmsStyle::LmmsStyle()
    // which calls qApp->setStyleSheet() internally and would wipe our QSS otherwise.
    applyTheme(app);

    // ── Wavy AI UI — embed in LMMS MainWindow ───────────────────────────────
    auto* lmmsWin = lmms::gui::getGUI()->mainWindow();

    // ── Create EngineAPI ─────────────────────────────────────────────────────
    auto* engine = new LmmsEngine(&app);
    engine->setPianoRoll(lmms::gui::getGUI()->pianoRoll());
    engine->setMainWindow(lmmsWin);

    ModelManager* modelMgr = new ModelManager();
    modelMgr->setClient(aiClient);

    // When backend connects, query it for available models + health status
    QObject::connect(aiClient, &AIClient::connected,
                     modelMgr, &ModelManager::refreshStatus);

    // If already connected (backend came up fast), refresh immediately
    if (aiClient->isConnected())
        modelMgr->refreshStatus();

    // ── QML AI Panel — replaces old AIPanel sidebar tabs ─────────────────────
    QQuickStyle::setStyle("Basic");

    AIBackend* aiBackend = new AIBackend(aiClient, modelMgr, &app);
    aiBackend->setEngine(engine);  // enable session key detection in dawContext()

    auto* quickWidget = new QQuickWidget;
    quickWidget->setObjectName("WavyAIPanel");
    quickWidget->setResizeMode(QQuickWidget::SizeRootObjectToView);
    quickWidget->rootContext()->setContextProperty("backend", aiBackend);
    quickWidget->rootContext()->setContextProperty("theme",
        Wavy::ThemeManager::themeObject());
    quickWidget->setSource(QUrl("qrc:/wavy/qml/MainPanel.qml"));
    qDebug() << "[ai-panel] status:" << quickWidget->status();
    for (const auto& err : quickWidget->errors())
        qDebug() << "[ai-panel] error:" << err.toString();
    quickWidget->setMinimumWidth(300);
    // Ignore QML implicit-width changes so tab switches never shift the splitter
    quickWidget->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Expanding);

    // ── Wire AIBackend outputs → EngineAPI ──────────────────────────────────
    QObject::connect(aiBackend, &AIBackend::audioReady,
        engine, [engine](const QString& name, const QString& path, double) {
            engine->insertAudioTrack(name, path, QColor("#4fc3f7"));
        });

    QObject::connect(aiBackend, &AIBackend::insertRequested,
        engine, [engine](const QString& audioPath, const QString& trackName, const QVariantList& sections) {
            if (!sections.isEmpty())
                engine->insertAudioTrackWithSections(trackName, audioPath, QColor("#4fc3f7"), sections);
            else
                engine->insertAudioTrack(trackName, audioPath, QColor("#4fc3f7"));
        });

    QObject::connect(aiBackend, &AIBackend::autoMixReady,
        engine, [engine](const QVariantList& suggestions) {
            engine->applyAutoMix(suggestions);
        });

    QObject::connect(aiBackend, &AIBackend::midiFileReady,
        engine, [engine](const QString& path) {
            engine->importMidiToActiveClip(path);
        });

    // Piano Roll AI Notes: prompt → MIDI → notes inserted into active clip
    auto* pianoRollWin = lmms::gui::getGUI()->pianoRoll();
    QObject::connect(pianoRollWin, &lmms::gui::PianoRollWindow::aiNotesRequested,
        engine, [aiClient, engine](const QString& prompt, int tempo, int bars) {
            QVariantMap p;
            p["prompt"] = prompt;
            p["tempo"]  = tempo;
            p["bars"]   = bars;
            aiClient->promptToMidi(p, [engine](bool ok, const QVariantMap& res) {
                if (!ok || res.contains("error")) return;
                const QString path = res.value("midi_path").toString();
                engine->importMidiToActiveClip(path);
            });
        });

    // Pattern Editor AI Beat: prompt → MIDI → notes inserted into Piano Roll clip
    auto* patternEditorWin = lmms::gui::getGUI()->patternEditor();
    QObject::connect(patternEditorWin, &lmms::gui::PatternEditorWindow::aiNotesRequested,
        engine, [aiClient, engine](const QString& prompt, int tempo, int bars) {
            QVariantMap p;
            p["prompt"] = prompt;
            p["tempo"]  = tempo;
            p["bars"]   = bars;
            aiClient->promptToMidi(p, [engine](bool ok, const QVariantMap& res) {
                if (!ok || res.contains("error")) return;
                const QString path = res.value("midi_path").toString();
                engine->importMidiToActiveClip(path);
            });
        });

    QObject::connect(aiBackend, &AIBackend::stemsReady,
        engine, [engine](const QStringList& paths, const QStringList& names) {
            engine->insertStemTracks(paths, names);
        });

    QObject::connect(aiBackend, &AIBackend::codeTracksReady,
        engine, [engine](const QStringList& paths, const QStringList& names) {
            engine->insertStemTracks(paths, names);
        });

    QObject::connect(aiBackend, &AIBackend::actionsReady,
        engine, [engine](const QVariantList& actions) {
            engine->dispatchActions(actions);
        });

    // Helper: enrich track name with preset + genre info
    static auto enrichTrackName = [](const QString& baseName,
                                     const QString& instrument,
                                     const QString& presetPath,
                                     const QString& activeGenre) -> QString
    {
        // Skip enrichment for audiofileprocessor drum sample tracks — name is already descriptive
        if (instrument.toLower() == QStringLiteral("audiofileprocessor"))
            return baseName;

        // Derive a short label from preset path or plugin name
        QString label;
        if (!presetPath.isEmpty()) {
            // "TripleOscillator/LSP-HousePiano.xpf" → "LSP-HousePiano"
            QString fn = QFileInfo(presetPath).completeBaseName();
            if (!fn.isEmpty()) label = fn;
        }
        if (label.isEmpty() && !instrument.isEmpty()) {
            // Skip overly generic plugin names
            const QString low = instrument.toLower();
            if (low != QStringLiteral("tripleoscillator") && low != QStringLiteral("kicker")) {
                // Capitalize first letter
                label = instrument;
                label[0] = label[0].toUpper();
            }
        }

        // Nothing to enrich — return as-is (e.g. single-track library import)
        if (label.isEmpty() && activeGenre.isEmpty()) return baseName;

        // For drums with kicker, still show "Kicker" when a genre is active
        if (label.isEmpty() && !activeGenre.isEmpty()
            && instrument.toLower() == QStringLiteral("kicker")) {
            label = QStringLiteral("Kicker");
        }

        // Build suffix
        QString suffix;
        QString genreDisplay;
        if (!activeGenre.isEmpty()) {
            genreDisplay = activeGenre;
            genreDisplay[0] = genreDisplay[0].toUpper();
        }

        if (!label.isEmpty() && !genreDisplay.isEmpty())
            suffix = label + QStringLiteral(" (") + genreDisplay + QStringLiteral(")");
        else if (!label.isEmpty())
            suffix = label;
        else if (!genreDisplay.isEmpty())
            suffix = QStringLiteral("(") + genreDisplay + QStringLiteral(")");

        if (suffix.isEmpty()) return baseName;

        // Guard against double-enrichment
        if (baseName.contains(suffix)) return baseName;

        return baseName + QStringLiteral(" \u2014 ") + suffix;
    };

    // Compose agent — "arrange" / "single" mode: create one track per generated MIDI part
    QObject::connect(aiBackend, &AIBackend::composeReady,
        engine, [engine, aiBackend](const QVariantList& parts, const QString& /*explanation*/) {
            qDebug() << "[composeReady] parts count:" << parts.size();
            const QString activeGenre = aiBackend->activeGenre();
            QVariantList actions;
            for (const QVariant& pv : parts) {
                const QVariantMap part = pv.toMap();
                const QString rawName  = part.value("name", "AI Track").toString();
                const QString instr    = part.value("instrument", "tripleoscillator").toString();
                const QString preset   = part.value("preset_name", "").toString();
                const QString name     = enrichTrackName(rawName, instr, preset, activeGenre);
                const QString midiPath = part.value("midi_path", "").toString();
                const bool    isSeed   = part.value("is_seed", false).toBool();
                qDebug() << "[composeReady] part:" << name
                         << "| is_seed:" << isSeed
                         << "| midi_path:" << midiPath
                         << "| exists:" << QFile::exists(midiPath);
                QVariantMap action;
                action["type"]        = part.value("action_type", "create_midi_track").toString();
                action["name"]        = name;
                action["midi_path"]   = midiPath;
                action["color"]       = part.value("color", "#9b59b6");
                action["bars"]        = part.value("bars", 4);
                action["instrument"]  = instr;
                action["preset_name"] = preset;
                action["start_bar"]   = part.value("start_bar", 0);
                action["reverb_wet"]  = part.value("reverb_wet", 0.0);
                action["gm_patch"]    = part.value("gm_patch", -1);
                actions.append(action);
            }
            qDebug() << "[composeReady] dispatching" << actions.size() << "create_midi_track actions";
            engine->dispatchActions(actions);
        }, Qt::QueuedConnection);

    // Compose agent — "fill" mode: import MIDI into active piano roll clip
    QObject::connect(aiBackend, &AIBackend::composeFillReady,
        engine, [engine](const QString& midiPath) {
            engine->importMidiToActiveClip(midiPath);
        }, Qt::QueuedConnection);

    // ── Wire backend logs → Console tab ──────────────────────────────────────
    QObject::connect(launcher, &BackendLauncher::logLine,
                     aiBackend, [aiBackend](const QString& line) { aiBackend->appendLog(line); });
    QObject::connect(launcher, &BackendLauncher::failed, aiBackend,
        [aiBackend](const QString& r) { aiBackend->appendLog("FAILED: " + r); });
    QObject::connect(aiClient, &AIClient::connected, aiBackend,
        [aiBackend]() { aiBackend->appendLog("AIClient: CONNECTED"); });
    QObject::connect(aiClient, &AIClient::disconnected, aiBackend,
        [aiBackend]() { aiBackend->appendLog("AIClient: DISCONNECTED"); });
    QObject::connect(aiClient, &AIClient::error, aiBackend,
        [aiBackend](const QString& e) { aiBackend->appendLog("AIClient ERROR: " + e); });

    // ── Startup diagnostics → Console tab ────────────────────────────────────
    QObject::connect(launcher, &BackendLauncher::ready, aiBackend, [aiBackend, aiClient]() {
        aiBackend->appendLog("=== Wavy Labs Startup Diagnostics ===");
        aiClient->callAsync("startup_check", QVariantMap{},
            [aiBackend](bool ok, const QVariantMap& result) {
                if (!ok) {
                    aiBackend->appendLog("[ERR] Startup check RPC failed");
                    return;
                }
                const auto checks = result.value("checks").toList();
                for (const QVariant& cv : checks) {
                    const QVariantMap c = cv.toMap();
                    const QString status = c.value("status").toString();
                    const QString name   = c.value("name").toString();
                    const QString msg    = c.value("message").toString();
                    QString prefix = (status == "ok")   ? "[OK]   " :
                                     (status == "warn")  ? "[WARN] " : "[ERR]  ";
                    aiBackend->appendLog(prefix + name + ": " + msg);
                }
                aiBackend->appendLog("=== Diagnostics Complete ===");
            }, 30000);
    });

    // ── Inject Wavy menu items into LMMS Edit menu ─────────────────────────
    // MUST happen before adoptLmmsContent() moves the menu bar to WavyShell.
    for (QAction* menuAction : lmmsWin->menuBar()->actions()) {
        if (menuAction->text().contains("Edit", Qt::CaseInsensitive)) {
            QMenu* editMenu = menuAction->menu();
            editMenu->addSeparator();
            QMenu* themeMenu = editMenu->addMenu("App theme");
            const QString current = Wavy::ThemeManager::currentTheme();
            auto* themeGroup = new QActionGroup(lmmsWin);
            themeGroup->setExclusive(true);

            auto* defaultAction = themeMenu->addAction("Crimson");
            defaultAction->setCheckable(true);
            defaultAction->setChecked(current == "wavy-crimson");
            defaultAction->setData(QString("wavy-crimson"));
            themeGroup->addAction(defaultAction);

            auto* silverAction = themeMenu->addAction("Silver");
            silverAction->setCheckable(true);
            silverAction->setChecked(current == "wavy-silver");
            silverAction->setData(QString("wavy-silver"));
            themeGroup->addAction(silverAction);

            auto* rubyAction = themeMenu->addAction("Ruby");
            rubyAction->setCheckable(true);
            rubyAction->setChecked(current == "wavy-ruby");
            rubyAction->setData(QString("wavy-ruby"));
            themeGroup->addAction(rubyAction);

            auto* midnightAction = themeMenu->addAction("Midnight");
            midnightAction->setCheckable(true);
            midnightAction->setChecked(current == "wavy-midnight");
            midnightAction->setData(QString("wavy-midnight"));
            themeGroup->addAction(midnightAction);

            auto* orangesicleAction = themeMenu->addAction("Orangesicle");
            orangesicleAction->setCheckable(true);
            orangesicleAction->setChecked(current == "wavy-orangesicle");
            orangesicleAction->setData(QString("wavy-orangesicle"));
            themeGroup->addAction(orangesicleAction);

            auto* sunsetAction = themeMenu->addAction("Sunset");
            sunsetAction->setCheckable(true);
            sunsetAction->setChecked(current == "wavy-sunset");
            sunsetAction->setData(QString("wavy-sunset"));
            themeGroup->addAction(sunsetAction);

            QObject::connect(themeGroup, &QActionGroup::triggered, lmmsWin, [](QAction* action) {
                const QString id = action->data().toString();
                if (!id.isEmpty()) {
                    Wavy::ThemeManager::setTheme(id);
                    action->setChecked(true);
                }
            });
            editMenu->addSeparator();
            auto* acctAction = editMenu->addAction("Settings");
            QObject::connect(acctAction, &QAction::triggered, lmmsWin, [lmmsWin]() {
                QWidget* parent = lmmsWin->isVisible() ? static_cast<QWidget*>(lmmsWin)
                                                        : qApp->activeWindow();
                auto* dlg = new ApiKeySettings(parent);
                dlg->setAttribute(Qt::WA_DeleteOnClose);
                dlg->exec();
            });
            break;
        }
    }

    // ── Create WavyShell — replaces LMMS MDI with single-window layout ───
    auto* wavyShell = new WavyShell(engine);
    wavyShell->adoptLmmsContent(lmmsWin);
    wavyShell->setAIPanel(quickWidget);
    wavyShell->addAINavButtons(aiBackend);

    // Start with an empty project (initialises the engine; dashboard covers the workspace)
    engine->createNewProject();

    // ── Dashboard landing page ─────────────────────────────────────────────
    auto* dashWidget = new QQuickWidget;
    dashWidget->setObjectName("WavyDashboard");
    dashWidget->setResizeMode(QQuickWidget::SizeRootObjectToView);
    dashWidget->rootContext()->setContextProperty("backend", aiBackend);
    dashWidget->rootContext()->setContextProperty("theme",
        Wavy::ThemeManager::themeObject());
    dashWidget->setSource(QUrl("qrc:/wavy/qml/DashboardPage.qml"));
    qDebug() << "[dashboard] status after setSource:" << dashWidget->status();
    for (const auto& e : dashWidget->errors()) qDebug() << "[dashboard] error:" << e.toString();
    wavyShell->setDashboard(dashWidget);   // index 1 in workStack, shown immediately

    // Wire Import Audio from dashboard → Song tab
    QObject::connect(aiBackend, &AIBackend::switchToEditorRequested,
        wavyShell, [wavyShell]() { wavyShell->activateEditorTab(1); });

    // Wire project open from dashboard → LMMS
    QObject::connect(aiBackend, &AIBackend::projectOpenRequested,
        wavyShell, [wavyShell, engine](const QString& path) {
            if (path.isEmpty()) {
                engine->createNewProject();
            } else {
                lmms::Engine::getSong()->loadProject(path);
            }
            // Switch to Song tab after project loads
            QTimer::singleShot(200, wavyShell, [wavyShell]() {
                wavyShell->activateEditorTab(1);  // Song = 1
            });
        });

    // ── Show WavyShell ───────────────────────────────────────────────────────
    wavyShell->show();
    wavyShell->showMaximized();

    // ── Boot sound ───────────────────────────────────────────────────────────
#ifdef _WIN32
    {
        QFile sf(QStringLiteral(":/wavy/sounds/startup.wav"));
        if (sf.open(QIODevice::ReadOnly)) {
            // Keep data alive until PlaySound returns (ASYNC, so use static)
            static QByteArray wavData = sf.readAll();
            sf.close();
            ::PlaySoundA(wavData.constData(), nullptr,
                         SND_MEMORY | SND_ASYNC | SND_NODEFAULT);
        }
    }
#endif

    // ── First-run onboarding ──────────────────────────────────────────────────
    if (OnboardingWizard::shouldShow()) {
        QTimer::singleShot(600, wavyShell, [wavyShell, modelMgr]() {
            auto* wiz = new OnboardingWizard(modelMgr, wavyShell);
            wiz->setAttribute(Qt::WA_DeleteOnClose);
            wiz->exec();
        });
    }

    return app.exec();

#else
    // ── Standalone dev harness (WAVY_BUILD_LMMS_CORE=OFF) ────────────────────
    QApplication app(argc, argv);
    app.setApplicationName("Wavy Labs");
    app.setApplicationVersion(WAVY_VERSION);
    app.setOrganizationName("Wavy Labs");
    app.setOrganizationDomain("wavylab.net");

    QCoreApplication::addLibraryPath(QCoreApplication::applicationDirPath());

    applyTheme(app);
    ensureDataDirs();

    QPixmap splash(":/icons/splash.png");
    QSplashScreen* splashScreen = nullptr;
    if (!splash.isNull()) {
        splashScreen = new QSplashScreen(splash);
        splashScreen->show();
        splashScreen->showMessage("Starting Wavy Labs…",
                                  Qt::AlignBottom | Qt::AlignHCenter,
                                  QColor("#7c5cbf"));
        app.processEvents();
    }

    ModelManager*    modelMgr = new ModelManager();
    AIClient*        aiClient = AIClient::instance();
    modelMgr->setClient(aiClient);   // so refreshStatus() can query the backend
    BackendLauncher* launcher = new BackendLauncher(aiClient, &app);

    QObject::connect(launcher, &BackendLauncher::logLine,
                     &app, [](const QString& line) { qDebug().noquote() << line; });

    if (splashScreen) {
        QObject::connect(launcher, &BackendLauncher::logLine,
                         splashScreen, [splashScreen](const QString& line) {
                             splashScreen->showMessage(
                                 line.left(80),
                                 Qt::AlignBottom | Qt::AlignHCenter,
                                 QColor("#4fc3f7"));
                         });
    }

    // ── Create EngineAPI (stub) ──────────────────────────────────────────────
    auto* engine = new StubEngine(&app);

    // ── Build harness window ──────────────────────────────────────────────────
    //
    //  ┌──────────────────────────────────────────────────────┐
    //  │  Wavy Labs — Dev Harness                             │
    //  ├────────────────────────────┬─────────────────────────┤
    //  │  [Gen][Vocal][SFX][Mix]    │  Song Tracks            │
    //  │  [Tools][Code][Prompt]     │  🎵 AI Generated…       │
    //  │  [Console]                 │  🎚 vocals              │
    //  └────────────────────────────┴─────────────────────────┘

    AIPanel* panel = new AIPanel(aiClient, modelMgr);

    QMainWindow* window = new QMainWindow();
    window->setWindowTitle("Wavy Labs — Dev Harness");
    window->resize(1100, 660);

    // AIPanel hosts all tabs (Generate, Vocal, Mix/Master, Code-to-Music)
    window->setCentralWidget(panel);

    // Right dock: Song Tracks list
    auto* trackDock   = new QDockWidget("Song Tracks", window);
    auto* dockContent = new QWidget(trackDock);
    auto* dockLayout  = new QVBoxLayout(dockContent);
    dockLayout->setContentsMargins(4, 4, 4, 4);
    dockLayout->setSpacing(4);

    auto* trackList = new QListWidget(dockContent);
    trackList->setAlternatingRowColors(true);
    dockLayout->addWidget(trackList);
    dockContent->setLayout(dockLayout);

    trackDock->setWidget(dockContent);
    trackDock->setMinimumWidth(260);
    window->addDockWidget(Qt::RightDockWidgetArea, trackDock);

    // DAW context helper — builds a snapshot of track names + tempo for the LLM.
    auto updateDawContext = [engine, panel]() {
        QVariantList trackNames;
        for (const auto& n : engine->trackNames())
            trackNames.append(n);
        QVariantMap ctx;
        ctx["track_count"] = engine->trackCount();
        ctx["tracks"]      = trackNames;
        ctx["tempo"]       = engine->tempo();
        panel->setPromptContext(ctx);
    };

    // Sync track list widget from EngineAPI
    auto syncTrackList = [engine, trackList, updateDawContext]() {
        trackList->clear();
        for (const auto& name : engine->trackNames())
            trackList->addItem(name);
        updateDawContext();
    };

    QObject::connect(engine, &EngineAPI::trackListChanged, &app, syncTrackList);

    // audioReady → insert via EngineAPI
    QObject::connect(panel, &AIPanel::audioReady,
        engine, [engine](const QString& name, const QString& path, double) {
            engine->insertAudioTrack(name, path, QColor("#4fc3f7"));
        });

    // stemsReady → insert each via EngineAPI
    QObject::connect(panel, &AIPanel::stemsReady,
        engine, [engine](const QStringList& paths, const QStringList& names) {
            engine->insertStemTracks(paths, names);
        });

    // codeTracksReady → insert Code-to-Music audio tracks via EngineAPI
    QObject::connect(panel, &AIPanel::codeTracksReady,
        engine, [engine](const QStringList& paths, const QStringList& names) {
            engine->insertStemTracks(paths, names);
        });

    // actionsReady → dispatch via EngineAPI
    QObject::connect(panel, &AIPanel::actionsReady,
        engine, [engine](const QVariantList& actions) {
            engine->dispatchActions(actions);
        });

    // ── Show window (called once backend is ready or failed to start) ─────────
    auto showWindow = [splashScreen, window, modelMgr, updateDawContext]() {
        if (splashScreen) {
            splashScreen->finish(window);
            delete splashScreen;
        }

        // Always show the main window first so Qt doesn't quit when the wizard
        // closes (quitOnLastWindowClosed would fire if wizard were the only window).
        window->show();

        // First-run onboarding wizard — shown on top of the main window.
        // Wizard calls markCompleted() on accept; if rejected (cancel) the
        // wizard will appear again on next launch so the user can finish setup.
        if (OnboardingWizard::shouldShow()) {
            auto* wizard = new OnboardingWizard(modelMgr, window);
            wizard->show();
        }

        // ── License revalidation ──────────────────────────────────────────────
        // 1) Immediate background check if grace period is at or past expiry.
        auto runRevalidation = []() {
            QThread* t = QThread::create([]() {
                LicenseManager::instance()->revalidateWithServer();
            });
            QObject::connect(t, &QThread::finished, t, &QObject::deleteLater);
            t->start();
        };

        if (LicenseManager::instance()->needsRevalidation())
            runRevalidation();

        // 2) Periodic revalidation every 12 hours while the app is running.
        //    This keeps the validated-at timestamp fresh so the 7-day grace
        //    period doesn't expire during long sessions.
        constexpr int TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;
        auto* revalTimer = new QTimer(window);
        revalTimer->setInterval(TWELVE_HOURS_MS);
        revalTimer->setSingleShot(false);
        QObject::connect(revalTimer, &QTimer::timeout, window, runRevalidation);
        revalTimer->start();
    };

    // Wire backend logs → Console tab
    QObject::connect(launcher, &BackendLauncher::logLine,
                     panel, &AIPanel::appendLog);
    QObject::connect(launcher, &BackendLauncher::failed, panel,
        [panel](const QString& r) { panel->appendLog("FAILED: " + r); });
    QObject::connect(aiClient, &AIClient::connected, panel,
        [panel]() { panel->appendLog("AIClient: CONNECTED"); });
    QObject::connect(aiClient, &AIClient::disconnected, panel,
        [panel]() { panel->appendLog("AIClient: DISCONNECTED"); });
    QObject::connect(aiClient, &AIClient::error, panel,
        [panel](const QString& e) { panel->appendLog("AIClient ERROR: " + e); });

    QObject::connect(launcher, &BackendLauncher::ready,  &app, showWindow);
    QObject::connect(launcher, &BackendLauncher::failed, &app,
                     [showWindow](const QString&) { showWindow(); });
    QObject::connect(&app, &QApplication::aboutToQuit,
                     launcher, &BackendLauncher::stop);

    launcher->start();

    return app.exec();
#endif
}
