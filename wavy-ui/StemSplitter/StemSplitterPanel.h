#pragma once
#include <QWidget>
#include <QStringList>
#include <QComboBox>
#include <QLabel>
#include <QPushButton>
#include <QProgressBar>
#include <QListWidget>

class AIClient;

// ---------------------------------------------------------------------------
// StemSplitterPanel — dedicated stem-split UI (also callable from context menu)
// ---------------------------------------------------------------------------

class StemSplitterPanel : public QWidget
{
    Q_OBJECT
public:
    explicit StemSplitterPanel(AIClient* client, QWidget* parent = nullptr);

    // Set the input file programmatically (e.g. from right-click context menu)
    void setInputFile(const QString& path);

Q_SIGNALS:
    void stemsReady(const QStringList& paths, const QStringList& names);

private Q_SLOTS:
    void onBrowseClicked();
    void onSplitClicked();
    void onSplitFinished(bool ok, const QVariantMap& result);

private:
    AIClient*     m_client{nullptr};
    QLabel*       m_inputLabel{nullptr};
    QComboBox*    m_stemCountCombo{nullptr};
    QPushButton*  m_splitBtn{nullptr};
    QProgressBar* m_progress{nullptr};
    QListWidget*  m_outputList{nullptr};
    QString       m_inputPath;

    void buildUI();
    void setSplitting(bool busy);
};
