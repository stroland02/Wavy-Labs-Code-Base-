#include "AIClient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QThread>
#include <QThreadPool>
#include <QRunnable>
#include <QVariant>

#include <zmq.hpp>
#include <mutex>
#include <stdexcept>

// ---------------------------------------------------------------------------
// ZMQ pimpl
// ---------------------------------------------------------------------------

struct AIClient::Impl {
    zmq::context_t  ctx{1};
    // One REQ socket per thread; we serialise with m_socketMutex.
    zmq::socket_t   socket{ctx, zmq::socket_type::req};
    bool            socketOpen{false};
};

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

AIClient* AIClient::s_instance = nullptr;

AIClient* AIClient::instance()
{
    static std::once_flag flag;
    std::call_once(flag, []{ s_instance = new AIClient(); });
    return s_instance;
}

AIClient::AIClient(QObject* parent)
    : QObject(parent)
    , m_impl(std::make_unique<Impl>())
{}

AIClient::~AIClient()
{
    disconnectFromBackend();
}

// ---------------------------------------------------------------------------
// Connect
// ---------------------------------------------------------------------------

bool AIClient::connectToBackend(const QString& host, int port)
{
    // Already connected — nothing to do
    if (m_connected.loadAcquire())
        return true;

    QMutexLocker lock(&m_socketMutex);

    if (m_impl->socketOpen) {
        m_impl->socket.close();
        m_impl->socketOpen = false;
    }

    m_host = host;
    m_port = port;

    try {
        m_impl->socket = zmq::socket_t(m_impl->ctx, zmq::socket_type::req);
        m_impl->socket.set(zmq::sockopt::rcvtimeo, 5000);   // 5 s default
        m_impl->socket.set(zmq::sockopt::sndtimeo, 5000);
        m_impl->socket.set(zmq::sockopt::linger,   0);

        const std::string endpoint =
            "tcp://" + host.toStdString() + ":" + std::to_string(port);
        m_impl->socket.connect(endpoint);
        m_impl->socketOpen = true;
    } catch (const zmq::error_t& e) {
        emit error(QString("ZMQ connect failed: %1").arg(e.what()));
        return false;
    }

    // Fire health-check in background
    QThread* t = QThread::create([this]() {
        try {
            QVariantMap res = callSync("health", {}, 5000);
            if (res.contains("result")) {
                m_connected.storeRelease(1);
                emit connected();
            }
        } catch (...) {
            emit error("AI backend health check failed — is wavy-ai/server.py running?");
        }
    });
    t->start();
    connect(t, &QThread::finished, t, &QObject::deleteLater);

    return true;
}

void AIClient::disconnectFromBackend()
{
    QMutexLocker lock(&m_socketMutex);
    if (m_impl->socketOpen) {
        m_impl->socket.close();
        m_impl->socketOpen = false;
    }
    m_connected.storeRelease(0);
    emit disconnected();
}

// ---------------------------------------------------------------------------
// RPC helpers
// ---------------------------------------------------------------------------

QVariantMap AIClient::buildRequest(const QString& method,
                                   const QVariantMap& params, int id) const
{
    QVariantMap req;
    req["id"]     = id;
    req["method"] = method;
    req["params"] = params;
    return req;
}

QVariantMap AIClient::parseResponse(const QByteArray& data) const
{
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(data, &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject())
        throw std::runtime_error("Invalid JSON response: " +
                                 err.errorString().toStdString());
    return doc.object().toVariantMap();
}

// ---------------------------------------------------------------------------
// Synchronous call
// ---------------------------------------------------------------------------

