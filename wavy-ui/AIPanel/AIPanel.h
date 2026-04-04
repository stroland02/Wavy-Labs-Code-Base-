#pragma once

#include <QAtomicInt>
#include <QCheckBox>
#include <QDialog>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QLineEdit>
#include <QList>
#include <QListWidget>
#include <QMdiSubWindow>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QComboBox>
#include <QSlider>
#include <QSpinBox>
#include <QStackedWidget>
#include <QString>
#include <QTextEdit>
#include <QToolButton>
#include <QVariantMap>
#include <QVariantList>
#include <QWidget>

class AIClient;
class ModelManager;
class GenerationHistoryWidget;
class CodeEditor;
class PromptBar;

// Forward include for Tier enum used in onTierChanged slot
#include "../LicenseGate/LicenseManager.h"

// ---------------------------------------------------------------------------
// AIPanel — main AI generation MDI sub-window
// Tabs: Generate | Vocal/TTS | SFX | Mix/Master | Tools | Code | Prompt | Console
// ---------------------------------------------------------------------------

class AIPanel : public QWidget
{
    Q_OBJECT

public:
    explicit AIPanel(AIClient* client,
                     ModelManager* modelManager,
                     QWidget* parent = nullptr);

    // Wrap this panel inside an MDI sub-window.
    QMdiSubWindow* asMdiSubWindow(QWidget* mdiArea);

    // Pass current DAW context to the Prompt tab so the LLM has track/tempo info.
    void setPromptContext(const QVariantMap& ctx);

    // Removes the nav bar from AIPanel's internal layout and returns it.
    // Call once from main.cpp to embed it in the dock wrapper outside the panel.
    QWidget* detachNavBar();

    // Remove and return the page widget at position idx from the internal stack.
    // Always call with idx=0 in a loop — indices shift after each removal.
    // Used by main.cpp to extract pages for embedding in the LMMS left sidebar.
    QWidget* takePage(int idx);

Q_SIGNALS:
    // Emitted when the backend returns a generated audio file.
    void audioReady(const QString& trackName, const QString& audioPath, double duration);

    // Emitted when stems are split and ready to insert as separate tracks.
    void stemsReady(const QStringList& stemPaths, const QStringList& stemNames);

    // Emitted when Code-to-Music produces audio tracks for the timeline.
    void codeTracksReady(const QStringList& audioPaths, const QStringList& trackNames);

    // Emitted when the Prompt tab parses actions for the DAW.
    void actionsReady(const QVariantList& actions);

    // Emitted when AI Auto-Mix completes — carry mixer suggestions for wiring.
    void autoMixReady(const QVariantList& suggestions);

    // Emitted when Audio-to-MIDI or promptToMidi produces a MIDI file.
    void midiFileReady(const QString& midiPath);

    // Emitted when user clicks "+ Insert" on a generation (may include section structure).
    void insertRequested(const QString& audioPath, const QString& trackName, const QVariantList& sections);

    // Emitted when the user collapses/expands the panel by clicking the active nav icon.
    void panelCollapsed();
    void panelExpanded();

public Q_SLOTS:
    // Append a timestamped line to the Console tab.
    void appendLog(const QString& msg);

    // Switch to a named page: "generate","vocal","sfx","mix","tools","code","chat","console"
    void navigateTo(const QString& page);

