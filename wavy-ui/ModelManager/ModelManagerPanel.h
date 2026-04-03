#pragma once
#include <QWidget>
#include <QScrollArea>
#include <QVBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QProgressBar>
#include <QMap>
#include <QString>

class ModelManager;

// ---------------------------------------------------------------------------
// ModelManagerPanel — visual UI for model download/status management.
// Section A: Cloud API models (connection status, no download)
// Section B: Local models (download, uninstall, update)
// ---------------------------------------------------------------------------

class ModelManagerPanel : public QWidget
{
    Q_OBJECT
public:
    explicit ModelManagerPanel(ModelManager* mgr, QWidget* parent = nullptr);

    // Refresh the display from the current ModelManager state.
    void refresh();

Q_SIGNALS:
    void allModelsReady();

private Q_SLOTS:
    void onDownloadClicked(const QString& name);
    void onUninstallClicked(const QString& name);
    void onDownloadProgress(const QString& name, int percent);
    void onDownloadFinished(const QString& name, bool success);
    void onStatusChanged();

private:
    struct ModelRow {
        QWidget*      widget{nullptr};
        QLabel*       statusLabel{nullptr};
        QProgressBar* progress{nullptr};
        QPushButton*  actionBtn{nullptr};    // Download / Update
        QPushButton*  uninstallBtn{nullptr}; // Shown only when installed
    };

    void buildUI();
    void buildCloudApiSection(QVBoxLayout* parent);
    void buildLocalModelsSection(QVBoxLayout* parent);
    ModelRow buildLocalModelRow(const QString& name, const QString& displayName,
                                bool recommended, double diskSizeGb);
    void setRowStatus(const QString& name, bool downloaded, bool loading);
    qint64 availableDiskBytes() const;

    ModelManager*            m_mgr{nullptr};
    QWidget*                 m_cloudApiSection{nullptr};
    QVBoxLayout*             m_localRowLayout{nullptr};
    QLabel*                  m_diskLabel{nullptr};
    QPushButton*             m_downloadAllRecommendedBtn{nullptr};
    QLabel*                  m_cloudStatusLabel{nullptr};
    QMap<QString, ModelRow>  m_rows;
    // Cloud API row labels keyed by model name
    QMap<QString, QLabel*>   m_cloudRows;
};
