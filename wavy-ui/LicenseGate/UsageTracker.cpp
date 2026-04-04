#include "UsageTracker.h"

#include <QDir>
#include <QSqlError>
#include <QSqlQuery>
#include <QStandardPaths>
#include <QtDebug>
#include <mutex>

UsageTracker* UsageTracker::s_instance = nullptr;

UsageTracker* UsageTracker::instance()
{
    static std::once_flag flag;
    std::call_once(flag, []{ s_instance = new UsageTracker(); });
    return s_instance;
}

UsageTracker::UsageTracker(QObject* parent)
    : QObject(parent)
{
    const QString dir = QStandardPaths::writableLocation(
        QStandardPaths::AppDataLocation);
    QDir().mkpath(dir);
    m_dbPath = dir + "/usage.db";
    updateToday();
    initDb();
    resetIfNewDay();
}

// ---------------------------------------------------------------------------
// DB setup
// ---------------------------------------------------------------------------

bool UsageTracker::initDb()
{
    m_db = QSqlDatabase::addDatabase("QSQLITE", "wavy_usage");
    m_db.setDatabaseName(m_dbPath);

    if (!m_db.open()) {
        qWarning() << "[UsageTracker] Cannot open DB:" << m_db.lastError().text();
        QFile dbg(QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/wavy_debug.log");
        if (dbg.open(QIODevice::Append)) {
            dbg.write(("DB OPEN FAILED: " + m_db.lastError().text() + "\n").toUtf8());
            dbg.write(("  drivers: " + QSqlDatabase::drivers().join(", ") + "\n").toUtf8());
            dbg.write(("  path: " + m_dbPath + "\n").toUtf8());
            dbg.close();
        }
        return false;
    } else {
        QFile dbg(QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/wavy_debug.log");
        if (dbg.open(QIODevice::Append)) {
            dbg.write(("DB OK path=" + m_dbPath + "\n").toUtf8());
            dbg.close();
        }
    }

    QSqlQuery q(m_db);
    // Daily usage table
    q.exec(R"(
        CREATE TABLE IF NOT EXISTS daily_usage (
            date        TEXT PRIMARY KEY,
            count       INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL
        )
    )");
    // Generation log table
    q.exec(R"(
        CREATE TABLE IF NOT EXISTS generation_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            model       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        )
    )");
    // ElevenLabs per-feature daily usage table — migrate old single-PK schema
    {
        QSqlQuery chk(m_db);
        chk.exec("PRAGMA table_info(elevenlabs_daily)");
        bool hasFeatureCol = false;
        while (chk.next()) {
            if (chk.value(1).toString() == "feature") { hasFeatureCol = true; break; }
        }
        if (!hasFeatureCol) {
            q.exec("DROP TABLE IF EXISTS elevenlabs_daily");
        }
    }
    q.exec(R"(
        CREATE TABLE IF NOT EXISTS elevenlabs_daily (
            date        TEXT NOT NULL,
            feature     TEXT NOT NULL DEFAULT '',
            count       INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (date, feature)
        )
    )");
    if (q.lastError().isValid()) {
        qWarning() << "[UsageTracker] Schema error:" << q.lastError().text();
        return false;
    }
    return true;
}

bool UsageTracker::ensureTodayRow()
{
    QSqlQuery q(m_db);
    q.prepare("INSERT OR IGNORE INTO daily_usage (date, count, updated_at) "
              "VALUES (?, 0, ?)");
    q.addBindValue(m_today);
    q.addBindValue(QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    return q.exec();
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void UsageTracker::updateToday()
{
    m_today = QDate::currentDate().toString(Qt::ISODate);
}

void UsageTracker::resetIfNewDay()
{
    const QString today = QDate::currentDate().toString(Qt::ISODate);
    if (m_today != today) {
        m_today = today;
    }
    ensureTodayRow();
}

int UsageTracker::dailyRemaining() const
{
    if (!m_db.isOpen()) return 0;

    QSqlQuery q(m_db);
    q.prepare("SELECT count FROM daily_usage WHERE date = ?");
    q.addBindValue(m_today);
    if (!q.exec() || !q.next()) return FREE_DAILY_LIMIT;

    const int used = q.value(0).toInt();
    return qMax(0, FREE_DAILY_LIMIT - used);
}

bool UsageTracker::recordGeneration(const QString& modelUsed)
{
    if (!m_db.isOpen()) return false;
    resetIfNewDay();

    if (dailyRemaining() <= 0) return false;

    // Increment daily count atomically
    QSqlQuery q(m_db);
    q.prepare("INSERT INTO daily_usage (date, count, updated_at) VALUES (?, 1, ?) "
              "ON CONFLICT(date) DO UPDATE SET "
              "count = count + 1, updated_at = excluded.updated_at");
    q.addBindValue(m_today);
    q.addBindValue(QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    if (!q.exec()) {
        qWarning() << "[UsageTracker] recordGeneration error:" << q.lastError().text();
        return false;
    }

    // Log entry
    QSqlQuery log(m_db);
    log.prepare("INSERT INTO generation_log (date, model, created_at) VALUES (?, ?, ?)");
    log.addBindValue(m_today);
    log.addBindValue(modelUsed);
    log.addBindValue(QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    log.exec();

    return true;
}

int UsageTracker::totalGenerations() const
{
    if (!m_db.isOpen()) return 0;
    QSqlQuery q("SELECT COUNT(*) FROM generation_log", m_db);
    if (!q.exec() || !q.next()) return 0;
    return q.value(0).toInt();
}

// ---------------------------------------------------------------------------
// ElevenLabs per-feature limits
// ---------------------------------------------------------------------------
//
// Cost analysis (EL Pro plan $99/mo = 500K credits, ~$0.20/1K credits):
//   TTS ~500 chars = 500 cred = $0.10       SFX auto = 200 cred = $0.04
//   STS ~500 cred = $0.10                   Isolate ~1K cred/min = $0.20
//   Transcribe ~500 cred/min = $0.10        Clone ~1K cred = $0.20
//   Align ~500 cred/min = $0.10             Dub ~3K cred/min = $0.60
//
// Wavy Free=$0  Pro=$9.99/mo  Studio=$24.99/mo
// Target: worst-case Studio user maxing all limits ≈ $15/mo EL cost
// ---------------------------------------------------------------------------

const QMap<QString, UsageTracker::ELLimits>& UsageTracker::elFeatureLimits()
{
    //                                        Free  Pro  Studio
    static const QMap<QString, ELLimits> lim{
        { "music",          { 3, 20, 60 } },  // ElevenLabs music gen — free tier!
        { "tts",            { 0, 15, 50 } },
        { "sts",            { 0, 10, 30 } },
        { "sfx",            { 0, 15, 50 } },
        { "voice_isolate",  { 3, 10, 30 } },  // Free gets Demucs fallback
        { "transcribe",     { 0,  5, 20 } },
        { "voice_clone",    { 0,  0,  5 } },
        { "forced_align",   { 0,  0, 10 } },
        { "dub",            { 0,  0,  5 } },
    };
    return lim;
}

// Total daily cap across all EL features (prevents abuse via spreading)
static constexpr int EL_TOTAL_FREE   = 3;
static constexpr int EL_TOTAL_PRO    = 30;
static constexpr int EL_TOTAL_STUDIO = 100;

int UsageTracker::elFeatureRemaining(const QString& feature, int limit) const
{
    if (!m_db.isOpen() || limit <= 0) return 0;

    QSqlQuery q(m_db);
    q.prepare("SELECT COALESCE(SUM(count),0) FROM elevenlabs_daily "
              "WHERE date = ? AND feature = ?");
    q.addBindValue(m_today);
    q.addBindValue(feature);
    if (!q.exec() || !q.next()) return limit;

    return qMax(0, limit - q.value(0).toInt());
}

int UsageTracker::elTotalRemaining(int totalLimit) const
{
    {
        QFile dbg(QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/wavy_debug.log");
        if (dbg.open(QIODevice::Append)) {
            dbg.write(QString("elTotalRemaining: dbOpen=%1 totalLimit=%2 today=%3\n")
                .arg(m_db.isOpen()).arg(totalLimit).arg(m_today).toUtf8());
            dbg.close();
        }
    }
    if (!m_db.isOpen()) return 0;
    if (totalLimit <= 0) return 0;

    QSqlQuery q(m_db);
    q.prepare("SELECT COALESCE(SUM(count),0) FROM elevenlabs_daily WHERE date = ?");
    q.addBindValue(m_today);
    if (!q.exec() || !q.next()) {
        QFile dbg(QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/wavy_debug.log");
        if (dbg.open(QIODevice::Append)) {
            dbg.write(QString("  query failed or no row, returning totalLimit=%1\n").arg(totalLimit).toUtf8());
            dbg.close();
        }
        return totalLimit;
    }

    const int used = q.value(0).toInt();
    {
        QFile dbg(QStandardPaths::writableLocation(QStandardPaths::TempLocation) + "/wavy_debug.log");
        if (dbg.open(QIODevice::Append)) {
            dbg.write(QString("  used=%1 returning=%2\n").arg(used).arg(qMax(0, totalLimit - used)).toUtf8());
            dbg.close();
        }
    }
    return qMax(0, totalLimit - used);
}

bool UsageTracker::recordElevenLabsCall(const QString& method)
{
    if (!m_db.isOpen()) return false;
    resetIfNewDay();

    const QString now = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);

    QSqlQuery q(m_db);
    q.prepare("INSERT INTO elevenlabs_daily (date, feature, count, updated_at) "
              "VALUES (?, ?, 1, ?) "
              "ON CONFLICT(date, feature) DO UPDATE SET "
              "count = count + 1, updated_at = excluded.updated_at");
    q.addBindValue(m_today);
    q.addBindValue(method);
    q.addBindValue(now);
    if (!q.exec()) {
        qWarning() << "[UsageTracker] recordElevenLabsCall error:" << q.lastError().text();
        return false;
    }

    // Also log to generation_log for analytics
    QSqlQuery log(m_db);
    log.prepare("INSERT INTO generation_log (date, model, created_at) VALUES (?, ?, ?)");
    log.addBindValue(m_today);
    log.addBindValue(QStringLiteral("elevenlabs:") + method);
    log.addBindValue(now);
    log.exec();

    return true;
}
