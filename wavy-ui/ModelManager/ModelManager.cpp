#include "ModelManager.h"
#include "ModelDownloader.h"
#include "../IPC/AIClient.h"

ModelManager::ModelManager(QObject* parent)
    : QObject(parent)
    , m_downloader(new ModelDownloader(this))
{
    initModelCatalog();

    connect(m_downloader, &ModelDownloader::progress, this,
            &ModelManager::downloadProgress);
    connect(m_downloader, &ModelDownloader::finished, this, [this](const QString& name, bool ok) {
        emit downloadFinished(name, ok);
        if (ok) {
            for (auto& m : m_models)
                if (m.name == name) { m.downloaded = true; break; }
            emit modelStatusChanged();
            if (allRequiredModelsReady())
                emit allModelsReady();
        }
    });
}

void ModelManager::setClient(AIClient* client)
{
    m_client = client;
}

void ModelManager::initModelCatalog()
{
    // Positional order matches ModelInfo field order:
    //   name, displayName, huggingFaceRepo, vramGb, required,
    //   downloaded, loaded, localPath,
    //   isCloudApi, apiKeyEnvVar, apiKeyConfigured,
    //   recommended, diskSizeGb
    // (version and remoteVersion default to "")

    m_models = {
        // ── Cloud API models (required — ElevenLabs + Anthropic) ────────────
        { "anthropic_claude",   "Claude (Anthropic — Commands)",       "", 0, false,
          false, false, "",  true, "ANTHROPIC_API_KEY",  false, true,  0.0 },

        { "elevenlabs_tts",     "ElevenLabs TTS (Cloud)",              "", 0, false,
          false, false, "",  true, "ELEVENLABS_API_KEY", false, true,  0.0 },

        { "elevenlabs_music",   "ElevenLabs Music (Cloud)",            "", 0, false,
          false, false, "",  true, "ELEVENLABS_API_KEY", false, true,  0.0 },

        { "elevenlabs_sfx",     "ElevenLabs SFX (Cloud)",              "", 0, false,
          false, false, "",  true, "ELEVENLABS_API_KEY", false, true,  0.0 },

        { "elevenlabs_scribe",  "ElevenLabs Scribe STT (Cloud)",       "", 0, false,
          false, false, "",  true, "ELEVENLABS_API_KEY", false, false, 0.0 },

        { "elevenlabs_dubbing", "ElevenLabs Dubbing (Cloud)",          "", 0, false,
          false, false, "",  true, "ELEVENLABS_API_KEY", false, false, 0.0 },

        // ── Local models (all optional) ─────────────────────────────────────
        { "demucs",       "Demucs v4 (Stem Split)", "facebook/demucs",                    0.5, true,
          false, false, "",  false, "", false, true,  0.4 },

        { "mixer",        "AI Mixer/Mastering (Built-in)", "(built-in)",                  0.0, true,
          true,  false, "",  false, "", false, false, 0.0 },

        { "prompt_cmd",   "Mistral 7B (Optional Fallback)", "mistralai/Mistral-7B-Instruct-v0.3", 8.0, false,
          false, false, "",  false, "", false, false, 4.0 },

        { "code_to_music","Code-to-Music",           "(built-in)",                         0.0, true,
          true,  false, "",  false, "", false, false, 0.0 },
    };

    populateApiKeyStatus();
}

void ModelManager::populateApiKeyStatus()
{
    for (auto& m : m_models) {
        if (!m.isCloudApi || m.apiKeyEnvVar.isEmpty()) continue;
        m.apiKeyConfigured = !qEnvironmentVariable(m.apiKeyEnvVar.toUtf8()).isEmpty();
    }
}

void ModelManager::refreshStatus()
{
    if (!m_client || !m_client->isConnected()) return;

    // Query health to detect cloud provider and signal readiness.
    m_client->callAsync("health", {},
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onHealthRefreshed(ok, result);
            }, Qt::QueuedConnection);
        });

    m_client->callAsync("list_models", {},
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onStatusRefreshed(ok, result);
            }, Qt::QueuedConnection);
        });
}

void ModelManager::onStatusRefreshed(bool ok, const QVariantMap& result)
{
    if (!ok) return;
    const QVariantList serverModels = result.value("models").toList();
    for (const auto& sm : serverModels) {
        const QVariantMap m  = sm.toMap();
        const QString name   = m.value("name").toString();
        const bool loaded    = m.value("loaded").toBool();
        const double diskGb  = m.value("disk_size_gb").toDouble();
        const QString ver    = m.value("version").toString();
        for (auto& local : m_models) {
            if (local.name == name) {
                local.loaded = loaded;
                if (diskGb > 0) {
                    local.diskSizeGb = diskGb;
                    local.downloaded = true;   // backend reports size → model is on disk
                }
                if (loaded) local.downloaded = true;  // loaded implies downloaded
                if (!ver.isEmpty()) local.version = ver;
                break;
            }
        }
    }
    emit modelStatusChanged();
}

void ModelManager::downloadRequiredModels()
{
    // Cloud-first: no local model downloads required on first run.
    // Demucs is loaded lazily by the Python backend on first stem-split call.
}

void ModelManager::downloadModel(const QString& name)
{
    for (const auto& m : m_models) {
        if (m.name == name && !m.isCloudApi && !m.huggingFaceRepo.isEmpty()) {
            m_downloader->enqueue(m.name, m.huggingFaceRepo);
            return;
        }
    }
}

void ModelManager::downloadRecommendedModels()
{
    for (const auto& m : m_models)
        if (m.recommended && !m.isCloudApi && !m.downloaded)
            m_downloader->enqueue(m.name, m.huggingFaceRepo);
}

void ModelManager::uninstallModel(const QString& name)
{
    if (!m_client) return;
    QVariantMap params;
    params["name"] = name;
    m_client->callAsync("delete_model", params, [this, name](bool ok, const QVariantMap&) {
        QMetaObject::invokeMethod(this, [this, name, ok]() {
            if (!ok) return;
            for (auto& m : m_models)
                if (m.name == name) { m.downloaded = false; m.loaded = false; break; }
            emit modelStatusChanged();
        }, Qt::QueuedConnection);
    });
}

bool ModelManager::allRequiredModelsReady() const
{
    // Cloud backend is ready as soon as the health check succeeds.
    return m_healthOk;
}

void ModelManager::onHealthRefreshed(bool ok, const QVariantMap& result)
{
    if (!ok) return;
    m_healthOk = true;
    m_cloudProvider = result.value("cloud_provider", "elevenlabs").toString();

    // Mark required entries (demucs, mixer, code_to_music) as ready.
    for (auto& m : m_models)
        if (m.required)
            m.downloaded = true;

    // Use API key status reported by the Python backend (which loads from .env)
    // rather than reading the C++ process env (which may not have the key yet).
    const bool elKey  = result.value("elevenlabs_api_key_configured", false).toBool();
    const bool anthKey = result.value("anthropic_api_key_configured", false).toBool();
    for (auto& m : m_models) {
        if (!m.isCloudApi) continue;
        if (m.apiKeyEnvVar == "ELEVENLABS_API_KEY")
            m.apiKeyConfigured = elKey;
        else if (m.apiKeyEnvVar == "ANTHROPIC_API_KEY")
            m.apiKeyConfigured = anthKey;
        else
            m.apiKeyConfigured = !qEnvironmentVariable(m.apiKeyEnvVar.toUtf8()).isEmpty();
    }

    emit modelStatusChanged();
    emit allModelsReady();
}