    // Returns the name of the currently visible page
    QString currentPage() const;

private Q_SLOTS:
    void onGenerateClicked();
    void onGenerateMultiClicked();        // "Generate x3" -- fires 3 attempts
    void onStemSplitClicked();
    void onAnalyzeClicked();
    void onMasterClicked();
    void onGenerationFinished(bool ok, const QVariantMap& result);
    void onStemFinished(bool ok, const QVariantMap& result);
    void onAnalyzeFinished(bool ok, const QVariantMap& result);
    void onMasterFinished(bool ok, const QVariantMap& result);
    void onModelStatusChanged(bool backendConnected);
    void updateDailyCounter(int remaining);
    void populateModelCombo();
    void onTierChanged(Tier newTier);
    void onCodeTracksReady(const QVariantList& trackDefs,
                           const QString& midiPath,
                           const QStringList& audioPaths);
    // ElevenLabs slots
    void onTTSClicked();
    void onSTSClicked();
    void onVoiceCloneClicked();
    void onSFXClicked();
    void onVoiceIsolateClicked();
    void onTranscribeClicked();
    void onForcedAlignClicked();
    void onDubClicked();
    void onTTSFinished(bool ok, const QVariantMap& result);
    void onSTSFinished(bool ok, const QVariantMap& result);
    void onVoiceCloneFinished(bool ok, const QVariantMap& result);
    void onSFXFinished(bool ok, const QVariantMap& result);
    void onVoiceIsolateFinished(bool ok, const QVariantMap& result);
    void onTranscribeFinished(bool ok, const QVariantMap& result);
    void onForcedAlignFinished(bool ok, const QVariantMap& result);
    void onDubFinished(bool ok, const QVariantMap& result);
    void populateVoiceCombo();
    // Code tab (non-WebEngine path)
    void onPlainCodeRunClicked();
    void onPlainCodeConvertFinished(bool ok, const QVariantMap& result);
    // Chat tab
    void onChatSend();
    void onChatFinished(bool ok, const QVariantMap& result);
    // Suno-inspired feature slots
    void onGenerateStemClicked();
    void onGenerateStemFinished(bool ok, const QVariantMap& result);
    void onReplaceSectionClicked();
    void onReplaceSectionFinished(bool ok, const QVariantMap& result);
    void onAudioToMidiClicked();
    void onAudioToMidiFinished(bool ok, const QVariantMap& result);
    void onExtendMusicClicked();
    void onExtendMusicFinished(bool ok, const QVariantMap& result);
    void onSavePersonaClicked();
    void onLoadPersonasFinished(bool ok, const QVariantMap& result);
    void onAutoMixClicked();
    void onAutoMixFinished(bool ok, const QVariantMap& result);
    void onCheckStatusClicked();

private:
    void buildUI();
    void buildMusicTab(QWidget* tab);
    void buildVocalTab(QWidget* tab);
    void buildSFXTab(QWidget* tab);
    void buildMixTab(QWidget* tab);
    void buildToolsTab(QWidget* tab);
    void buildCodeTab(QWidget* tab);
    void buildPromptTab(QWidget* tab);
    void buildConsoleTab(QWidget* tab);
    void setGenerating(bool busy);
    void showError(const QString& msg);
    QVariantMap collectMusicParams() const;
    // Shared handler for ElevenLabs slots that produce a single audio_path output.
    void finishElevenLabsAudio(bool ok, const QVariantMap& result,
                               const QString& trackName, const QString& elFeature);
    // Append a message bubble to the chat display.
    void appendChatBubble(const QString& role, const QString& text);

    AIClient*                m_client{nullptr};
    ModelManager*            m_modelManager{nullptr};

    // ── NavBar + Stack (replaces QTabWidget) ─────────────────────────────────
    QWidget*                 m_navBar{nullptr};
    QStackedWidget*          m_pageStack{nullptr};
    // Nav buttons — index matches page index in m_pageStack
    static constexpr int     kPageCount = 7;
    QToolButton*             m_navBtns[kPageCount]{};
    // Page indices
    enum Page { Generate=0, Vocal, SFX, Mix, Tools, Chat, Console };

    // ── Music tab ────────────────────────────────────────────────────────────
    QTextEdit*               m_promptEdit{nullptr};
    QComboBox*               m_modelCombo{nullptr};

