#pragma once

#include <QObject>
#include <QString>
#include <QVariantMap>
#include <QAtomicInt>
#include <QMutex>
#include <QThread>
#include <functional>
#include <memory>

// Forward-declare ZMQ types to avoid exposing <zmq.hpp> in every translation unit.
namespace zmq { class context_t; class socket_t; }

// ---------------------------------------------------------------------------
// AIClient — singleton ZeroMQ JSON-RPC client
// ---------------------------------------------------------------------------
// Thread-safety: sendRequest() is thread-safe (mutex-guarded).
// All signals are emitted on the AIClient's thread; connect via
// Qt::QueuedConnection if updating UI from another thread.
// ---------------------------------------------------------------------------

class AIClient : public QObject
{
    Q_OBJECT

public:
    // Singleton accessor
    static AIClient* instance();

    // Connect to the Python AI backend.
    // Returns true immediately; connection health is checked asynchronously.
    bool connectToBackend(const QString& host = "127.0.0.1", int port = 5555);

    // Disconnect and clean up.
    void disconnectFromBackend();

    bool isConnected() const { return m_connected.loadAcquire(); }

    // ---------------------------------------------------------------------------
    // Synchronous (blocking) RPC call — use only from non-UI threads.
    // Returns parsed response on success; throws std::runtime_error on failure.
    // ---------------------------------------------------------------------------
    QVariantMap callSync(const QString& method,
                         const QVariantMap& params = {},
                         int timeoutMs = 30'000);

    // ---------------------------------------------------------------------------
    // Asynchronous RPC call — non-blocking, result delivered via callback.
    // The callback is invoked from a worker thread.
    // ---------------------------------------------------------------------------
    using ResponseCallback = std::function<void(bool ok, const QVariantMap& result)>;

    void callAsync(const QString& method,
                   const QVariantMap& params,
                   ResponseCallback callback,
                   int timeoutMs = 60'000);

    // ---------------------------------------------------------------------------
    // Convenience wrappers
    // ---------------------------------------------------------------------------
    void generateMusic(const QVariantMap& params, ResponseCallback cb);
    void splitStems   (const QVariantMap& params, ResponseCallback cb);
    void analyzeTrack (const QVariantMap& params, ResponseCallback cb);
    void masterAudio  (const QVariantMap& params, ResponseCallback cb);
    void promptCommand(const QString& prompt, const QVariantMap& ctx,
                       const QVariantList& history, ResponseCallback cb);
    void codeToMusic  (const QVariantMap& params, ResponseCallback cb);

    // ElevenLabs wrappers
    void elevenLabsTTS        (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsVoiceClone (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsSTS        (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsSFX        (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsVoiceIsolate(const QVariantMap& params, ResponseCallback cb);
    void elevenLabsTranscribe (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsForcedAlign(const QVariantMap& params, ResponseCallback cb);
    void elevenLabsDub        (const QVariantMap& params, ResponseCallback cb);
    void elevenLabsListVoices (ResponseCallback cb);

    // Suno-inspired feature wrappers
    void generateStem   (const QVariantMap& params, ResponseCallback cb);
    void replaceSection (const QVariantMap& params, ResponseCallback cb);
    void audioToMidi    (const QVariantMap& params, ResponseCallback cb);
    void extendMusic    (const QVariantMap& params, ResponseCallback cb);
    void promptToMidi   (const QVariantMap& params, ResponseCallback cb);
    void savePersona    (const QVariantMap& params, ResponseCallback cb);
    void loadPersonas   (ResponseCallback cb);

    // Compose agent — multi-track arrangement generation
    void composeArrangement(const QVariantMap& params, ResponseCallback cb,
                            int timeoutMs = 120'000);

    // Chat generation — adaptive audio or MIDI routing
    void chatGenerate(const QVariantMap& params, ResponseCallback cb,
                      int timeoutMs = 120'000);

    // Chat widget features
    void chordSuggestions  (const QVariantMap& params, ResponseCallback cb);
    void beatBuilder       (const QVariantMap& params, ResponseCallback cb);
    void regenerateBar     (const QVariantMap& params, ResponseCallback cb,
                            int timeoutMs = 60'000);
    void setSessionContext   (const QVariantMap& params, ResponseCallback cb);
    void extractStems        (const QVariantMap& params, ResponseCallback cb,
                              int timeoutMs = 120'000);
    void getInstrumentChoices(ResponseCallback cb);
    void getBitmidiInspirations(const QString& genre, ResponseCallback cb);
    void databaseTips(const QString& dbName, ResponseCallback cb);
    void browseDataset(const QString& db, const QString& query, int offset, ResponseCallback cb);
    void downloadLibraryFile(const QString& db, const QString& fileId,
                             const QString& plugin, ResponseCallback cb);
    void midicapsLibraryStatus(ResponseCallback cb);
    void startMidicapsDownload(ResponseCallback cb);
    void testDatabases(ResponseCallback cb);

    // Ping backend and update connection state; callback receives (ok, result).
    // If currently disconnected, callback is invoked with ok=false (no reconnect).
    void checkStatus(ResponseCallback cb);

Q_SIGNALS:
    void connected();
    void disconnected();
    void error(const QString& message);

private:
    explicit AIClient(QObject* parent = nullptr);
    ~AIClient() override;

    static AIClient* s_instance;

    QString  m_host;
    int      m_port{5555};
    QAtomicInt m_connected{0};
    QAtomicInt m_nextId{1};
    QMutex   m_socketMutex;

    // ZMQ context / socket (pimpl to isolate the header)
    struct Impl;
    std::unique_ptr<Impl> m_impl;

    QVariantMap buildRequest(const QString& method,
                             const QVariantMap& params, int id) const;
    QVariantMap parseResponse(const QByteArray& data) const;
};
