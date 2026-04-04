#include "LicenseManager.h"
#include "UsageTracker.h"

#include <QCryptographicHash>
#include <QMessageAuthenticationCode>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QSettings>
#include <QUrl>
#include <QJsonDocument>
#include <QJsonObject>
#include <QEventLoop>
#include <QThread>
#include <mutex>

// Windows DPAPI for token encryption (replaces trivial XOR)
#ifdef Q_OS_WIN
#  include <windows.h>
#  include <wincrypt.h>
#  pragma comment(lib, "crypt32.lib")
#endif

// Optional qtkeychain integration
#ifdef WAVY_USE_KEYCHAIN
#  include <qt6keychain/keychain.h>
using namespace QKeychain;
#endif

// ---------------------------------------------------------------------------
// HMAC secret — replaced at build time via -DWAVY_LICENSE_HMAC_SECRET=...
// Fall back to WAVY_HMAC_SECRET env var, then compile-time default.
// IMPORTANT: Set a strong secret for production builds!
// ---------------------------------------------------------------------------
#ifndef WAVY_LICENSE_HMAC_SECRET
#  define WAVY_LICENSE_HMAC_SECRET "CHANGE_ME_IN_PRODUCTION"
#endif

static QByteArray hmacSecret()
{
    static const QByteArray s = []() {
        QByteArray env = qgetenv("WAVY_HMAC_SECRET");
        if (!env.isEmpty()) return env;
        QByteArray compiled(WAVY_LICENSE_HMAC_SECRET);
        if (compiled == "CHANGE_ME_IN_PRODUCTION")
            qWarning("LicenseManager: HMAC secret is still the default placeholder! "
                     "Set -DWAVY_LICENSE_HMAC_SECRET=... or WAVY_HMAC_SECRET env var.");
        return compiled;
    }();
    return s;
}

// License server base URL — override at build time via -DWAVY_LICENSE_SERVER_URL=...
// NOTE: License validation is bypassed in the open-source build (tier() always returns Studio).
// This URL is dead code in normal operation but kept for potential future opt-in telemetry.
#ifndef WAVY_LICENSE_SERVER_URL
#  define WAVY_LICENSE_SERVER_URL "https://license.wavylab.net"
#endif

// XOR key for QSettings obfuscation (not cryptographic — just avoids
// plain-text storage when qtkeychain is unavailable)
static constexpr quint8 XOR_MASK = 0xA7;

LicenseManager* LicenseManager::s_instance = nullptr;

LicenseManager* LicenseManager::instance()
{
    static std::once_flag flag;
    std::call_once(flag, []{ s_instance = new LicenseManager(); });
    return s_instance;
}

LicenseManager::LicenseManager(QObject* parent)
    : QObject(parent)
{
    loadFromKeychain();
    m_lastValidatedAt = loadValidatedAt();
}

// ---------------------------------------------------------------------------
// tier() — open-source build: always Studio
// ---------------------------------------------------------------------------

Tier LicenseManager::tier() const
{
    // NOTE: License validation bypassed in open-source build.
    // All features are unlocked. Users bring their own API keys via Settings.
    return Tier::Studio;
}

// ---------------------------------------------------------------------------
// Offline grace period
// ---------------------------------------------------------------------------

bool LicenseManager::needsRevalidation() const
{
    if (m_activatedTier == Tier::Free)
        return false;
    if (!m_lastValidatedAt.isValid())
        return true;
    return m_lastValidatedAt.daysTo(QDateTime::currentDateTimeUtc()) > GRACE_PERIOD_DAYS;
}

