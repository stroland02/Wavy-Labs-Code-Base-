#pragma once

#include <QObject>
#include <QString>
#include <QVariantMap>
#include <QVariantList>

#include "GenerationListModel.h"
#include "ChatMessageModel.h"

class AIClient;
class ModelManager;
class EngineAPI;

#include "../LicenseGate/LicenseManager.h"

// ---------------------------------------------------------------------------
// AIBackend — C++ backend exposed to QML via root context.
// Contains all AI business logic (generate, TTS, SFX, chat, etc.).
// QML pages call Q_INVOKABLE methods; results update Q_PROPERTY values.
// ---------------------------------------------------------------------------

class AIBackend : public QObject
{
    Q_OBJECT

    // ── Observable state for QML binding ────────────────────────────────────
    Q_PROPERTY(bool connected       READ isConnected    NOTIFY connectedChanged)
    Q_PROPERTY(bool generating      READ isGenerating   NOTIFY generatingChanged)
    Q_PROPERTY(int  dailyRemaining  READ dailyRemaining NOTIFY dailyRemainingChanged)
    Q_PROPERTY(bool isFreeUser      READ isFreeUser     NOTIFY tierChanged)
    Q_PROPERTY(bool isPro           READ isPro          NOTIFY tierChanged)
    Q_PROPERTY(bool isStudio        READ isStudio       NOTIFY tierChanged)
    Q_PROPERTY(QString userEmail    READ userEmail      NOTIFY loginStateChanged)
    Q_PROPERTY(bool   isLoggedIn    READ isLoggedIn     NOTIFY loginStateChanged)
    Q_PROPERTY(QString tierName     READ tierName       NOTIFY tierChanged)
    Q_PROPERTY(QString statusText   READ statusText     NOTIFY statusTextChanged)
    Q_PROPERTY(QString errorText    READ errorText      NOTIFY errorTextChanged)
    Q_PROPERTY(QStringList modelNames READ modelNames   NOTIFY modelsChanged)
    Q_PROPERTY(QStringList voiceNames READ voiceNames   NOTIFY voicesChanged)
    Q_PROPERTY(QVariantList voiceData READ voiceData     NOTIFY voicesChanged)
    Q_PROPERTY(QString transcribeResult READ transcribeResult NOTIFY transcribeResultChanged)
    Q_PROPERTY(QString mixResult        READ mixResult        NOTIFY mixResultChanged)
    Q_PROPERTY(QString consoleLog       READ consoleLog       NOTIFY consoleLogChanged)
    Q_PROPERTY(GenerationListModel* generations READ generations CONSTANT)
    Q_PROPERTY(ChatMessageModel* chatMessages   READ chatMessages CONSTANT)
    Q_PROPERTY(int currentPage READ currentPage WRITE setCurrentPage NOTIFY currentPageChanged)
    Q_PROPERTY(QVariantMap sessionContext READ sessionContext NOTIFY sessionContextChanged)
    Q_PROPERTY(QString     songSessionId READ songSessionId NOTIFY songSessionChanged)
    Q_PROPERTY(QVariantMap songMeta      READ songMeta      NOTIFY songMetaChanged)
    Q_PROPERTY(QString     activeGenre   READ activeGenre   NOTIFY activeGenreChanged)

public:
    explicit AIBackend(AIClient* client, ModelManager* modelManager,
                       QObject* parent = nullptr);

    /// Wire up the DAW engine so dawContext() can read existing MIDI notes.
    void setEngine(EngineAPI* engine) { m_engine = engine; }

    // ── Property getters ───────────────────────────────────────────────────
    bool isConnected() const;
    bool isGenerating() const { return m_generating; }
    int  dailyRemaining() const;
    bool isFreeUser() const;
    bool isPro() const;
    bool isStudio() const;
    QString userEmail()  const;
    bool    isLoggedIn() const;
    QString tierName()   const;
    Q_INVOKABLE void importDashAudio();
    QString statusText() const { return m_statusText; }
    QString errorText() const { return m_errorText; }
    QStringList modelNames() const { return m_modelNames; }
    QStringList voiceNames() const { return m_voiceNames; }
    QVariantList voiceData() const { return m_voiceData; }
    QString transcribeResult() const { return m_transcribeResult; }
    QString mixResult() const { return m_mixResult; }
    QString consoleLog() const { return m_consoleLog; }
    GenerationListModel* generations() const { return m_generations; }
    ChatMessageModel* chatMessages() const { return m_chatMessages; }
    int currentPage() const { return m_currentPage; }
    Q_INVOKABLE void setCurrentPage(int page);
    QVariantMap sessionContext() const { return m_sessionContext; }
    QString     songSessionId() const { return m_songSessionId; }
    QVariantMap songMeta()      const { return m_songMeta; }
    QString     activeGenre()   const { return m_activeGenre; }
    Q_INVOKABLE void setActiveGenre(const QString& genre);
    Q_INVOKABLE void setGenreMode(const QString& modeKey);

