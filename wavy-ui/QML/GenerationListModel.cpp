#include "GenerationListModel.h"

GenerationListModel::GenerationListModel(QObject* parent)
    : QAbstractListModel(parent)
{
}

int GenerationListModel::rowCount(const QModelIndex& parent) const
{
    return parent.isValid() ? 0 : m_entries.size();
}

QVariant GenerationListModel::data(const QModelIndex& index, int role) const
{
    if (!index.isValid() || index.row() >= m_entries.size())
        return {};

    const auto& e = m_entries[index.row()];
    switch (role) {
    case PromptRole:    return e.prompt;
    case AudioPathRole: return e.audioPath;
    case DurationRole:  return e.duration;
    case SectionsRole:  return e.sections;
    default:            return {};
    }
}

QHash<int, QByteArray> GenerationListModel::roleNames() const
{
    return {
        { PromptRole,    "prompt"    },
        { AudioPathRole, "audioPath" },
        { DurationRole,  "duration"  },
        { SectionsRole,  "sections"  },
    };
}

void GenerationListModel::addEntry(const QString& prompt, const QString& audioPath,
                                    double duration, const QVariantList& sections)
{
    beginInsertRows(QModelIndex(), m_entries.size(), m_entries.size());
    m_entries.append({ prompt, audioPath, duration, sections });
    endInsertRows();
}

void GenerationListModel::clear()
{
    beginResetModel();
    m_entries.clear();
    endResetModel();
}
