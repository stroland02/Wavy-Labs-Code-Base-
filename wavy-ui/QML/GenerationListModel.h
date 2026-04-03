#pragma once

#include <QAbstractListModel>
#include <QString>
#include <QVariantList>

// ---------------------------------------------------------------------------
// GenerationListModel — QAbstractListModel for QML generation history list.
// ---------------------------------------------------------------------------

struct GenerationEntry {
    QString prompt;
    QString audioPath;
    double  duration{0};
    QVariantList sections;
};

class GenerationListModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles {
        PromptRole = Qt::UserRole + 1,
        AudioPathRole,
        DurationRole,
        SectionsRole,
    };

    explicit GenerationListModel(QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = QModelIndex()) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    Q_INVOKABLE void addEntry(const QString& prompt, const QString& audioPath,
                               double duration, const QVariantList& sections = {});
    Q_INVOKABLE void clear();

    const GenerationEntry& entryAt(int index) const { return m_entries[index]; }

private:
    QList<GenerationEntry> m_entries;
};