    QComboBox*               m_genreCombo{nullptr};
    QComboBox*               m_tempoCombo{nullptr};
    QComboBox*               m_keyCombo{nullptr};
    QComboBox*               m_durationCombo{nullptr};
    QComboBox*               m_lyricsCombo{nullptr};
    QTextEdit*               m_customLyricsEdit{nullptr};
    QCheckBox*                m_sectionStructureChk{nullptr};
    QPushButton*              m_generateBtn{nullptr};
    QPushButton*             m_generateMultiBtn{nullptr};  // "Generate ×3"
    QProgressBar*            m_progressBar{nullptr};
    QLabel*                  m_statusLabel{nullptr};
    QLabel*                  m_dailyCounterLabel{nullptr};
    GenerationHistoryWidget* m_history{nullptr};

    // Prompt card quick options (time + lyrics), synced with Advanced
    QComboBox*               m_promptTimeCombo{nullptr};
    QComboBox*               m_promptLyricsCombo{nullptr};

    // ── Vocal/TTS tab (ElevenLabs) ──────────────────────────────────────────
    QStackedWidget*          m_vocalStack{nullptr};
    // TTS page
    QTextEdit*               m_ttsTextEdit{nullptr};
    QComboBox*               m_voiceCombo{nullptr};
    QComboBox*               m_ttsModelCombo{nullptr};
    QSlider*                 m_stabilitySlider{nullptr};
    QSlider*                 m_similaritySlider{nullptr};
    QPushButton*             m_ttsBtn{nullptr};
    // STS page
    QLabel*                  m_stsFileLabel{nullptr};
    QString                  m_stsFilePath;
    QComboBox*               m_stsVoiceCombo{nullptr};
    QPushButton*             m_stsBtn{nullptr};
    // Voice Clone page
    QLineEdit*               m_cloneNameEdit{nullptr};
    QListWidget*             m_cloneFileList{nullptr};
    QPushButton*             m_cloneBtn{nullptr};
    QLabel*                  m_cloneResultLabel{nullptr};
    // ── SFX tab ──────────────────────────────────────────────────────────────
    QTextEdit*               m_sfxPromptEdit{nullptr};
    QSlider*                 m_sfxDurationSlider{nullptr};
    QLabel*                  m_sfxDurationLabel{nullptr};
    QPushButton*             m_sfxBtn{nullptr};

    // ── Mix/Master tab ────────────────────────────────────────────────────────
    QLabel*                  m_mixInputLabel{nullptr};
    QPushButton*             m_analyzeBtn{nullptr};
    QPushButton*             m_masterBtn{nullptr};
    QLabel*                  m_mixResultLabel{nullptr};

    // ── Tools tab (ElevenLabs) ──────────────────────────────────────────────
    QStackedWidget*          m_toolsStack{nullptr};
    // Voice Isolator page
    QLabel*                  m_isolateFileLabel{nullptr};
    QString                  m_isolateFilePath;
    QPushButton*             m_isolateBtn{nullptr};
    // Transcribe page
    QLabel*                  m_transcribeFileLabel{nullptr};
    QString                  m_transcribeFilePath;
    QComboBox*               m_transcribeLangCombo{nullptr};
    QPushButton*             m_transcribeBtn{nullptr};
    QTextEdit*               m_transcribeResult{nullptr};
    // Forced Alignment page
    QLabel*                  m_alignFileLabel{nullptr};
    QString                  m_alignFilePath;
    QTextEdit*               m_alignTextEdit{nullptr};
    QPushButton*             m_alignBtn{nullptr};
    QLabel*                  m_alignResultLabel{nullptr};
    // AI Dubbing page
    QLabel*                  m_dubFileLabel{nullptr};
    QString                  m_dubFilePath;
    QComboBox*               m_dubSourceLangCombo{nullptr};
    QComboBox*               m_dubTargetLangCombo{nullptr};
    QPushButton*             m_dubBtn{nullptr};

    // ── Code-to-Music tab ─────────────────────────────────────────────────────
    CodeEditor*              m_codeEditor{nullptr};

