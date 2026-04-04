#pragma once
#include <QDateTime>
#include <QObject>
#include <QString>

// ---------------------------------------------------------------------------
// LicenseManager — validates user account tier via Supabase (account-based
// auth) with a fallback to legacy HMAC license keys.
//
// Account-based flow (preferred)
// --------------------------------
// 1. User signs in via LoginDialog (email + password).
// 2. loginWithAccount() calls POST /account/login on the license server,
//    which authenticates against Supabase and returns a JWT + tier.
// 3. Tokens and tier are stored in QSettings (XOR-obfuscated).
// 4. revalidateWithServer() calls POST /account/verify periodically.
// 5. If the access token is expired, refreshAccountToken() is called first.
//
// Legacy license key flow (fallback for existing customers)
// ---------------------------------------------------------
// activateLicense(key) validates the HMAC and calls POST /validate.
// Key is stored in the OS keychain (qtkeychain) or QSettings.
//
// Offline grace period
// --------------------
// After a successful validation, the timestamp is persisted.  The app
// operates in full licensed mode for GRACE_PERIOD_DAYS (7) without
// needing the server.  After expiry it demotes to Free until connectivity
// is restored and revalidation succeeds.
// ---------------------------------------------------------------------------

enum class Tier { Free, Pro, Studio };

class LicenseManager : public QObject
{
    Q_OBJECT
public:
    static constexpr int GRACE_PERIOD_DAYS = 7;

    static LicenseManager* instance();

    Tier  tier()     const;
    bool  isPro()    const { return tier() >= Tier::Pro; }
    bool  isStudio() const { return tier() == Tier::Studio; }

    // Returns true when the stored validated-at timestamp is older than
    // GRACE_PERIOD_DAYS.  A free-tier instance always returns false.
    bool needsRevalidation() const;

    // Call from network-available code path (e.g., startup, weekly timer).
    // Returns true if server confirmed the tier; also refreshes the timestamp.
    bool revalidateWithServer();

    // ── Account-based auth (Supabase) ─────────────────────────────────────

    // Sign in with email + password; returns true on success.
    // Stores JWT tokens and tier in QSettings.
    bool loginWithAccount(const QString& email, const QString& password);

    // Refresh the access token using the stored refresh token.
    bool refreshAccountToken();

    // Sign out: clears tokens, downgrades to Free.
    void logoutAccount();

    QString currentEmail()   const { return m_email; }
    bool    isLoggedIn()     const { return !m_accessToken.isEmpty(); }
    bool    isTokenExpired() const {
        return isLoggedIn() && m_tokenExpiry.isValid() &&
               QDateTime::currentDateTimeUtc() >= m_tokenExpiry;
    }

    // ── Legacy license key ────────────────────────────────────────────────

    // Validate and activate a license key (writes to OS keychain on success).
    bool activateLicense(const QString& key);

    // Remove stored license (downgrade to Free).
    void deactivateLicense();

    // ── API key encryption (DPAPI on Windows, XOR fallback) ──────────────
    // Used by ApiKeySettings and BackendLauncher to store/retrieve user API keys.
    static QByteArray encryptApiKey(const QString& value);
    static QString    decryptApiKey(const QByteArray& stored);

    // ── Daily generation counter (Free tier: max 5/day) ───────────────────

    int  dailyGenerationsRemaining() const;
    bool recordGeneration(const QString& modelUsed = "");

    // ── Feature gates ─────────────────────────────────────────────────────

    bool canGenerate()     const;
    bool canSplitStems6()  const { return isPro(); }
    bool canVocal()        const { return isPro(); }
    bool canMaster()       const { return isPro(); }
    bool canPromptCmd()    const { return isStudio(); }
    bool canCodeToMusic()  const { return isStudio(); }

    // ElevenLabs per-feature gates — returns true if user has quota remaining
    bool canElevenLabs(const QString& feature) const;

    // Convenience wrappers (call canElevenLabs internally)
    bool canElevenLabsMusic()      const { return canElevenLabs("music"); }
    bool canElevenLabsTTS()        const { return canElevenLabs("tts"); }
    bool canElevenLabsVoiceClone() const { return canElevenLabs("voice_clone"); }
    bool canElevenLabsSTS()        const { return canElevenLabs("sts"); }
    bool canElevenLabsSFX()        const { return canElevenLabs("sfx"); }
    bool canElevenLabsIsolate()    const { return canElevenLabs("voice_isolate"); }
    bool canElevenLabsTranscribe() const { return canElevenLabs("transcribe"); }
    bool canElevenLabsAlign()      const { return canElevenLabs("forced_align"); }
    bool canElevenLabsDub()        const { return canElevenLabs("dub"); }

    int  elFeatureRemaining(const QString& feature) const;
    int  elevenLabsDailyRemaining() const;
    bool recordElevenLabsCall(const QString& method = "");

Q_SIGNALS:
    void tierChanged(Tier newTier);
    void gracePeriodExpired();
    void loginStateChanged(bool loggedIn);

private:
    explicit LicenseManager(QObject* parent = nullptr);

    static LicenseManager* s_instance;

    Tier    m_activatedTier{Tier::Free};
    QDateTime m_lastValidatedAt;

    // ── Account-based auth state ──────────────────────────────────────────
    QString   m_email;
    QString   m_accessToken;
    QString   m_refreshToken;
    QDateTime m_tokenExpiry;

    // ── Legacy key state ──────────────────────────────────────────────────
    QString m_licenseKey;

    // ── Internal helpers ──────────────────────────────────────────────────

    bool validateHmac(const QString& key) const;

    // Account token persistence (QSettings, XOR-obfuscated)
    void saveAccountTokens();
    void loadAccountTokens();
    void clearAccountTokens();

    // Keychain abstraction ─────────────────────────────────────────────────
    void    loadFromKeychain();
    void    saveToKeychain(const QString& key);
    void    removeFromKeychain();

    // QSettings-based fallback (XOR-obfuscated)
    QString readSettingsKey() const;
    void    writeSettingsKey(const QString& key);

    // Validation timestamp helpers
    void      saveValidatedAt(const QDateTime& dt);
    QDateTime loadValidatedAt() const;
};
