#include "ChatMessageModel.h"

ChatMessageModel::ChatMessageModel(QObject* parent)
    : QAbstractListModel(parent)
{
}

int ChatMessageModel::rowCount(const QModelIndex& parent) const
{
    return parent.isValid() ? 0 : m_messages.size();
}

QVariant ChatMessageModel::data(const QModelIndex& index, int role) const
{
    if (!index.isValid() || index.row() >= m_messages.size())
        return {};

    const auto& m = m_messages[index.row()];
    switch (role) {
    case RoleNameRole:  return m.role;
    case ContentRole:   return m.content;
    case ActionsRole:   return m.actions;
    case IsUserRole:    return m.role == "user";
    case WidgetRole:    return m.widget;
    case WidgetDataRole:return m.widgetData;
    default:            return {};
    }
}

QHash<int, QByteArray> ChatMessageModel::roleNames() const
{
    return {
        { RoleNameRole,  "roleName"   },
        { ContentRole,   "content"    },
        { ActionsRole,   "actions"    },
        { IsUserRole,    "isUser"     },
        { WidgetRole,    "widget"     },
        { WidgetDataRole,"widgetData" },
    };
}

void ChatMessageModel::addMessage(const QString& role, const QString& content,
                                   const QVariantList& actions,
                                   const QString& widget,
                                   const QVariantMap& widgetData)
{
    beginInsertRows(QModelIndex(), m_messages.size(), m_messages.size());
    m_messages.append({ role, content, actions, widget, widgetData });
    endInsertRows();
}

void ChatMessageModel::clear()
{
    beginResetModel();
    m_messages.clear();
    endResetModel();
}

QVariantList ChatMessageModel::toVariantList() const
{
    QVariantList list;
    for (const auto& m : m_messages) {
        QVariantMap entry;
        entry["role"]    = m.role;
        entry["content"] = m.content;
        list.append(entry);
    }
    return list;
}