    // ── Music generation ───────────────────────────────────────────────────
    Q_INVOKABLE void generate(const QString& prompt, const QVariantMap& options);
    Q_INVOKABLE void generateStem(const QString& stemType, const QString& refPath,
                                   const QString& prompt);

    // ── Vocal / TTS ────────────────────────────────────────────────────────
    Q_INVOKABLE void textToSpeech(const QString& text, const QString& voiceId,
                                   const QString& model, double stability,
                                   double similarity);
    Q_INVOKABLE void speechToSpeech(const QString& audioPath, const QString& voiceId);
    Q_INVOKABLE void voiceClone(const QString& name, const QStringList& samplePaths);

    // ── SFX ────────────────────────────────────────────────────────────────
    Q_INVOKABLE void generateSFX(const QString& prompt, double duration);

    // ── Mix / Master ───────────────────────────────────────────────────────
    Q_INVOKABLE void analyzeMix();
    Q_INVOKABLE void masterAudio();
    Q_INVOKABLE void autoMix();

    // ── Tools ──────────────────────────────────────────────────────────────
    Q_INVOKABLE void voiceIsolate(const QString& audioPath);
    Q_INVOKABLE void transcribe(const QString& audioPath, const QString& lang);
    Q_INVOKABLE void forcedAlign(const QString& audioPath, const QString& text);
    Q_INVOKABLE void dubAudio(const QString& audioPath,
                               const QString& sourceLang, const QString& targetLang);
    Q_INVOKABLE void replaceSection(const QString& audioPath, double startSec,
                                     double endSec, const QString& prompt);
    Q_INVOKABLE void audioToMidi(const QString& audioPath);

    // ── Code ───────────────────────────────────────────────────────────────
    Q_INVOKABLE void runCode(const QString& code, const QString& mode);

    // ── Chat ───────────────────────────────────────────────────────────────
    Q_INVOKABLE void sendChat(const QString& text);
    Q_INVOKABLE void clearChat();
    Q_INVOKABLE void chatGenerate(const QString& prompt);

    // ── Compose agent ──────────────────────────────────────────────────────
    Q_INVOKABLE void composeArrangement(const QString& prompt, const QString& mode,
                                         const QString& sessionId,
                                         const QVariantMap& dawCtx,
                                         const QVariantMap& instrumentOverrides = {});
    Q_INVOKABLE void composeTrack(const QString& prompt, const QString& role,
                                   const QVariantMap& instrOverride = {},
                                   const QVariantMap& section = {},
                                   const QString& seedMidiSlug = {});
    Q_INVOKABLE void clearSongSession();
    Q_INVOKABLE void getInstrumentChoices();
    Q_INVOKABLE void getBitmidiInspirations(const QString& genre);
    Q_INVOKABLE void askAboutMidiDatabase(const QString& dbName);
    Q_INVOKABLE void browseDataset(const QString& db, const QString& query, int offset);
    Q_INVOKABLE void downloadLibraryFile(const QString& db, const QString& fileId,
                                         const QString& title,
                                         const QString& plugin = QString());
    Q_INVOKABLE void startMidicapsDownload();
    Q_INVOKABLE void checkMidicapsStatus();
    Q_INVOKABLE void testDatabases();
    Q_INVOKABLE QString newSessionId() const;
    Q_INVOKABLE QVariantMap dawContext() const;
    Q_INVOKABLE void regenerateBar(const QString& sessionId, const QString& partName,
                                    int barIndex, const QVariantMap& ctx);

    // ── Session context lock ────────────────────────────────────────────────
    Q_INVOKABLE void setSessionContext(const QVariantMap& ctx);

    // ── Chord suggestions ──────────────────────────────────────────────────
    Q_INVOKABLE void getChordSuggestions(const QString& prompt, const QVariantMap& ctx);
    Q_INVOKABLE void insertChord(const QVariantList& pitches, int barIndex);

    // ── Beat builder ───────────────────────────────────────────────────────
    Q_INVOKABLE void buildBeat(const QString& prompt, const QVariantMap& ctx);
    Q_INVOKABLE void insertBeatPattern(const QVariantList& rows, int bpm, int bars);

