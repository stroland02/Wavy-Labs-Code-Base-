#include "BackendLauncher.h"
#include "AIClient.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QProcessEnvironment>
#include <QSettings>
#include <QStandardPaths>
#include <QThread>
#include "../LicenseGate/LicenseManager.h"

#include <zmq.hpp>

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

BackendLauncher::BackendLauncher(AIClient* client, QObject* parent)
    : QObject(parent)
    , m_client(client)
{
    m_retryTimer = new QTimer(this);
    m_retryTimer->setInterval(RETRY_INTERVAL);
    m_retryTimer->setSingleShot(false);
    connect(m_retryTimer, &QTimer::timeout, this, &BackendLauncher::onRetryTimer);

    connect(m_client, &AIClient::connected, this, &BackendLauncher::onClientConnected);
    connect(m_client, &AIClient::error,     this, &BackendLauncher::onClientError);
}

BackendLauncher::~BackendLauncher()
{
    stop();
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

void BackendLauncher::setState(State s)
{
    if (m_state == s) return;
    m_state = s;
    emit stateChanged(s);
}

// ---------------------------------------------------------------------------
// Path resolution
// ---------------------------------------------------------------------------

QString BackendLauncher::findServerScript() const
{
    // 1. Explicit env override
    const QString envPath = QProcessEnvironment::systemEnvironment()
                                .value("WAVY_BACKEND_PATH");
    if (!envPath.isEmpty() && QFileInfo::exists(envPath))
        return envPath;

    // 2–4. Relative to the running executable
    const QString exeDir = QCoreApplication::applicationDirPath();
    const QStringList candidates = {
        exeDir + "/wavy-ai/server.py",
        exeDir + "/../wavy-ai/server.py",
        exeDir + "/../../wavy-ai/server.py",
    };
    for (const QString& c : candidates) {
        if (QFileInfo::exists(c))
            return QDir::cleanPath(c);
    }
    return {};
}

QString BackendLauncher::findPython(const QString& serverDir) const
{
    // 1. Explicit env override
    const QString envPy = QProcessEnvironment::systemEnvironment()
                              .value("WAVY_PYTHON");
    if (!envPy.isEmpty()) return envPy;

    // 2. Embedded Python — check both installer directory names
    const QString exeDir = QCoreApplication::applicationDirPath();
    for (const auto& dir : {"python-embed", "python"}) {
        const QString embedPy = exeDir + "/" + dir + "/python.exe";
        if (QFileInfo::exists(embedPy))
            return embedPy;
    }

    // 3–4. Virtual environment beside server.py
    const QStringList venvCandidates = {
        serverDir + "/.venv/Scripts/python.exe",  // Windows
        serverDir + "/.venv/bin/python3",          // Unix/macOS
        serverDir + "/.venv/bin/python",
    };
    for (const QString& v : venvCandidates) {
        if (QFileInfo::exists(v)) return v;
    }

    // 4. System Python on PATH
    for (const QString& name : {QStringLiteral("python3"), QStringLiteral("python")}) {
        const QString found = QStandardPaths::findExecutable(name);
        if (!found.isEmpty()) return found;
    }
    return {};
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

void BackendLauncher::start()
{
    if (m_state == State::Starting || m_state == State::Ready)
        return;

    setState(State::Starting);
    m_attempts = 0;

    // ── Quick check: is a backend already running? (dev mode / external) ──
    // Run the 1.5 s ZMQ probe on a background thread so the GUI (splash screen,
    // main window) can appear immediately without any visible freeze.
    QThread* probeThread = QThread::create([this]() {
        bool externalRunning = false;
        try {
            zmq::context_t tmpCtx(1);
            zmq::socket_t  tmpSock(tmpCtx, zmq::socket_type::req);
            tmpSock.set(zmq::sockopt::rcvtimeo, 1500);
            tmpSock.set(zmq::sockopt::sndtimeo, 1500);
            tmpSock.set(zmq::sockopt::linger,   0);
            tmpSock.connect(
                QString("tcp://127.0.0.1:%1").arg(WAVY_AI_PORT).toStdString());

            const QByteArray payload = R"({"id":0,"method":"health","params":{}})";
            zmq::message_t msg(payload.data(), static_cast<size_t>(payload.size()));
            tmpSock.send(msg, zmq::send_flags::none);

            zmq::message_t reply;
            auto res = tmpSock.recv(reply);
            if (res) {
                const auto data = QString::fromUtf8(
                    static_cast<const char*>(reply.data()), static_cast<int>(reply.size()));
                if (data.contains("\"result\""))
                    externalRunning = true;
            }
            tmpSock.close();
        } catch (...) {}

        // Marshal result back to the main thread
        QMetaObject::invokeMethod(this, [this, externalRunning]() {
            if (externalRunning) {
                // Defer signals so consumers have time to wire connections.
                QTimer::singleShot(0, this, [this]() {
                    emit logLine("[BackendLauncher] External backend already running.");
                    m_client->connectToBackend();
                    setState(State::Ready);
                    emit ready();
                });
            } else {
                continueStart();
            }
        }, Qt::QueuedConnection);
    });
    probeThread->setObjectName("wavy-zmq-probe");
    connect(probeThread, &QThread::finished, probeThread, &QObject::deleteLater);
    probeThread->start();
}

void BackendLauncher::continueStart()
{
    const QString script = findServerScript();
    if (script.isEmpty()) {
        const QString msg = "server.py not found. "
                            "Set WAVY_BACKEND_PATH or keep wavy-ai/ next to the executable.";
        emit logLine("[BackendLauncher] " + msg);
        emit failed(msg);
        setState(State::Failed);
        return;
    }

    const QString serverDir = QFileInfo(script).absolutePath();
    const QString python    = findPython(serverDir);
    if (python.isEmpty()) {
        const QString msg = "Python not found. "
                            "Install Python 3.10+ or set WAVY_PYTHON to the interpreter path.";
        emit logLine("[BackendLauncher] " + msg);
        emit failed(msg);
        setState(State::Failed);
        return;
    }

    emit logLine(QString("[BackendLauncher] Starting backend: %1 %2").arg(python, script));

    m_process = new QProcess(this);
    m_process->setWorkingDirectory(serverDir);
    m_process->setProcessChannelMode(QProcess::SeparateChannels);

    // Build process environment: start from system env, then inject saved API keys.
    // QSettings keys take precedence so users don't need to set env vars manually.
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    {
        QSettings ks("WavyLabs", "ApiKeys");
        const QList<QPair<QString,QString>> keyMap = {
            {"ANTHROPIC_API_KEY",  "anthropic"},
            {"GROQ_API_KEY",       "groq"},
            {"ELEVENLABS_API_KEY", "elevenlabs"},
            {"FREESOUND_API_KEY",  "freesound"},
        };
        for (const auto& [envName, settingsKey] : keyMap) {
            const QString val = LicenseManager::decryptApiKey(
                                    ks.value(settingsKey).toByteArray());
            if (!val.isEmpty())
                env.insert(envName, val);
        }
    }
    m_process->setProcessEnvironment(env);

    connect(m_process, &QProcess::readyReadStandardOutput,
            this, &BackendLauncher::onStdout);
    connect(m_process, &QProcess::readyReadStandardError,
            this, &BackendLauncher::onStderr);
    connect(m_process, &QProcess::errorOccurred,
            this, &BackendLauncher::onProcessError);
    connect(m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this, &BackendLauncher::onProcessFinished);

    m_process->start(python, {script, "--log-level", "DEBUG"});

    if (!m_process->waitForStarted(3000)) {
        const QString msg = "Failed to start backend process: " + m_process->errorString();
        emit logLine("[BackendLauncher] " + msg);
        emit failed(msg);
        setState(State::Failed);
        return;
    }

    // Give the server time to bind the ZMQ socket, then start polling
    QTimer::singleShot(INITIAL_DELAY_MS, this, [this]() {
        if (m_state == State::Starting)
            m_retryTimer->start();
    });
}

void BackendLauncher::stop()
{
    m_retryTimer->stop();

    if (m_process && m_process->state() != QProcess::NotRunning) {
        emit logLine("[BackendLauncher] Stopping backend process …");
        m_process->terminate();
        if (!m_process->waitForFinished(3000))
            m_process->kill();
    }
    setState(State::Idle);
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

void BackendLauncher::onRetryTimer()
{
    if (m_attempts >= MAX_ATTEMPTS) {
        m_retryTimer->stop();
        const QString msg = QString("Backend did not become ready after %1 attempts.")
                                .arg(MAX_ATTEMPTS);
        emit logLine("[BackendLauncher] " + msg);
        emit failed(msg);
        setState(State::Failed);
        return;
    }
    ++m_attempts;
    attemptConnect();
}

void BackendLauncher::attemptConnect()
{
    // connectToBackend() opens the ZMQ socket and fires a background health check.
    // onClientConnected() / onClientError() pick up the result.
    m_client->connectToBackend();
}

// ---------------------------------------------------------------------------
// AIClient callbacks
// ---------------------------------------------------------------------------

void BackendLauncher::onClientConnected()
{
    if (m_state != State::Starting) return;
    m_retryTimer->stop();
    setState(State::Ready);
    emit logLine("[BackendLauncher] Backend ready.");
    emit ready();
}

void BackendLauncher::onClientError(const QString& msg)
{
    if (m_state != State::Starting) return;
    emit logLine(QString("[BackendLauncher] Attempt %1/%2 failed: %3")
                     .arg(m_attempts).arg(MAX_ATTEMPTS).arg(msg));
    // retry timer will call attemptConnect() again on next tick
}

// ---------------------------------------------------------------------------
// Process I/O
// ---------------------------------------------------------------------------

void BackendLauncher::onStdout()
{
    if (!m_process) return;
    const QString text = QString::fromUtf8(m_process->readAllStandardOutput()).trimmed();
    if (!text.isEmpty())
        emit logLine("[server] " + text);
}

void BackendLauncher::onStderr()
{
    if (!m_process) return;
    const QString text = QString::fromUtf8(m_process->readAllStandardError()).trimmed();
    if (!text.isEmpty())
        emit logLine("[server] " + text);
}

// ---------------------------------------------------------------------------
// Process signals
// ---------------------------------------------------------------------------

void BackendLauncher::onProcessError(QProcess::ProcessError err)
{
    const QString msg = QString("Process error (%1): %2")
                            .arg(static_cast<int>(err))
                            .arg(m_process ? m_process->errorString() : QString());
    emit logLine("[BackendLauncher] " + msg);

    // Don't give up immediately — an external backend might be running.
    // Let onProcessFinished handle the fallback check.
}

void BackendLauncher::onProcessFinished(int exitCode, QProcess::ExitStatus status)
{
    const QString msg = QString("Backend process exited (code=%1, status=%2)")
                            .arg(exitCode)
                            .arg(status == QProcess::NormalExit ? "normal" : "crash");
    emit logLine("[BackendLauncher] " + msg);

    if (m_state == State::Ready) {
        // Process exited, but we may be connected to an external backend
        // (e.g. the spawned process failed because port was already in use).
        if (m_client->isConnected()) {
            emit logLine("[BackendLauncher] Process exited but backend is still reachable.");
            return;
        }
        m_client->disconnectFromBackend();
        setState(State::Failed);
    } else if (m_state == State::Starting) {
        // Process failed but an external backend might be running (dev mode).
        // Try connecting before giving up.
        emit logLine("[BackendLauncher] Process exited — checking for external backend …");
        attemptConnect();
    }
}
