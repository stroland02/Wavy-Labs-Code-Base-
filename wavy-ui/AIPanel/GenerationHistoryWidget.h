#pragma once
#include <QWidget>
#include <QListWidget>
#include <QVBoxLayout>
#include <QString>
#include <QVariantList>

// ---------------------------------------------------------------------------
// GenerationHistoryWidget — scrollable list of past AI generations.
// Each entry shows the prompt, duration, and a Play button.
// ---------------------------------------------------------------------------

class GenerationHistoryWidget : public QWidget
{
    Q_OBJECT
public:
    explicit GenerationHistoryWidget(QWidget* parent = nullptr);

    void addEntry(const QString& prompt, const QString& audioPath, double duration,
                  const QVariantList& sections = QVariantList());
    void clear();

Q_SIGNALS:
    void entryPlayRequested(const QString& audioPath);
    void entryInsertRequested(const QString& audioPath, const QString& trackName, const QVariantList& sections);

private Q_SLOTS:
    void onItemDoubleClicked(QListWidgetItem* item);

private:
    QListWidget* m_list{nullptr};
};