    // ── Genre FX / Pitch / Arp / Granular (v0.9.5) ───────────────────────
    Q_INVOKABLE void applyTrackFx(const QString& audioPath,
                                   const QString& genre,
                                   const QString& role = QStringLiteral("any"));
    Q_INVOKABLE void pitchCorrectAudio(const QString& audioPath,
                                        const QString& key   = QStringLiteral("C"),
                                        const QString& scale = QStringLiteral("minor"),
                                        double strength = 0.8);
    Q_INVOKABLE void generateArpeggio(const QVariantList& chordNotes,
                                       int bpm = 120,
                                       const QString& style = QStringLiteral("16th"),
                                       int bars = 2);
    Q_INVOKABLE void granularChopAudio(const QString& audioPath,
                                        double grainMs     = 80.0,
                                        double pitchSpread = 0.3,
                                        double density     = 0.5);

    // ── NCS Toolkit (v0.9.9) ──────────────────────────────────────────────
    Q_INVOKABLE void generateRiser(const QString& riserType, int bpm, double bars);
    Q_INVOKABLE void applySidechainPump(const QString& audioPath, int bpm,
                                        double depth, double releaseMs);
    Q_INVOKABLE void getNcsSongStructure(const QString& genre, const QString& key,
                                         const QString& scale, int bpm);

    // ── Stem extraction ────────────────────────────────────────────────────
    Q_INVOKABLE void extractStems(const QString& audioPath, const QString& mode);
    Q_INVOKABLE void insertStemFile(const QString& stemPath, const QString& stemName);
    Q_INVOKABLE void previewAudio(const QString& path);
    /// Returns [{name, path}] for every SampleTrack in the Song Editor with audio.
    Q_INVOKABLE QVariantList getSongAudioTracks() const;

    // ── SoundFont Manager ────────────────────────────────────────────────
    Q_INVOKABLE QVariantList getAvailableSoundfonts();
    Q_INVOKABLE void downloadSoundfont(const QString& name);
    Q_INVOKABLE void setDefaultSoundfont(const QString& path);

    // ── Genre instrument config ──────────────────────────────────────────
    Q_INVOKABLE QVariantList getAvailablePlugins();
    Q_INVOKABLE QStringList  getPresetsForPlugin(const QString& plugin);
    Q_INVOKABLE bool         addInstrumentTrack(const QString& pluginName, const QString& trackName = {},
                                                const QString& preset = {}, const QString& samplePath = {});
    Q_INVOKABLE QVariantList getGenreInstrumentConfig(const QString& genreKey);
    Q_INVOKABLE void saveGenreInstrumentOverride(const QString& genreKey,
                                                  const QVariantList& instrSlots);
    Q_INVOKABLE void resetGenreInstrumentDefaults(const QString& genreKey);

    // ── Instrument Catalog (v0.14.0) ─────────────────────────────────────
    Q_INVOKABLE void searchInstruments(const QString& query = {},
                                        const QString& category = {},
                                        const QString& source = {},
                                        int offset = 0, int limit = 50);
    Q_INVOKABLE void getInstrumentDetails(const QString& instrumentId);
    Q_INVOKABLE void downloadInstrumentPack(const QString& packName);
    Q_INVOKABLE void listInstrumentPacks();

    // ── Audio editing (v0.12.0) ─────────────────────────────────────────────
    Q_INVOKABLE void extendAudio(const QString& audioPath, double extendSec,
                                  const QString& prompt = {});

    // ── MIDI AI tools (v0.12.0) ──────────────────────────────────────────────
    Q_INVOKABLE void midiExtend(const QString& midiPath, int barsToAdd,
                                 const QString& prompt = {});
    Q_INVOKABLE void midiRecompose(const QString& midiPath, int startBar,
                                    int endBar, const QString& style = {});
    Q_INVOKABLE void midiLayer(const QString& midiPath, const QString& layerType,
                                const QString& key = {}, const QString& scale = {});

    // ── AI FX Chain (v0.12.0) ────────────────────────────────────────────────
    Q_INVOKABLE void textToFxChain(const QString& prompt,
                                    const QString& audioPath = {});

    // ── Reference track analysis (v0.12.0) ───────────────────────────────────
    Q_INVOKABLE void analyzeReference(const QString& audioPath);
    Q_INVOKABLE void analyzeSongMaterial();

    // ── MIDI import confirmation ────────────────────────────────────────────
    Q_INVOKABLE void confirmMidiImport(bool useMidiBpm, bool useGenrePresets);
    Q_INVOKABLE void cancelMidiImport();

    // ── Mix fix dispatch ───────────────────────────────────────────────────
    Q_INVOKABLE void applyMixFix(const QVariantMap& fixAction);

    // ── API Keys ───────────────────────────────────────────────────────────
    // Push updated API keys to the running Python backend.
    Q_INVOKABLE void updateApiKeys(const QVariantMap& keys);

    // ── Console ────────────────────────────────────────────────────────────
    Q_INVOKABLE void clearConsole();
    void appendLog(const QString& msg);