    // ── Prompt / Chat tab ────────────────────────────────────────────────────
    PromptBar*               m_promptBar{nullptr};   // kept for Ctrl+K bar
    QTextEdit*               m_chatDisplay{nullptr}; // read-only HTML chat log
    QLineEdit*               m_chatInput{nullptr};   // user input field
    QPushButton*             m_chatSendBtn{nullptr};
    QVariantList             m_chatHistory;          // [{role,content}, ...]

    // ── Console tab ──────────────────────────────────────────────────────────
    QPlainTextEdit*          m_consoleEdit{nullptr};
    // Non-WebEngine fallback widgets (used when WAVY_WEBENGINE is not defined)
    QPlainTextEdit*          m_codePlainEdit{nullptr};
    QComboBox*               m_codeModeCombo{nullptr};
    QPushButton*             m_codeRunBtn{nullptr};
    QListWidget*             m_codeOutputList{nullptr};
    QLabel*                  m_codeStatusLabel{nullptr};

    // ── Auto-split stems ──────────────────────────────────────────────────────
    QCheckBox*               m_autoSplitChk{nullptr};
    QComboBox*               m_stemCountCombo{nullptr};
    QComboBox*               m_advancedStemGenerationCombo{nullptr};  // Advanced page: Off / On (2/4/6 stems)

    // ── Generate tab — Inspo + Influence + Extend ─────────────────────────────
    QListWidget*             m_inspoList{nullptr};
    QPushButton*             m_inspoAddBtn{nullptr};
    QSlider*                 m_influenceSlider{nullptr};
    QLabel*                  m_influenceLabel{nullptr};
    QPushButton*             m_extendBtn{nullptr};       // removed from UI; kept for optional reuse
    QSpinBox*                m_extendSecSpin{nullptr};  // ditto

    // ── Generate tab — Advanced settings (collapsible) ─────────────────────────
    QWidget*                 m_advancedMusicPanel{nullptr};
    QStackedWidget*         m_generateTabStack{nullptr};  // Simple | Advanced | Sounds
    QComboBox*               m_stemTypeCombo{nullptr};
    QLabel*                  m_stemRefLabel{nullptr};
    QString                  m_stemRefPath;
    QPushButton*             m_stemRefBtn{nullptr};
    QPushButton*             m_generateStemBtn{nullptr};

    // ── Tools tab — Replace Section (page 4) ──────────────────────────────────
    QLabel*                  m_replaceFileLabel{nullptr};
    QString                  m_replaceFilePath;
    QDoubleSpinBox*          m_replaceStartSpin{nullptr};
    QDoubleSpinBox*          m_replaceEndSpin{nullptr};
    QTextEdit*               m_replacePromptEdit{nullptr};
    QPushButton*             m_replaceBtn{nullptr};

    // ── Tools tab — Audio to MIDI (page 5) ───────────────────────────────────
    QLabel*                  m_a2mFileLabel{nullptr};
    QString                  m_a2mFilePath;
    QPushButton*             m_a2mBtn{nullptr};
    QLabel*                  m_a2mResultLabel{nullptr};

    // ── Vocal tab — Personas ──────────────────────────────────────────────────
    QComboBox*               m_personaCombo{nullptr};
    QLineEdit*               m_personaNameEdit{nullptr};
    QPushButton*             m_personaSaveBtn{nullptr};

    // ── Mix tab — Auto-Mix ────────────────────────────────────────────────────
    QPushButton*             m_autoMixBtn{nullptr};
    QLabel*                  m_autoMixResultLabel{nullptr};

    // ── Multi-attempt state ───────────────────────────────────────────────────
    // Accumulates up to 3 results; when full, opens the comparison dialog.
    QList<QVariantMap>       m_multiResults;
    QAtomicInt               m_multiPending{0};

    void showMultiPickDialog();

    // ── State ────────────────────────────────────────────────────────────────
    QString                  m_lastAudioPath;
    bool                     m_isFreeUser{true};  // set false when Pro/Studio license validated
};