bool LicenseManager::revalidateWithServer()
{
    // ── Account-based validation (preferred) ──────────────────────────────
    if (isLoggedIn()) {
        // If access token is expired (or near expiry), refresh first
        if (m_tokenExpiry.isValid() &&
            QDateTime::currentDateTimeUtc() >= m_tokenExpiry)
        {
            refreshAccountToken();
        }

        if (m_accessToken.isEmpty())
            return false;

        QNetworkAccessManager nam;
        const QUrl url(QString("%1/account/verify").arg(WAVY_LICENSE_SERVER_URL));
        QNetworkRequest req(url);
        req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        req.setTransferTimeout(45000);

        const QJsonObject body{{"access_token", m_accessToken}};
        QNetworkReply* reply = nam.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));

        QEventLoop loop;
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec();

        bool ok = false;
        if (reply->error() == QNetworkReply::NoError) {
            const QJsonObject resp = QJsonDocument::fromJson(reply->readAll()).object();
            if (resp.value("valid").toBool(false)) {
                const QString tierStr = resp.value("tier").toString("free");
                Tier newTier = Tier::Free;
                if (tierStr == "studio")   newTier = Tier::Studio;
                else if (tierStr == "pro") newTier = Tier::Pro;

                if (newTier != m_activatedTier) {
                    m_activatedTier = newTier;
                    emit tierChanged(m_activatedTier);
                }

                const QDateTime now = QDateTime::currentDateTimeUtc();
                m_lastValidatedAt = now;
                saveValidatedAt(now);
                ok = true;
            }
        }
        reply->deleteLater();

        if (!ok && needsRevalidation()) {
            logoutAccount();
            emit gracePeriodExpired();
        }
        return ok;
    }

    // ── Legacy key-based validation ───────────────────────────────────────
    if (m_licenseKey.isEmpty())
        return false;

    QNetworkAccessManager nam;
    const QUrl url(QString("%1/validate").arg(WAVY_LICENSE_SERVER_URL));
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    req.setTransferTimeout(45000);

    const QJsonObject body{{"key", m_licenseKey}};
    QNetworkReply* reply = nam.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));

    QEventLoop loop;
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    loop.exec();

    bool ok = false;
    if (reply->error() == QNetworkReply::NoError) {
        const QJsonObject resp = QJsonDocument::fromJson(reply->readAll()).object();
        ok = resp.value("valid").toBool(false);
    }
    reply->deleteLater();

    if (ok) {
        const QDateTime now = QDateTime::currentDateTimeUtc();
        m_lastValidatedAt = now;
        saveValidatedAt(now);
    } else if (needsRevalidation()) {
        deactivateLicense();
        emit gracePeriodExpired();
    }

    return ok;
}

// ---------------------------------------------------------------------------
// Account-based auth (Supabase)
// ---------------------------------------------------------------------------

bool LicenseManager::loginWithAccount(const QString& email, const QString& password)
{
    QNetworkAccessManager nam;
    const QUrl url(QString("%1/account/login").arg(WAVY_LICENSE_SERVER_URL));
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    req.setTransferTimeout(45000);

    const QJsonObject body{{"email", email}, {"password", password}};
    QNetworkReply* reply = nam.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));

    QEventLoop loop;
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    loop.exec();

    bool ok = false;
    if (reply->error() == QNetworkReply::NoError) {
        const QJsonObject resp = QJsonDocument::fromJson(reply->readAll()).object();
        if (resp.contains("access_token")) {
            m_email        = resp.value("email").toString(email);
            m_accessToken  = resp.value("access_token").toString();
            m_refreshToken = resp.value("refresh_token").toString();
            const int exp  = resp.value("expires_in").toInt(3600);
            m_tokenExpiry  = QDateTime::currentDateTimeUtc().addSecs(exp - 60);

            const QString tierStr = resp.value("tier").toString("free");
            if (tierStr == "studio")   m_activatedTier = Tier::Studio;
            else if (tierStr == "pro") m_activatedTier = Tier::Pro;
            else                       m_activatedTier = Tier::Free;

            const QDateTime now = QDateTime::currentDateTimeUtc();
            m_lastValidatedAt = now;
            saveValidatedAt(now);
            saveAccountTokens();

            emit tierChanged(m_activatedTier);
            emit loginStateChanged(true);
            ok = true;
        }
    }
    reply->deleteLater();
    return ok;
}

bool LicenseManager::refreshAccountToken()
{
    if (m_refreshToken.isEmpty())
        return false;

    QNetworkAccessManager nam;
    const QUrl url(QString("%1/account/refresh").arg(WAVY_LICENSE_SERVER_URL));
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    req.setTransferTimeout(45000);

    const QJsonObject body{{"refresh_token", m_refreshToken}};
    QNetworkReply* reply = nam.post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));

    QEventLoop loop;
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    loop.exec();

    bool ok = false;
    if (reply->error() == QNetworkReply::NoError) {
        const QJsonObject resp = QJsonDocument::fromJson(reply->readAll()).object();
        if (resp.contains("access_token")) {
            m_accessToken  = resp.value("access_token").toString();
            m_refreshToken = resp.value("refresh_token").toString();
            const int exp  = resp.value("expires_in").toInt(3600);
            m_tokenExpiry  = QDateTime::currentDateTimeUtc().addSecs(exp - 60);
            saveAccountTokens();
            ok = true;
        }
    }
    reply->deleteLater();
    return ok;
}