QVariantMap AIClient::callSync(const QString& method,
                                const QVariantMap& params,
                                int timeoutMs)
{
    QMutexLocker lock(&m_socketMutex);

    if (!m_impl->socketOpen)
        throw std::runtime_error("Not connected to AI backend.");

    const int id = m_nextId.fetchAndAddOrdered(1);
    const QByteArray payload =
        QJsonDocument(QJsonObject::fromVariantMap(buildRequest(method, params, id)))
            .toJson(QJsonDocument::Compact);

    // Set per-call timeout
    m_impl->socket.set(zmq::sockopt::rcvtimeo, timeoutMs);
    m_impl->socket.set(zmq::sockopt::sndtimeo, timeoutMs);

    zmq::message_t msg(payload.data(), static_cast<size_t>(payload.size()));
    auto res_send = m_impl->socket.send(msg, zmq::send_flags::none);
    if (!res_send)
        throw std::runtime_error("ZMQ send failed.");

    zmq::message_t reply;
    auto res_recv = m_impl->socket.recv(reply, zmq::recv_flags::none);
    if (!res_recv) {
        // REQ socket is now in a broken state (sent but no reply).
        // We must recreate it so future calls can work.
        const std::string endpoint =
            "tcp://" + m_host.toStdString() + ":" + std::to_string(m_port);
        m_impl->socket.close();
        m_impl->socket = zmq::socket_t(m_impl->ctx, zmq::socket_type::req);
        m_impl->socket.set(zmq::sockopt::rcvtimeo, 5000);
        m_impl->socket.set(zmq::sockopt::sndtimeo, 5000);
        m_impl->socket.set(zmq::sockopt::linger,   0);
        m_impl->socket.connect(endpoint);
        throw std::runtime_error("ZMQ recv timed out (backend unreachable?).");
    }

    const QByteArray raw(static_cast<const char*>(reply.data()),
                         static_cast<int>(reply.size()));
    QVariantMap response = parseResponse(raw);

    if (response.contains("error"))
        throw std::runtime_error(response["error"].toString().toStdString());

    return response;
}

// ---------------------------------------------------------------------------
// Asynchronous call
// ---------------------------------------------------------------------------

// Helper QRunnable for thread pool dispatch
class RpcTask : public QRunnable {
public:
    RpcTask(AIClient* client, const QString& method,
            const QVariantMap& params, AIClient::ResponseCallback cb, int timeoutMs)
        : m_client(client), m_method(method), m_params(params)
        , m_callback(std::move(cb)), m_timeoutMs(timeoutMs) {}

    void run() override {
        try {
            QVariantMap response = m_client->callSync(m_method, m_params, m_timeoutMs);
            m_callback(true, response["result"].toMap());
        } catch (const std::exception& e) {
            m_callback(false, {{"error", QString::fromUtf8(e.what())}});
        }
    }
private:
    AIClient* m_client;
    QString m_method;
    QVariantMap m_params;
    AIClient::ResponseCallback m_callback;
    int m_timeoutMs;
};

void AIClient::callAsync(const QString& method,
                          const QVariantMap& params,
                          ResponseCallback callback,
                          int timeoutMs)
{
    auto* task = new RpcTask(this, method, params, std::move(callback), timeoutMs);
    task->setAutoDelete(true);
    QThreadPool::globalInstance()->start(task);
}

// ---------------------------------------------------------------------------
// Convenience wrappers
// ---------------------------------------------------------------------------

