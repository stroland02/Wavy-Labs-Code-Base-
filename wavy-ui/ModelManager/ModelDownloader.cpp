#include "ModelDownloader.h"

#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QNetworkRequest>
#include <QStandardPaths>
#include <QTimer>
#include <QUrl>

static QString modelBaseDir()
{
    return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation)
           + "/models";
}

ModelDownloader::ModelDownloader(QObject* parent)
    : QObject(parent)
    , m_nam(new QNetworkAccessManager(this))
{}

void ModelDownloader::enqueue(const QString& name,
                               const QString& huggingFaceRepo,
                               const QString& filename,
                               const QString& sha256)
{
    const QString dest = modelBaseDir() + "/" + name + "/" + filename;
    if (QFile::exists(dest)) {
        emit finished(name, true);
        return;
    }

    DownloadJob job;
    job.name     = name;
    job.repoId   = huggingFaceRepo;
    job.filename = filename;
    job.sha256   = sha256;
    job.destPath = dest;
    m_queue.enqueue(job);

    if (!isDownloading())
        QTimer::singleShot(0, this, &ModelDownloader::downloadNext);
}

void ModelDownloader::downloadNext()
{
    if (m_queue.isEmpty()) return;

    m_currentJob = m_queue.dequeue();
    QDir().mkpath(QFileInfo(m_currentJob.destPath).absolutePath());

    const QUrl url(hfUrl(m_currentJob.repoId, m_currentJob.filename));
    QNetworkRequest req(url);
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                     QNetworkRequest::NoLessSafeRedirectPolicy);

    m_outputFile = new QFile(m_currentJob.destPath + ".part", this);
    m_outputFile->open(QIODevice::WriteOnly);

    m_currentReply = m_nam->get(req);
    connect(m_currentReply, &QNetworkReply::downloadProgress,
            this, &ModelDownloader::onDownloadProgress);
    connect(m_currentReply, &QNetworkReply::finished,
            this, &ModelDownloader::onDownloadFinished);
    connect(m_currentReply, &QNetworkReply::errorOccurred,
            this, &ModelDownloader::onDownloadError);
    connect(m_currentReply, &QNetworkReply::readyRead, this, [this]() {
        if (m_outputFile)
            m_outputFile->write(m_currentReply->readAll());
    });
}

QString ModelDownloader::hfUrl(const QString& repoId,
                                 const QString& filename) const
{
    return QString("https://huggingface.co/%1/resolve/main/%2")
               .arg(repoId, filename);
}

void ModelDownloader::onDownloadProgress(qint64 received, qint64 total)
{
    if (total > 0)
        emit progress(m_currentJob.name,
                      static_cast<int>(100 * received / total));
}

void ModelDownloader::onDownloadFinished()
{
    m_outputFile->flush();
    m_outputFile->close();

    const QString partPath = m_currentJob.destPath + ".part";
    bool ok = true;

    if (!m_currentJob.sha256.isEmpty())
        ok = verifyChecksum(partPath, m_currentJob.sha256);

    if (ok) {
        QFile::rename(partPath, m_currentJob.destPath);
        emit finished(m_currentJob.name, true);
    } else {
        QFile::remove(partPath);
        emit finished(m_currentJob.name, false);
    }

    m_outputFile->deleteLater();
    m_outputFile = nullptr;
    m_currentReply->deleteLater();
    m_currentReply = nullptr;

    QTimer::singleShot(0, this, &ModelDownloader::downloadNext);
}

void ModelDownloader::onDownloadError(QNetworkReply::NetworkError /*err*/)
{
    if (m_outputFile) {
        m_outputFile->close();
        QFile::remove(m_currentJob.destPath + ".part");
        m_outputFile->deleteLater();
        m_outputFile = nullptr;
    }
    emit finished(m_currentJob.name, false);
    m_currentReply->deleteLater();
    m_currentReply = nullptr;
    QTimer::singleShot(0, this, &ModelDownloader::downloadNext);
}

bool ModelDownloader::verifyChecksum(const QString& filePath,
                                      const QString& expected) const
{
    QFile f(filePath);
    if (!f.open(QIODevice::ReadOnly)) return false;
    QCryptographicHash hash(QCryptographicHash::Sha256);
    hash.addData(&f);
    return hash.result().toHex() == expected.toLatin1();
}