void LicenseManager::logoutAccount()
{
    m_email.clear();
    m_accessToken.clear();
    m_refreshToken.clear();
    m_tokenExpiry = QDateTime();
    clearAccountTokens();
    deactivateLicense();  // also clears key, tier, and validated_at
    emit loginStateChanged(false);
}

// ---------------------------------------------------------------------------
// Legacy license key activation
// ---------------------------------------------------------------------------

bool LicenseManager::activateLicense(const QString& key)
{
    if (!validateHmac(key))
        return false;

    Tier newTier = Tier::Free;
    if (key.startsWith("PRO-"))       newTier = Tier::Pro;
    else if (key.startsWith("STU-"))  newTier = Tier::Studio;
    else return false;

    m_activatedTier = newTier;
    m_licenseKey    = key;
    saveToKeychain(key);

    const QDateTime now = QDateTime::currentDateTimeUtc();
    m_lastValidatedAt = now;
    saveValidatedAt(now);

    emit tierChanged(m_activatedTier);
    return true;
}

void LicenseManager::deactivateLicense()
{
    m_activatedTier = Tier::Free;
    m_licenseKey.clear();
    m_lastValidatedAt = QDateTime();
    removeFromKeychain();
    emit tierChanged(Tier::Free);
}

// ---------------------------------------------------------------------------
// HMAC validation
// ---------------------------------------------------------------------------

bool LicenseManager::validateHmac(const QString& key) const
{
    const QStringList parts = key.split('-');
    if (parts.size() < 3) return false;

    const QString hmacPart = parts.last();
    const QString payload  = key.left(key.length() - hmacPart.length() - 1);

    const QByteArray computed = QMessageAuthenticationCode::hash(
        payload.toUtf8(), hmacSecret(), QCryptographicHash::Sha256).toHex();

    return computed.left(8) == hmacPart.toLower().toLatin1();
}

// ---------------------------------------------------------------------------
// Account token persistence (QSettings, XOR-obfuscated)
// ---------------------------------------------------------------------------

static const char* KC_SETTINGS   = "WavyLabs/License";
static const char* KC_ACC_EMAIL   = "acc_email";
static const char* KC_ACC_ACCESS  = "acc_access";
static const char* KC_ACC_REFRESH = "acc_refresh";
static const char* KC_ACC_EXPIRY  = "acc_expiry";
static const char* KC_ACC_TIER    = "acc_tier";

// Legacy XOR encode/decode — kept for migration from old stored tokens
static QByteArray xorEncode(const QString& v) {
    const QByteArray raw = v.toUtf8();
    QByteArray enc(raw.size(), '\0');
    for (int i = 0; i < raw.size(); ++i)
        enc[i] = raw[i] ^ XOR_MASK;
    return enc.toBase64();
}

static QString xorDecode(const QByteArray& b64) {
    const QByteArray enc = QByteArray::fromBase64(b64);
    QByteArray dec(enc.size(), '\0');
    for (int i = 0; i < enc.size(); ++i)
        dec[i] = enc[i] ^ XOR_MASK;
    return QString::fromUtf8(dec);
}

// ---------------------------------------------------------------------------
// DPAPI-based token encryption (Windows) — encrypts to current user context
// Stored format: "dpapi:" + base64(DPAPI_blob)
// Old XOR format: plain base64 (no prefix) — auto-migrated on next save
// ---------------------------------------------------------------------------

#ifdef Q_OS_WIN
static QByteArray dpapiEncrypt(const QByteArray& plaintext)
{
    DATA_BLOB in;
    in.cbData = static_cast<DWORD>(plaintext.size());
    in.pbData = reinterpret_cast<BYTE*>(const_cast<char*>(plaintext.data()));
    DATA_BLOB out{};
    if (CryptProtectData(&in, nullptr, nullptr, nullptr, nullptr,
                         CRYPTPROTECT_UI_FORBIDDEN, &out)) {
        QByteArray result(reinterpret_cast<const char*>(out.pbData),
                          static_cast<int>(out.cbData));
        LocalFree(out.pbData);
        return result;
    }
    return {};
}

static QByteArray dpapiDecrypt(const QByteArray& encrypted)
{
    DATA_BLOB in;
    in.cbData = static_cast<DWORD>(encrypted.size());
    in.pbData = reinterpret_cast<BYTE*>(const_cast<char*>(encrypted.data()));
    DATA_BLOB out{};
    if (CryptUnprotectData(&in, nullptr, nullptr, nullptr, nullptr,
                           CRYPTPROTECT_UI_FORBIDDEN, &out)) {
        QByteArray result(reinterpret_cast<const char*>(out.pbData),
                          static_cast<int>(out.cbData));
        LocalFree(out.pbData);
        return result;
    }
    return {};
}
#endif

