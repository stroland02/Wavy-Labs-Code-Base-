#pragma once

#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QString>

class AIClient;

// ---------------------------------------------------------------------------
// BackendLauncher — manages the lifecycle of the wavy-ai Python server
// ---------------------------------------------------------------------------
// Locates python + server.py, spawns the process, then polls the ZMQ
// health endpoint until the backend is ready (or gives up after ~10 s).
//
// Path resolution order for server.py:
//   1. WAVY_BACKEND_PATH env var          (explicit override)
//   2. <exe_dir>/wavy-ai/server.py        (installed layout)
//   3. <exe_dir>/../wavy-ai/server.py     (dev build inside build/)
//   4. <exe_dir>/../../wavy-ai/server.py  (nested build dir)
//
// Python resolution order:
//   1. WAVY_PYTHON env var
//   2. <server_dir>/.venv/Scripts/python.exe  (Windows venv)
//   3. <server_dir>/.venv/bin/python3          (Unix venv)
//   4. python3 / python on PATH
// ---------------------------------------------------------------------------

class BackendLauncher : public QObject
{
    Q_OBJECT

public:
    enum class State { Idle, Starting, Ready, Failed };

    explicit BackendLauncher(AIClient* client, QObject* parent = nullptr);
    ~BackendLauncher() override;

    // Start the backend process and begin health-check polling.
    void start();

    // Gracefully terminate the backend process.
    void stop();

    State state() const { return m_state; }

Q_SIGNALS:
    void stateChanged(State state);

    // Forwarded stdout/stderr lines from server.py
    void logLine(const QString& line);

    // Emitted once when the backend responds to a health check.
    void ready();

    // Emitted when all retries are exhausted.
    void failed(const QString& reason);

private Q_SLOTS:
    void onRetryTimer();
    void onProcessError(QProcess::ProcessError err);
    void onProcessFinished(int exitCode, QProcess::ExitStatus status);
    void onStdout();
    void onStderr();

    void onClientConnected();
    void onClientError(const QString& msg);

private:
    QString findServerScript() const;
    QString findPython(const QString& serverDir) const;
    void    setState(State s);
    void    attemptConnect();
    void    continueStart();  // called on main thread after async ZMQ probe

    AIClient* m_client{nullptr};
    QProcess* m_process{nullptr};
    QTimer*   m_retryTimer{nullptr};

    int   m_attempts{0};
    State m_state{State::Idle};

    static constexpr int MAX_ATTEMPTS     = 20;   // 20 × 500 ms = 10 s
    static constexpr int RETRY_INTERVAL   = 500;  // ms
    static constexpr int INITIAL_DELAY_MS = 1200; // let server bind socket
};
