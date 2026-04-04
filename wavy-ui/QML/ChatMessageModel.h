#pragma once

#include <QAbstractListModel>
#include <QString>
#include <QVariantList>

// ---------------------------------------------------------------------------
// ChatMessageModel — QAbstractListModel for QML chat history display.
// ---------------------------------------------------------------------------

struct ChatMessage {
    QString role;         // "user" or "wavy"
    QString content;
    QVariantList actions; // optional DAW actions
    QString widget;       // "note_grid" | "chords" | "beat_grid" | "mix_fixes" | ""
    QVariantMap widgetData;
};

class ChatMessageModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles {
        RoleNameRole = Qt::UserRole + 1,
        ContentRole,
        ActionsRole,
        IsUserRole,
        WidgetRole,
        WidgetDataRole,
    };

    explicit ChatMessageModel(QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = QModelIndex()) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    void addMessage(const QString& role, const QString& content,
                    const QVariantList& actions = {},
                    const QString& widget = {},
                    const QVariantMap& widgetData = {});
    void clear();

    // Get history as QVariantList for sending to backend
    QVariantList toVariantList() const;

private:
    QList<ChatMessage> m_messages;
};