static constexpr const char* DPAPI_PREFIX = "dpapi:";

static QByteArray encryptToken(const QString& v)
{
    if (v.isEmpty()) return {};
#ifdef Q_OS_WIN
    QByteArray encrypted = dpapiEncrypt(v.toUtf8());
    if (!encrypted.isEmpty())
        return QByteArray(DPAPI_PREFIX) + encrypted.toBase64();
#endif
    // Fallback: XOR (non-Windows or DPAPI failure)
    return xorEncode(v);
}

static QString decryptToken(const QByteArray& stored)
{
    if (stored.isEmpty()) return {};
#ifdef Q_OS_WIN
    if (stored.startsWith(DPAPI_PREFIX)) {
        QByteArray raw = QByteArray::fromBase64(stored.mid(int(strlen(DPAPI_PREFIX))));
        QByteArray decrypted = dpapiDecrypt(raw);
        if (!decrypted.isEmpty())
            return QString::fromUtf8(decrypted);
        return {};  // DPAPI failed — token corrupted
    }
#endif
    // Legacy XOR format (auto-migrated on next save)
    return xorDecode(stored);
}

// Public wrappers — used by ApiKeySettings + BackendLauncher
QByteArray LicenseManager::encryptApiKey(const QString& value)
{
    return encryptToken(value);
}

QString LicenseManager::decryptApiKey(const QByteArray& stored)
{
    return decryptToken(stored);
}

void LicenseManager::saveAccountTokens()
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    s.setValue(KC_ACC_EMAIL,   m_email);
    s.setValue(KC_ACC_ACCESS,  encryptToken(m_accessToken));
    s.setValue(KC_ACC_REFRESH, encryptToken(m_refreshToken));
    s.setValue(KC_ACC_EXPIRY,  m_tokenExpiry.toString(Qt::ISODate));

    const QString tierStr = m_activatedTier == Tier::Studio ? "studio" :
                            m_activatedTier == Tier::Pro    ? "pro"    : "free";
    s.setValue(KC_ACC_TIER, tierStr);
}

void LicenseManager::loadAccountTokens()
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    m_email = s.value(KC_ACC_EMAIL).toString();
    if (m_email.isEmpty()) return;

    m_accessToken  = decryptToken(s.value(KC_ACC_ACCESS).toByteArray());
    m_refreshToken = decryptToken(s.value(KC_ACC_REFRESH).toByteArray());
    m_tokenExpiry  = QDateTime::fromString(
                         s.value(KC_ACC_EXPIRY).toString(), Qt::ISODate);

    const QString tierStr = s.value(KC_ACC_TIER, "free").toString();
    if (tierStr == "studio")   m_activatedTier = Tier::Studio;
    else if (tierStr == "pro") m_activatedTier = Tier::Pro;
    else                       m_activatedTier = Tier::Free;
}

void LicenseManager::clearAccountTokens()
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    s.remove(KC_ACC_EMAIL);
    s.remove(KC_ACC_ACCESS);
    s.remove(KC_ACC_REFRESH);
    s.remove(KC_ACC_EXPIRY);
    s.remove(KC_ACC_TIER);
    m_email.clear();
    m_accessToken.clear();
    m_refreshToken.clear();
    m_tokenExpiry = QDateTime();
}

// ---------------------------------------------------------------------------
// Keychain — OS credential store with QSettings fallback (legacy keys)
// ---------------------------------------------------------------------------

static const char* KC_SERVICE = "WavyLabs";
static const char* KC_ACCOUNT = "license_key";

void LicenseManager::loadFromKeychain()
{
    // Account tokens take priority over legacy keys
    loadAccountTokens();
    if (isLoggedIn()) return;

#ifdef WAVY_USE_KEYCHAIN
    ReadPasswordJob job(KC_SERVICE);
    job.setAutoDelete(false);
    job.setKey(KC_ACCOUNT);
    QEventLoop loop;
    QObject::connect(&job, &Job::finished, &loop, &QEventLoop::quit);
    job.start();
    loop.exec();

    if (job.error() == NoError) {
        const QString key = job.textData();
        if (!key.isEmpty() && validateHmac(key)) {
            m_licenseKey = key;
            if (key.startsWith("STU-"))      m_activatedTier = Tier::Studio;
            else if (key.startsWith("PRO-")) m_activatedTier = Tier::Pro;
            return;
        }
    }
#endif
    const QString key = readSettingsKey();
    if (!key.isEmpty() && validateHmac(key)) {
        m_licenseKey = key;
        if (key.startsWith("STU-"))      m_activatedTier = Tier::Studio;
        else if (key.startsWith("PRO-")) m_activatedTier = Tier::Pro;
    }
}