    // ── Misc ───────────────────────────────────────────────────────────────
    Q_INVOKABLE void checkStatus();
    Q_INVOKABLE void savePersona(const QString& name, const QString& voiceId,
                                  double stability, double similarity);
    Q_INVOKABLE QString browseAudioFile();
    Q_INVOKABLE QStringList browseAudioFiles();
    Q_INVOKABLE void insertGeneration(int index);

    // ── Dashboard ──────────────────────────────────────────────────────────
    Q_INVOKABLE QStringList recentProjects() const;
    Q_INVOKABLE void openProject(const QString& path);

Q_SIGNALS:
    void connectedChanged();
    void generatingChanged();
    void dailyRemainingChanged();
    void tierChanged();
    void statusTextChanged();
    void errorTextChanged();
    void modelsChanged();
    void voicesChanged();
    void transcribeResultChanged();
    void mixResultChanged();
    void consoleLogChanged();

    void currentPageChanged(int page);
    void singerWarning(const QString& message, const QVariantMap& pendingOpts);

    void loginStateChanged();
    void switchToEditorRequested();

    // Forwarded to AIPanel/main.cpp
    void projectOpenRequested(const QString& path);
    void audioReady(const QString& trackName, const QString& audioPath, double duration);
    void stemsReady(const QStringList& stemPaths, const QStringList& stemNames);
    void codeTracksReady(const QStringList& audioPaths, const QStringList& trackNames);
    void actionsReady(const QVariantList& actions);
    void autoMixReady(const QVariantList& suggestions);
    void midiFileReady(const QString& midiPath);
    void insertRequested(const QString& audioPath, const QString& trackName,
                         const QVariantList& sections);

    // Compose agent outputs
    void composeReady(const QVariantList& parts, const QString& explanation);
    void composeFillReady(const QString& midiPath);
    void instrumentChoicesReady(const QVariantMap& choices);
    void bitmidiInspirationsReady(const QVariantList& titles);
    void regenerateBarReady(const QString& trackName, int barIndex,
                            const QVariantList& notes, const QString& midiPath);

    // Session context
    void sessionContextChanged(const QVariantMap& ctx);
    void activeGenreChanged(const QString& genre);

    // Song builder session
    void songSessionChanged();
    void songMetaChanged();

    // Stem extraction
    void stemsExtracted(const QVariantList& stems);

    // Genre instrument config
    void genreInstrumentConfigChanged(const QString& genreKey);

    // SoundFont Manager
    void soundfontDownloaded(const QString& name, const QString& path);

    // NCS Toolkit (v0.9.9)
    void riserReady(const QString& audioPath);
    void sidechainReady(const QString& audioPath);
    void ncsSongStructureReady(const QVariantList& sections);

    // MIDI import confirmation
    void midiImportConfirm(const QString& title, int midiBpm, int songBpm,
                           const QString& activeGenre, bool hasGmData);

    // Reference / Song material analysis (v0.12.0)
    void referenceAnalyzed(const QVariantMap& analysis);
    void songMaterialAnalyzed(const QVariantMap& analysis);
    void fxChainApplied(const QVariantList& fxChain, const QString& audioPath);

    // Instrument Catalog (v0.14.0)
    void instrumentSearchResults(const QVariantList& items, int total, bool hasMore);
    void instrumentDetailsReady(const QVariantMap& details);
    void instrumentPackDownloaded(const QString& name, const QString& path);
    void instrumentPacksListed(const QVariantList& packs);

    // Library dataset browser
    void datasetBrowseReady(QVariantList items, int total, bool hasMore, bool append);
    void libraryFileImported(QString title);
    void midicapsStatusUpdate(QString status, double progress, int filesExtracted,
                              qlonglong bytesDownloaded, qlonglong totalBytes);

private:
    void setGenerating(bool busy);
    void setError(const QString& msg);
    void setStatus(const QString& msg);
    void refreshModels();
    void refreshVoices();
    void _updateSongMeta(const QVariantMap& result);

    AIClient*     m_client;
    ModelManager* m_modelManager;
    EngineAPI*    m_engine{nullptr};
    GenerationListModel* m_generations;
    ChatMessageModel*    m_chatMessages;

    bool        m_generating{false};
    int         m_currentPage{0};
    QVariantMap m_sessionContext;
    QString     m_songSessionId;
    QVariantMap m_songMeta;
    QString     m_activeGenre;
    QString     m_statusText;
    QString     m_errorText;
    QStringList m_modelNames;
    QStringList m_modelIds;
    QStringList m_voiceNames;
    QVariantList m_voiceData;
    QString     m_transcribeResult;
    QString     m_mixResult;
    QString     m_consoleLog;
    QString     m_lastAudioPath;

    // MIDI import confirmation pending state
    QVariantList m_pendingGenreParts;
    QVariantList m_pendingGmParts;
    int          m_pendingMidiBpm{0};
    QString      m_pendingImportTitle;
};
