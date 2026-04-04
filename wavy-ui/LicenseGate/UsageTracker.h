#pragma once
#include <QMap>
#include <QObject>
#include <QString>
#include <QDateTime>
#include <QSqlDatabase>

// ---------------------------------------------------------------------------
// UsageTracker — SQLite-backed daily generation counter for the Free tier.
// DB file: <AppData>/WavyLabs/usage.db
// ---------------------------------------------------------------------------

class UsageTracker : public QObject
{
    Q_OBJECT
public:
    static UsageTracker* instance();

    static constexpr int FREE_DAILY_LIMIT = 5;

    // ── Per-feature ElevenLabs daily limits ────────────────────────────────
    // Feature key → { free_limit, pro_limit, studio_limit }
    struct ELLimits { int free; int pro; int studio; };
    static const QMap<QString, ELLimits>& elFeatureLimits();

    // Returns the number of generations remaining today (free tier).
    int dailyRemaining() const;

    // Record one generation. Returns false if daily limit exceeded.
    bool recordGeneration(const QString& modelUsed = "");

    // Total lifetime generations (for stats display).
    int totalGenerations() const;

    // Reset daily count (called automatically at midnight).
    void resetIfNewDay();

    // ElevenLabs per-feature daily counter
    int elFeatureRemaining(const QString& feature, int limit) const;
    int elTotalRemaining(int totalLimit) const;
    bool recordElevenLabsCall(const QString& method = "");

private:
    explicit UsageTracker(QObject* parent = nullptr);
    static UsageTracker* s_instance;

    bool initDb();
    bool ensureTodayRow();

    QSqlDatabase m_db;
    QString      m_dbPath;
    QString      m_today;    // ISO date string for today

    void updateToday();
};