void LicenseManager::saveToKeychain(const QString& key)
{
#ifdef WAVY_USE_KEYCHAIN
    WritePasswordJob job(KC_SERVICE);
    job.setAutoDelete(false);
    job.setKey(KC_ACCOUNT);
    job.setTextData(key);
    QEventLoop loop;
    QObject::connect(&job, &Job::finished, &loop, &QEventLoop::quit);
    job.start();
    loop.exec();
    if (job.error() == NoError) return;
#endif
    writeSettingsKey(key);
}

void LicenseManager::removeFromKeychain()
{
#ifdef WAVY_USE_KEYCHAIN
    DeletePasswordJob job(KC_SERVICE);
    job.setAutoDelete(false);
    job.setKey(KC_ACCOUNT);
    QEventLoop loop;
    QObject::connect(&job, &Job::finished, &loop, &QEventLoop::quit);
    job.start();
    loop.exec();
#endif
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    s.remove("key");
}

// ── QSettings fallback (legacy key, XOR-obfuscated) ──────────────────────

QString LicenseManager::readSettingsKey() const
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    return decryptToken(s.value("key").toByteArray());
}

void LicenseManager::writeSettingsKey(const QString& key)
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    s.setValue("key", encryptToken(key));
}

// ── Validation timestamp ─────────────────────────────────────────────────

void LicenseManager::saveValidatedAt(const QDateTime& dt)
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    s.setValue("validated_at", dt.toString(Qt::ISODate));
}

QDateTime LicenseManager::loadValidatedAt() const
{
    QSettings s(KC_SETTINGS, QSettings::IniFormat);
    return QDateTime::fromString(s.value("validated_at").toString(), Qt::ISODate);
}

// ---------------------------------------------------------------------------
// Daily counter — delegated to SQLite UsageTracker
// ---------------------------------------------------------------------------

int LicenseManager::dailyGenerationsRemaining() const
{
    if (isPro()) return 999999;
    return UsageTracker::instance()->dailyRemaining();
}

bool LicenseManager::recordGeneration(const QString& modelUsed)
{
    if (isPro()) return true;
    return UsageTracker::instance()->recordGeneration(modelUsed);
}

bool LicenseManager::canGenerate() const
{
    return isPro() || dailyGenerationsRemaining() > 0;
}

// ---------------------------------------------------------------------------
// ElevenLabs per-feature tier gates & daily counters
// ---------------------------------------------------------------------------

bool LicenseManager::canElevenLabs(const QString& feature) const
{
    const auto& lim = UsageTracker::elFeatureLimits();
    auto it = lim.find(feature);
    if (it == lim.end()) return false;

    int featureLimit = 0;
    if (isStudio())     featureLimit = it->studio;
    else if (isPro())   featureLimit = it->pro;
    else                featureLimit = it->free;

    if (featureLimit <= 0) return false;

    if (UsageTracker::instance()->elFeatureRemaining(feature, featureLimit) <= 0)
        return false;

    if (elevenLabsDailyRemaining() <= 0)
        return false;

    return true;
}

int LicenseManager::elFeatureRemaining(const QString& feature) const
{
    const auto& lim = UsageTracker::elFeatureLimits();
    auto it = lim.find(feature);
    if (it == lim.end()) return 0;

    int featureLimit = 0;
    if (isStudio())     featureLimit = it->studio;
    else if (isPro())   featureLimit = it->pro;
    else                featureLimit = it->free;

    return UsageTracker::instance()->elFeatureRemaining(feature, featureLimit);
}

int LicenseManager::elevenLabsDailyRemaining() const
{
    int totalLimit = 0;
    if (isStudio())     totalLimit = 100;
    else if (isPro())   totalLimit = 30;
    else                totalLimit = 3;

    return UsageTracker::instance()->elTotalRemaining(totalLimit);
}

bool LicenseManager::recordElevenLabsCall(const QString& method)
{
    return UsageTracker::instance()->recordElevenLabsCall(method);
}
