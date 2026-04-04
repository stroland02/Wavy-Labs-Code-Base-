#pragma once
#include <QObject>
#include <QString>
#include <QVariantList>
#include <QVariantMap>

class ModelDownloader;
class AIClient;

// ---------------------------------------------------------------------------
// ModelManager — tracks model availability, triggers first-run downloads,
// and exposes model status to the UI.
// ---------------------------------------------------------------------------

struct ModelInfo {
    QString  name;
    QString  displayName;
    QString  huggingFaceRepo;
    double   vramGb;
    bool     required;      // downloaded on first run
    bool     downloaded{false};
    bool     loaded{false};
    QString  localPath;
    // Cloud vs local:
    bool     isCloudApi{false};       // true = API key connection, no download
    QString  apiKeyEnvVar;            // e.g. "HF_TOKEN", "GROQ_API_KEY"
    bool     apiKeyConfigured{false}; // set at runtime by populateApiKeyStatus()
    bool     recommended{false};      // show "Recommended" badge
    double   diskSizeGb{0.0};         // download size in GB
    QString  version;                 // installed version (empty if not downloaded)
    QString  remoteVersion;           // latest available (for update detection)
};

class ModelManager : public QObject
{
    Q_OBJECT
public:
    explicit ModelManager(QObject* parent = nullptr);

    void setClient(AIClient* client);

    // Returns all known models and their status.
    QList<ModelInfo> models() const { return m_models; }

    // Refreshes status from the Python backend.
    void refreshStatus();

    // Trigger download of all required models (called on first launch).
    void downloadRequiredModels();

    // Trigger download of a single model by name.
    void downloadModel(const QString& name);

    // Trigger download of all models flagged recommended=true (local only).
    void downloadRecommendedModels();

    // Remove a local model via RPC; marks downloaded=false on success.
    void uninstallModel(const QString& name);

    // Populate apiKeyConfigured flags from environment variables.
    void populateApiKeyStatus();

    bool allRequiredModelsReady() const;

    // Returns the cloud_provider string reported by the backend health check.
    QString cloudProvider() const { return m_cloudProvider; }

Q_SIGNALS:
    void modelStatusChanged();
    void downloadProgress(const QString& modelName, int percent);
    void downloadFinished(const QString& modelName, bool success);
    void allModelsReady();
    void updateAvailable(const QString& modelName);

private Q_SLOTS:
    void onStatusRefreshed(bool ok, const QVariantMap& result);
    void onHealthRefreshed(bool ok, const QVariantMap& result);

private:
    void initModelCatalog();

    AIClient*          m_client{nullptr};
    ModelDownloader*   m_downloader{nullptr};
    QList<ModelInfo>   m_models;
    bool               m_healthOk{false};
    QString            m_cloudProvider{"huggingface"};
};