void AIClient::generateMusic(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("generate_music", params, std::move(cb), 600'000);  // 10 min — ACE-Step CPU
}

void AIClient::splitStems(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("split_stems", params, std::move(cb), 600'000);  // 10 min — Demucs CPU
}

void AIClient::analyzeTrack(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("mix_analyze", params, std::move(cb), 60'000);
}

void AIClient::masterAudio(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("master_audio", params, std::move(cb), 60'000);
}

void AIClient::promptCommand(const QString& prompt,
                              const QVariantMap& ctx,
                              const QVariantList& history,
                              ResponseCallback cb)
{
    QVariantMap p;
    p["prompt"]      = prompt;
    p["daw_context"] = ctx;
    if (!history.isEmpty())
        p["history"] = history;
    callAsync("prompt_command", p, std::move(cb), 60'000);
}

void AIClient::codeToMusic(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("code_to_music", params, std::move(cb), 120'000);
}

// ---------------------------------------------------------------------------
// ElevenLabs wrappers
// ---------------------------------------------------------------------------

void AIClient::elevenLabsTTS(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_tts", params, std::move(cb), 60'000);
}

void AIClient::elevenLabsVoiceClone(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_voice_clone", params, std::move(cb), 120'000);
}

void AIClient::elevenLabsSTS(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_speech_to_speech", params, std::move(cb), 60'000);
}

void AIClient::elevenLabsSFX(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_sfx", params, std::move(cb), 60'000);
}

void AIClient::elevenLabsVoiceIsolate(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_voice_isolate", params, std::move(cb), 120'000);
}

void AIClient::elevenLabsTranscribe(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_transcribe", params, std::move(cb), 120'000);
}

void AIClient::elevenLabsForcedAlign(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_forced_align", params, std::move(cb), 120'000);
}

void AIClient::elevenLabsDub(const QVariantMap& params, ResponseCallback cb)
{
    callAsync("elevenlabs_dub", params, std::move(cb), 600'000);  // up to 10 min
}

void AIClient::elevenLabsListVoices(ResponseCallback cb)
{
    callAsync("elevenlabs_list_voices", {}, std::move(cb), 15'000);
}

// ---------------------------------------------------------------------------
// Suno-inspired feature wrappers
// ---------------------------------------------------------------------------

void AIClient::generateStem   (const QVariantMap& p, ResponseCallback cb) { callAsync("generate_stem",   p, std::move(cb), 90'000);  }
void AIClient::replaceSection (const QVariantMap& p, ResponseCallback cb) { callAsync("replace_section", p, std::move(cb), 120'000); }
void AIClient::audioToMidi    (const QVariantMap& p, ResponseCallback cb) { callAsync("audio_to_midi",   p, std::move(cb), 60'000);  }
void AIClient::extendMusic    (const QVariantMap& p, ResponseCallback cb) { callAsync("extend_music",    p, std::move(cb), 120'000); }
void AIClient::promptToMidi   (const QVariantMap& p, ResponseCallback cb) { callAsync("prompt_to_midi",  p, std::move(cb), 30'000);  }
void AIClient::savePersona    (const QVariantMap& p, ResponseCallback cb) { callAsync("save_persona",    p, std::move(cb), 5'000);   }
void AIClient::loadPersonas   (ResponseCallback cb)                        { callAsync("load_personas",   {}, std::move(cb), 5'000);  }

void AIClient::composeArrangement(const QVariantMap& p, ResponseCallback cb, int timeoutMs)
{
    callAsync("compose", p, std::move(cb), timeoutMs);
}

// Chat widget feature wrappers
void AIClient::chordSuggestions(const QVariantMap& p, ResponseCallback cb)
{ callAsync("chord_suggestions",   p, std::move(cb), 30'000); }

void AIClient::beatBuilder(const QVariantMap& p, ResponseCallback cb)
{ callAsync("beat_builder",        p, std::move(cb), 30'000); }

void AIClient::regenerateBar(const QVariantMap& p, ResponseCallback cb, int timeoutMs)
{ callAsync("regenerate_bar",      p, std::move(cb), timeoutMs); }

void AIClient::setSessionContext(const QVariantMap& p, ResponseCallback cb)
{ callAsync("set_session_context", p, std::move(cb), 5'000); }

void AIClient::extractStems(const QVariantMap& p, ResponseCallback cb, int timeoutMs)
{ callAsync("elevenlabs_music_stems", p, std::move(cb), timeoutMs); }

void AIClient::getInstrumentChoices(ResponseCallback cb)
{ callAsync("get_instrument_choices", {}, std::move(cb), 10'000); }

void AIClient::getBitmidiInspirations(const QString& genre, ResponseCallback cb)
{ callAsync("get_bitmidi_inspirations", {{"genre", genre}}, std::move(cb), 15'000); }

void AIClient::databaseTips(const QString& dbName, ResponseCallback cb)
{ callAsync("database_tips", {{"db", dbName}}, std::move(cb), 30'000); }

void AIClient::browseDataset(const QString& db, const QString& query, int offset, ResponseCallback cb)
{ callAsync("browse_dataset",
    {{"db", db}, {"query", query}, {"offset", offset}},
    std::move(cb), 60'000); }   // 60 s — first browse may need to fetch metadata

void AIClient::downloadLibraryFile(const QString& db, const QString& fileId,
                                   const QString& plugin, ResponseCallback cb)
{ callAsync("download_library_file",
    {{"db", db}, {"file_id", fileId}, {"plugin", plugin}},
    std::move(cb), 30'000); }

void AIClient::midicapsLibraryStatus(ResponseCallback cb)
{ callAsync("midicaps_library_status", {}, std::move(cb), 5'000); }

void AIClient::startMidicapsDownload(ResponseCallback cb)
{ callAsync("start_midicaps_download", {}, std::move(cb), 5'000); }

void AIClient::testDatabases(ResponseCallback cb)
{ callAsync("test_databases", {}, std::move(cb), 120'000); }  // 2 min — ldrolez may need zip dl


void AIClient::chatGenerate(const QVariantMap& p, ResponseCallback cb, int timeoutMs)
{ callAsync("chat_generate", p, std::move(cb), timeoutMs); }

void AIClient::checkStatus(ResponseCallback cb)
{
    if (!m_connected.loadAcquire()) {
        cb(false, {{"error", QString("Not connected to AI backend.")}});
        return;
    }
    callAsync("health", {}, [this, cb](bool ok, const QVariantMap& result) {
        if (!ok) {
            m_connected.storeRelease(0);
            emit disconnected();
        }
        cb(ok, result);
    }, 5000);
}

// ---------------------------------------------------------------------------
// (end of file)
