#pragma once
#include <QObject>
#include <QString>
#include <QQueue>
#include <QFile>
#include <QNetworkAccessManager>
#include <QNetworkReply>

// ---------------------------------------------------------------------------
// ModelDownloader — queued HTTP downloader for model files.
// Downloads from HuggingFace Hub using the standard repo/filename URL pattern.
// Verifies SHA-256 checksums when available.
// ---------------------------------------------------------------------------

struct DownloadJob {
    QString name;
    QString repoId;
    QString filename;
    QString sha256;      // empty = no checksum verification
    QString destPath;
};

class ModelDownloader : public QObject
{
    Q_OBJECT
public:
    explicit ModelDownloader(QObject* parent = nullptr);

    // Enqueue a model for download (one job per filename in the repo).
    void enqueue(const QString& name, const QString& huggingFaceRepo,
                 const QString& filename = "model.safetensors",
                 const QString& sha256   = "");

    bool isDownloading() const { return m_currentReply != nullptr; }

Q_SIGNALS:
    void progress(const QString& name, int percent);
    void finished(const QString& name, bool success);

private Q_SLOTS:
    void downloadNext();
    void onDownloadProgress(qint64 received, qint64 total);
    void onDownloadFinished();
    void onDownloadError(QNetworkReply::NetworkError err);

private:
    QString hfUrl(const QString& repoId, const QString& filename) const;
    bool    verifyChecksum(const QString& filePath, const QString& expected) const;

    QNetworkAccessManager* m_nam{nullptr};
    QNetworkReply*         m_currentReply{nullptr};
    QQueue<DownloadJob>    m_queue;
    DownloadJob            m_currentJob;
    QFile*                 m_outputFile{nullptr};
};
