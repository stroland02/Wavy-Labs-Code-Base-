#include "AIBackend.h"
#include "GenerationListModel.h"
#include "ChatMessageModel.h"
#include "GenreModes.h"
#include "GmInstrumentMap.h"
#include "../IPC/AIClient.h"
#include "../LicenseGate/LicenseManager.h"
#include "../ModelManager/ModelManager.h"
#include "../EngineAPI/EngineAPI.h"

#ifdef WAVY_LMMS_CORE
#include "ConfigManager.h"
#include "../EngineAPI/LmmsEngine.h"
#endif

#include <QCoreApplication>
#include <QDateTime>
#include <QDebug>
#include <QElapsedTimer>
#include <QDesktopServices>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaObject>
#include <QRegularExpression>
#include <QSettings>
#include <QUrl>
#include <QUuid>

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

AIBackend::AIBackend(AIClient* client, ModelManager* modelManager, QObject* parent)
    : QObject(parent)
    , m_client(client)
    , m_modelManager(modelManager)
    , m_generations(new GenerationListModel(this))
    , m_chatMessages(new ChatMessageModel(this))
{
    connect(m_client, &AIClient::connected, this, [this]() {
        emit connectedChanged();
        refreshModels();
        refreshVoices();
    });
    connect(m_client, &AIClient::disconnected, this, [this]() {
        emit connectedChanged();
    });
    connect(m_modelManager, &ModelManager::modelStatusChanged,
            this, &AIBackend::refreshModels);
    connect(LicenseManager::instance(), &LicenseManager::tierChanged,
            this, [this]() {
                emit tierChanged();
                emit dailyRemainingChanged();
            });
    connect(LicenseManager::instance(), &LicenseManager::loginStateChanged,
            this, [this](bool) { emit loginStateChanged(); });

    refreshModels();
    refreshVoices();

    // Welcome message
    m_chatMessages->addMessage("wavy",
        "Hey! I'm Wavy \xF0\x9F\x8E\xB6\n\n"
        "I'm your AI music-making assistant. I can help you:\n"
        "\xE2\x80\xA2 Compose full arrangements and melodies\n"
        "\xE2\x80\xA2 Build chord progressions and beat patterns\n"
        "\xE2\x80\xA2 Generate vocals, stems, and sound effects\n"
        "\xE2\x80\xA2 Mix and master your tracks\n"
        "\xE2\x80\xA2 Answer music theory questions\n\n"
        "What are we making today?");
}

// ---------------------------------------------------------------------------
// Property getters
// ---------------------------------------------------------------------------

bool AIBackend::isConnected() const { return m_client->isConnected(); }

int AIBackend::dailyRemaining() const
{
    return LicenseManager::instance()->dailyGenerationsRemaining();
}

bool AIBackend::isFreeUser() const
{
    return !LicenseManager::instance()->isPro();
}

bool AIBackend::isPro() const
{
    auto t = LicenseManager::instance()->tier();
    return t == Tier::Pro || t == Tier::Studio;
}

bool AIBackend::isStudio() const
{
    return LicenseManager::instance()->tier() == Tier::Studio;
}

QString AIBackend::userEmail() const
{
    return LicenseManager::instance()->currentEmail();
}

bool AIBackend::isLoggedIn() const
{
    return LicenseManager::instance()->isLoggedIn();
}

QString AIBackend::tierName() const
{
    switch (LicenseManager::instance()->tier()) {
        case Tier::Pro:    return "Pro";
        case Tier::Studio: return "Studio";
        default:           return "Free";
    }
}

void AIBackend::importDashAudio()
{
    const QString path = browseAudioFile();
    if (path.isEmpty()) return;
    emit audioReady("Imported", path, 0.0);
    emit switchToEditorRequested();
}

// ---------------------------------------------------------------------------
// State helpers
// ---------------------------------------------------------------------------

void AIBackend::setCurrentPage(int page)
{
    if (page < 0 || page > 6 || m_currentPage == page) return;
    m_currentPage = page;
    emit currentPageChanged(page);
}

void AIBackend::setGenerating(bool busy)
{
    if (m_generating == busy) return;
    m_generating = busy;
    emit generatingChanged();
}

void AIBackend::setError(const QString& msg)
{
    m_errorText = msg;
    emit errorTextChanged();
}

void AIBackend::setStatus(const QString& msg)
{
    m_statusText = msg;
    emit statusTextChanged();
}

// ---------------------------------------------------------------------------
// Music generation
// ---------------------------------------------------------------------------

void AIBackend::generate(const QString& prompt, const QVariantMap& options)
{
    auto* lm = LicenseManager::instance();
    const QString model = options.value("model").toString();

    if (model == "elevenlabs_music") {
        if (!lm->canElevenLabsMusic()) {
            setError("ElevenLabs Music daily limit reached.");
            return;
        }
    } else if (!lm->canGenerate()) {
        setError("Daily generation limit reached. Configure your API key in Edit → Settings.");
        return;
    }

    if (prompt.trimmed().isEmpty()) {
        setError("Please enter a music description.");
        return;
    }

    setGenerating(true);
    setError({});

    QVariantMap params = options;
    params["prompt"] = prompt.trimmed();
    params["tier"]   = lm->isPro() ? "pro" : "free";

    m_client->generateMusic(params, [this, prompt, params](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, prompt, params]() {
            setGenerating(false);
            if (!ok || result.contains("error")) {
                if (result.value("singer_warning").toBool()) {
                    emit singerWarning(result.value("error").toString(), params);
                    return;
                }
                setError(result.value("error").toString());
                return;
            }

            const QString path     = result.value("audio_path").toString();
            const double  duration = result.value("duration").toDouble();
            const QVariantList sections = result.value("sections").toList();

            m_lastAudioPath = path;
            m_generations->addEntry(prompt.trimmed(), path, duration, sections);

            auto* lm = LicenseManager::instance();
            const QString modelUsed = result.value("model_used").toString();
            if (modelUsed.startsWith("elevenlabs"))
                lm->recordElevenLabsCall("music");
            else
                lm->recordGeneration(modelUsed);
            emit dailyRemainingChanged();

            // Check auto-stem split
            int numStems = result.value("auto_stems", 0).toInt();
            if (numStems > 0) {
                setStatus(QString("Splitting into %1 stems...").arg(numStems));
                setGenerating(true);
                QVariantMap p;
                p["audio_path"] = path;
                p["stems"]      = numStems;
                m_client->splitStems(p, [this](bool ok2, const QVariantMap& r) {
                    QMetaObject::invokeMethod(this, [this, ok2, r]() {
                        setGenerating(false);
                        if (!ok2) { setError("Stem split failed."); return; }
                        const QVariantList stems = r.value("stems").toList();
                        QStringList paths, names;
                        for (const auto& s : stems) {
                            auto m = s.toMap();
                            paths << m.value("path").toString();
                            names << m.value("name").toString();
                        }
                        emit stemsReady(paths, names);
                    }, Qt::QueuedConnection);
                });
                return;
            }

            emit audioReady("AI Generated", path, duration);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::generateStem(const QString& stemType, const QString& refPath,
                              const QString& prompt)
{
    setGenerating(true);
    QVariantMap p;
    p["stem_type"] = stemType;
    if (!refPath.isEmpty()) p["reference_path"] = refPath;
    if (!prompt.isEmpty())  p["prompt"] = prompt;

    m_client->generateStem(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            const QString path = result.value("audio_path").toString();
            const double dur   = result.value("duration", 0.0).toDouble();
            emit audioReady("AI Stem", path, dur);
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Vocal / TTS
// ---------------------------------------------------------------------------

void AIBackend::textToSpeech(const QString& text, const QString& voiceId,
                              const QString& model, double stability,
                              double similarity)
{
    if (text.trimmed().isEmpty()) { setError("Enter text to synthesize."); return; }
    setGenerating(true);

    QVariantMap p;
    p["text"]       = text.trimmed();
    p["voice_id"]   = voiceId;
    p["model_id"]   = model;
    p["stability"]  = stability;
    p["similarity"] = similarity;

    m_client->elevenLabsTTS(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            const QString path = result.value("audio_path").toString();
            emit audioReady("TTS", path, result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::speechToSpeech(const QString& audioPath, const QString& voiceId)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;
    p["voice_id"]   = voiceId;

    m_client->elevenLabsSTS(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            emit audioReady("Speech-to-Speech", result.value("audio_path").toString(),
                            result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::voiceClone(const QString& name, const QStringList& samplePaths)
{
    if (name.isEmpty() || samplePaths.isEmpty()) {
        setError("Provide a name and at least one audio sample.");
        return;
    }
    setGenerating(true);

    QVariantMap p;
    p["name"] = name;
    QVariantList files;
    for (const auto& f : samplePaths) files.append(f);
    p["files"] = files;

    m_client->elevenLabsVoiceClone(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            setStatus("Voice cloned: " + result.value("voice_id").toString());
            refreshVoices();
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// SFX
// ---------------------------------------------------------------------------

void AIBackend::generateSFX(const QString& prompt, double duration)
{
    if (prompt.trimmed().isEmpty()) { setError("Describe the sound effect."); return; }
    setGenerating(true);

    QVariantMap p;
    p["text"]          = prompt.trimmed();
    p["duration_seconds"] = duration;

    m_client->elevenLabsSFX(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            emit audioReady("SFX", result.value("audio_path").toString(),
                            result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Mix / Master
// ---------------------------------------------------------------------------

void AIBackend::analyzeMix()
{
    setGenerating(true);
    m_client->analyzeTrack({}, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            m_mixResult = result.value("analysis").toString();
            emit mixResultChanged();

            // If the result has structured suggestions, add as FixCardWidget in chat
            const QVariantList suggestions = result.value("suggestions").toList();
            if (!suggestions.isEmpty()) {
                QVariantMap wData;
                wData["suggestions"] = suggestions;
                wData["analysisText"] = m_mixResult;
                m_chatMessages->addMessage("wavy",
                    m_mixResult.isEmpty() ? "Mix analysis complete:" : m_mixResult,
                    {}, "mix_fixes", wData);
            }
        }, Qt::QueuedConnection);
    });
}

void AIBackend::masterAudio()
{
    setGenerating(true);
    m_client->masterAudio({}, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            const QString path = result.value("audio_path").toString();
            m_mixResult = "Mastered: " + path;
            emit mixResultChanged();
            emit audioReady("Mastered", path, result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::autoMix()
{
    setGenerating(true);
    QVariantMap p;
    p["action"] = "auto_mix";

    m_client->promptCommand("auto mix all tracks", p, {},
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                setGenerating(false);
                if (!ok) { setError(result.value("error").toString()); return; }
                const QVariantList suggestions = result.value("actions").toList();
                emit autoMixReady(suggestions);
                setStatus(QString("Auto-mix applied %1 adjustments").arg(suggestions.size()));
            }, Qt::QueuedConnection);
        });
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

void AIBackend::voiceIsolate(const QString& audioPath)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;

    m_client->elevenLabsVoiceIsolate(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            const QVariantList stems = result.value("stems").toList();
            QStringList paths, names;
            for (const auto& s : stems) {
                auto m = s.toMap();
                paths << m.value("path").toString();
                names << m.value("name").toString();
            }
            if (paths.isEmpty()) {
                paths << result.value("audio_path").toString();
                names << "Isolated Vocals";
            }
            emit stemsReady(paths, names);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::transcribe(const QString& audioPath, const QString& lang)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;
    p["language"]   = lang;

    m_client->elevenLabsTranscribe(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            m_transcribeResult = result.value("text").toString();
            emit transcribeResultChanged();
        }, Qt::QueuedConnection);
    });
}

void AIBackend::forcedAlign(const QString& audioPath, const QString& text)
{
    if (audioPath.isEmpty() || text.isEmpty()) {
        setError("Provide both audio file and text.");
        return;
    }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;
    p["text"]       = text;

    m_client->elevenLabsForcedAlign(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            setStatus("Alignment complete");
        }, Qt::QueuedConnection);
    });
}

void AIBackend::dubAudio(const QString& audioPath,
                          const QString& sourceLang, const QString& targetLang)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"]   = audioPath;
    p["source_lang"]  = sourceLang;
    p["target_lang"]  = targetLang;

    m_client->elevenLabsDub(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            emit audioReady("Dubbed", result.value("audio_path").toString(),
                            result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::replaceSection(const QString& audioPath, double startSec,
                                double endSec, const QString& prompt)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;
    p["start_sec"]  = startSec;
    p["end_sec"]    = endSec;
    p["prompt"]     = prompt;

    m_client->replaceSection(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            emit audioReady("Replaced Section", result.value("audio_path").toString(),
                            result.value("duration", 0.0).toDouble());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::audioToMidi(const QString& audioPath)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);

    QVariantMap p;
    p["audio_path"] = audioPath;

    m_client->audioToMidi(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }
            const QString midiPath = result.value("midi_path").toString();
            setStatus("MIDI exported: " + midiPath);
            emit midiFileReady(midiPath);
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Code
// ---------------------------------------------------------------------------

void AIBackend::runCode(const QString& code, const QString& mode)
{
    setGenerating(true);
    QVariantMap p;
    p["code"] = code;
    p["mode"] = mode;

    m_client->codeToMusic(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok) { setError(result.value("error").toString()); return; }

            const QVariantList tracks   = result.value("track_defs").toList();
            const QVariantList audioVar = result.value("audio_paths").toList();
            QStringList audioPaths, names;
            for (const auto& ap : audioVar) audioPaths << ap.toString();
            for (int i = 0; i < audioPaths.size(); ++i) {
                QString name;
                if (i < tracks.size())
                    name = tracks[i].toMap().value("track").toString();
                if (name.isEmpty()) name = QString("Code Track %1").arg(i + 1);
                names << name;
            }
            emit codeTracksReady(audioPaths, names);
            setStatus(QString("%1 tracks generated").arg(names.size()));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

void AIBackend::sendChat(const QString& text)
{
    if (text.trimmed().isEmpty()) return;

    const QString prompt = text.trimmed();
    m_chatMessages->addMessage("user", prompt);
    setGenerating(true);

    // ── Keyword routing to specialized widgets ──────────────────────────────
    const QString lower = prompt.toLower();
    const bool isChords = (lower.contains("chord") &&
                           (lower.contains("progression") || lower.contains("suggest")
                            || lower.contains("in ") || lower.contains("for ")));
    const bool isBeat   = (lower.contains("beat") || lower.contains("drum pattern")
                           || lower.contains("step sequencer"));

    if (isChords) {
        QVariantMap p;
        p["prompt"] = prompt;
        m_client->chordSuggestions(p, [this, prompt](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result, prompt]() {
                setGenerating(false);
                if (!ok || result.contains("error")) {
                    m_chatMessages->addMessage("wavy",
                        "Couldn't generate chords: " + result.value("error").toString());
                    return;
                }
                const QString label = QString("Here's a chord progression for: %1").arg(prompt);
                QVariantMap wData;
                wData["chords"]       = result.value("chords");
                wData["key"]          = result.value("key");
                wData["scale"]        = result.value("scale");
                wData["originalPrompt"] = prompt;
                m_chatMessages->addMessage("wavy", label, {}, "chords", wData);
            }, Qt::QueuedConnection);
        });
        return;
    }

    if (isBeat) {
        QVariantMap p;
        p["prompt"] = prompt;
        // Extract BPM if mentioned
        static const QRegularExpression bpmRe(R"(\b(\d{2,3})\s*bpm\b)",
                                               QRegularExpression::CaseInsensitiveOption);
        auto m = bpmRe.match(prompt);
        if (m.hasMatch()) p["bpm"] = m.captured(1).toInt();
        m_client->beatBuilder(p, [this, prompt](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result, prompt]() {
                setGenerating(false);
                if (!ok || result.contains("error")) {
                    m_chatMessages->addMessage("wavy",
                        "Couldn't build beat: " + result.value("error").toString());
                    return;
                }
                const QString label = QString("Beat grid for: %1").arg(prompt);
                QVariantMap wData;
                wData["rows"]          = result.value("rows");
                wData["bpm"]           = result.value("bpm", 120);
                wData["bars"]          = result.value("bars", 1);
                wData["originalPrompt"] = prompt;
                m_chatMessages->addMessage("wavy", label, {}, "beat_grid", wData);
            }, Qt::QueuedConnection);
        });
        return;
    }

    // ── Default: prompt_command ─────────────────────────────────────────────
    // Build history (all but last message)
    QVariantList history = m_chatMessages->toVariantList();
    if (!history.isEmpty()) history.removeLast();

    m_client->promptCommand(prompt, QVariantMap{}, history,
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                setGenerating(false);
                if (!ok) {
                    const QString err = result.value("error").toString();
                    m_chatMessages->addMessage("wavy",
                        "Error: " + (err.isEmpty() ? "Backend error." : err));
                    return;
                }

                const QString explanation = result.value("explanation").toString();
                const QVariantList actions = result.value("actions").toList();

                if (!explanation.isEmpty())
                    m_chatMessages->addMessage("wavy", explanation, actions);

                if (!actions.isEmpty())
                    emit actionsReady(actions);
            }, Qt::QueuedConnection);
        });
}

void AIBackend::clearChat()
{
    m_chatMessages->clear();
    m_chatMessages->addMessage("wavy",
        "Hey! I'm Wavy \xF0\x9F\x8E\xB6\n\n"
        "I'm your AI music-making assistant. I can help you:\n"
        "\xE2\x80\xA2 Compose full arrangements and melodies\n"
        "\xE2\x80\xA2 Build chord progressions and beat patterns\n"
        "\xE2\x80\xA2 Generate vocals, stems, and sound effects\n"
        "\xE2\x80\xA2 Mix and master your tracks\n"
        "\xE2\x80\xA2 Answer music theory questions\n\n"
        "What are we making today?");
}

// ---------------------------------------------------------------------------
// Compose agent
// ---------------------------------------------------------------------------

void AIBackend::composeArrangement(const QString& prompt, const QString& mode,
                                    const QString& sessionId,
                                    const QVariantMap& dawCtx,
                                    const QVariantMap& instrumentOverrides)
{
    if (prompt.trimmed().isEmpty()) return;

    // Show user message; Wavy response comes as widget or explanation after completion
    m_chatMessages->addMessage("user", prompt.trimmed());
    setGenerating(true);

    QVariantMap params;
    params["prompt"]      = prompt.trimmed();
    params["mode"]        = mode;
    params["session_id"]  = sessionId;
    params["daw_context"] = dawCtx;
    if (!instrumentOverrides.isEmpty())
        params["instrument_overrides"] = instrumentOverrides;

    m_client->composeArrangement(params,
        [this, mode](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result, mode]() {
                setGenerating(false);
                if (!ok || result.contains("error")) {
                    const QString err = result.value("error").toString();
                    m_chatMessages->addMessage("wavy",
                        "Compose error: " + (err.isEmpty() ? "Backend error." : err));
                    return;
                }

                const QString explanation = result.value("explanation").toString();

                if (mode == "fill") {
                    const QString path = result.value("midi_path").toString();
                    if (!path.isEmpty())
                        emit composeFillReady(path);
                } else {
                    const QVariantList parts = result.value("parts").toList();
                    if (!parts.isEmpty()) {
                        // Update persistent song session so subsequent composeTrack()
                        // calls inherit the same key/scale/bpm/genre
                        const QString sid = result.value("session_id").toString();
                        if (!sid.isEmpty() && m_songSessionId != sid) {
                            m_songSessionId = sid;
                            emit songSessionChanged();
                        }
                        _updateSongMeta(result);
                        emit composeReady(parts, explanation);
                        // Show a simple confirmation — tracks are inserted automatically
                        if (!explanation.isEmpty())
                            m_chatMessages->addMessage("wavy", explanation);
                    }
                }
            }, Qt::QueuedConnection);
        });
}

void AIBackend::composeTrack(const QString& prompt, const QString& role,
                              const QVariantMap& instrOverride,
                              const QVariantMap& section,
                              const QString& seedMidiSlug)
{
    if (prompt.trimmed().isEmpty()) return;

    const QString label = role.isEmpty() ? prompt.trimmed()
                        : (role[0].toUpper() + role.mid(1) + " \u2014 " + prompt.trimmed());
    m_chatMessages->addMessage("user", label);
    setGenerating(true);

    // Create persistent song session UUID on first call; reuse for harmonic unity
    if (m_songSessionId.isEmpty()) {
        m_songSessionId = QUuid::createUuid().toString(QUuid::WithoutBraces);
        emit songSessionChanged();
    }

    QVariantMap params;
    params["mode"]        = "single";
    params["prompt"]      = prompt.trimmed();
    params["role"]        = role;
    params["session_id"]  = m_songSessionId;
    params["daw_context"] = dawContext();
    if (!instrOverride.isEmpty())
        params["instrument_override"] = instrOverride;
    if (!section.isEmpty())
        params["section"] = section;
    if (!seedMidiSlug.trimmed().isEmpty())
        params["seed_midi_slug"] = seedMidiSlug.trimmed();

    m_client->composeArrangement(params,
        [this, section](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result, section]() {
                setGenerating(false);
                if (!ok || result.contains("error")) {
                    const QString err = result.value("error").toString();
                    m_chatMessages->addMessage("wavy",
                        "Error: " + (err.isEmpty() ? "Backend error." : err));
                    return;
                }
                _updateSongMeta(result);
                const QVariantList parts = result.value("parts").toList();
                const QString explanation = result.value("explanation").toString();
                if (!parts.isEmpty()) {
                    emit composeReady(parts, explanation);
                    const QString sec = section.value("name", "").toString();
                    const QString msg = sec.isEmpty()
                        ? QString("Added track (%1 notes)").arg(
                              result.value("parts").toList().value(0).toMap()
                                   .value("note_count", 0).toInt())
                        : QString("Added track to %1 (%2 notes)").arg(sec).arg(
                              result.value("parts").toList().value(0).toMap()
                                   .value("note_count", 0).toInt());
                    m_chatMessages->addMessage("wavy", msg);
                }
            }, Qt::QueuedConnection);
        });
}

void AIBackend::clearSongSession()
{
    m_songSessionId.clear();
    m_songMeta.clear();
    emit songSessionChanged();
    emit songMetaChanged();
}

void AIBackend::chatGenerate(const QString& prompt)
{
    qDebug() << "[chatGenerate] called, prompt=" << prompt;
    if (prompt.trimmed().isEmpty()) {
        qDebug() << "[chatGenerate] empty prompt, ignoring";
        return;
    }
    m_chatMessages->addMessage("user", prompt.trimmed());
    setGenerating(true);
    if (m_songSessionId.isEmpty()) {
        m_songSessionId = QUuid::createUuid().toString(QUuid::WithoutBraces);
        emit songSessionChanged();
    }
    QVariantMap params;
    params["prompt"]     = prompt.trimmed();
    params["session_id"] = m_songSessionId;
    qDebug() << "[chatGenerate] sending RPC: prompt=" << params["prompt"]
             << "session_id=" << params["session_id"];
    m_client->chatGenerate(params, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            qDebug() << "[chatGenerate] callback: ok=" << ok
                     << "keys=" << result.keys();
            setGenerating(false);
            if (!ok || result.contains("error")) {
                const QString err = result.value("error", "Backend error.").toString();
                qDebug() << "[chatGenerate] ERROR:" << err;
                m_chatMessages->addMessage("wavy", "Error: " + err);
                return;
            }
            const QString mode = result.value("mode").toString();
            const QString expl = result.value("explanation").toString();
            qDebug() << "[chatGenerate] mode=" << mode << "explanation=" << expl;
            if (mode == "audio") {
                const QVariantList audioParts = result.value("audio_parts").toList();
                qDebug() << "[chatGenerate] audio_parts count=" << audioParts.size();
                for (const auto& pv : audioParts) {
                    const QVariantMap p = pv.toMap();
                    qDebug() << "[chatGenerate] emit audioReady:" << p.value("title") << p.value("path");
                    emit audioReady(p.value("title", "AI Audio").toString(),
                                    p.value("path").toString(), 0.0);
                }
                m_chatMessages->addMessage("wavy", expl.isEmpty() ? "Generated audio." : expl);
            } else {
                const QVariantList parts = result.value("parts").toList();
                qDebug() << "[chatGenerate] MIDI parts count=" << parts.size();
                for (const auto& pv : parts) {
                    const QVariantMap p = pv.toMap();
                    qDebug() << "[chatGenerate]   part:" << p.value("name") << p.value("midi_path");
                }
                if (!parts.isEmpty()) {
                    _updateSongMeta(result);
                    emit composeReady(parts, expl);
                    m_chatMessages->addMessage("wavy",
                        expl.isEmpty()
                            ? QString("Added %1 MIDI track(s).").arg(parts.size())
                            : expl);
                } else {
                    qDebug() << "[chatGenerate] WARNING: parts list is empty!";
                    m_chatMessages->addMessage("wavy", "No tracks generated.");
                }
            }
        }, Qt::QueuedConnection);
    });
}

void AIBackend::_updateSongMeta(const QVariantMap& result)
{
    bool changed = false;
    for (const QString& k : {"key", "scale", "bpm", "genre"}) {
        if (result.contains(k) && m_songMeta.value(k) != result.value(k)) {
            m_songMeta[k] = result[k];
            changed = true;
        }
    }
    // Sync engine tempo so the transport bar display updates immediately
    if (result.contains("bpm") && m_engine) {
        const int newBpm = result.value("bpm").toInt();
        if (newBpm > 0 && newBpm != m_engine->tempo())
            m_engine->setTempo(newBpm);
    }
    if (changed)
        emit songMetaChanged();
}

void AIBackend::getInstrumentChoices()
{
    m_client->getInstrumentChoices([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok || result.contains("error")) return;
            const QVariantMap choices = result.value("choices").toMap();
            if (!choices.isEmpty())
                emit instrumentChoicesReady(choices);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::getBitmidiInspirations(const QString& genre)
{
    m_client->getBitmidiInspirations(genre, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok || result.contains("error")) return;
            const QVariantList items = result.value("items").toList();
            if (!items.isEmpty())
                emit bitmidiInspirationsReady(items);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::askAboutMidiDatabase(const QString& dbName)
{
    // Switch to Chat tab and post user question
    setCurrentPage(1);
    m_chatMessages->addMessage("user",
        "How do I use " + dbName + " in my production workflow?");
    setGenerating(true);

    m_client->databaseTips(dbName, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            const QString tips = (ok && !result.contains("error"))
                ? result.value("tips").toString()
                : QStringLiteral("Visit the dataset documentation for integration tips.");
            m_chatMessages->addMessage("wavy", tips);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::browseDataset(const QString& db, const QString& query, int offset)
{
    m_client->browseDataset(db, query, offset,
        [this, offset](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, offset]() {
            if (!ok || result.contains("error")) {
                emit datasetBrowseReady({}, 0, false, offset > 0);
                return;
            }
            emit datasetBrowseReady(
                result.value("items").toList(),
                result.value("total",    0).toInt(),
                result.value("has_more", false).toBool(),
                offset > 0);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::downloadLibraryFile(const QString& db, const QString& fileId,
                                     const QString& title, const QString& plugin)
{
    setGenerating(true);
    // Don't forward sf2player as a hint — Python will use _gm_to_plugin intelligence
    const QString rpcPlugin = (plugin == QStringLiteral("sf2player")) ? QString() : plugin;
    m_client->downloadLibraryFile(db, fileId, rpcPlugin,
        [this, title, plugin](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, title, plugin]() {
            setGenerating(false);
            if (!ok || result.contains("error")) {
                setError("Download failed: " + result.value("error").toString());
                return;
            }
            // Audio loop result (WAV/MP3) → add_audio_track action
            if (result.contains(QStringLiteral("audio_path"))) {
                QString audioPath = result.value(QStringLiteral("audio_path")).toString();
                QString trackName = result.value(QStringLiteral("track_name")).toString();
                if (trackName.isEmpty()) trackName = title;
                QVariantMap action;
                action[QStringLiteral("type")]       = QStringLiteral("add_audio_track");
                action[QStringLiteral("track_name")] = trackName;
                action[QStringLiteral("audio_path")] = audioPath;
                action[QStringLiteral("color")]      = QStringLiteral("#ef5350");
                QMetaObject::invokeMethod(m_engine, [this, action]() {
                    m_engine->dispatchActions(QVariantList{action});
                }, Qt::QueuedConnection);
                emit libraryFileImported(title);
                return;
            }
            // Multi-channel split: backend returns {parts: [...]} instead of {midi_path, instrument}
            if (result.contains(QStringLiteral("parts"))) {
                QVariantList rawParts = result.value(QStringLiteral("parts")).toList();
                if (!rawParts.isEmpty()) {
                    // ── Build genre-mapped parts ────────────────────────────
                    QVariantList genreParts;
                    bool hasGmData = false;
                    for (const auto& pv : rawParts) {
                        QVariantMap pm = pv.toMap();
                        const QString catStr = pm.value(QStringLiteral("category")).toString();
                        const int gmProg = pm.value(QStringLiteral("gm_program"), -1).toInt();

                        GmCategory cat;
                        if (!catStr.isEmpty()) {
                            cat = categoryFromString(catStr);
                        } else if (gmProg >= 0) {
                            cat = gmProgramToCategory(gmProg);
                        } else {
                            const QString pi = pm.value(QStringLiteral("instrument")).toString();
                            if (pi == QStringLiteral("kicker"))
                                cat = GmCategory::Drums;
                            else if (pi == QStringLiteral("lb302"))
                                cat = GmCategory::Bass;
                            else
                                cat = GmCategory::SynthLead;
                        }

                        const GmMapping& mapping = resolveGmMapping(m_activeGenre, cat);
                        pm[QStringLiteral("instrument")]  = QString(mapping.plugin);
                        pm[QStringLiteral("preset_name")] = QString(mapping.preset);
                        pm[QStringLiteral("reverb_wet")]  = static_cast<double>(mapping.reverbWet);
                        const int resolvedPatch = (mapping.gmPatch >= 0) ? mapping.gmPatch : gmProg;
                        pm[QStringLiteral("gm_patch")]    = resolvedPatch;
                        genreParts.append(pm);
                        if (gmProg >= 0) hasGmData = true;
                    }

                    // ── Build GM-original parts (sf2player with faithful patches) ──
                    QVariantList gmParts;
                    for (const auto& pv : rawParts) {
                        QVariantMap pm = pv.toMap();
                        const int gmProg = pm.value(QStringLiteral("gm_program"), -1).toInt();
                        if (pm.value(QStringLiteral("category")).toString() == QStringLiteral("drums")) {
                            pm[QStringLiteral("instrument")] = QStringLiteral("kicker");
                        } else {
                            pm[QStringLiteral("instrument")]  = QStringLiteral("sf2player");
                            pm[QStringLiteral("gm_patch")]    = gmProg;
                        }
                        gmParts.append(pm);
                    }

                    // ── Extract MIDI BPM from result ────────────────────────
                    const int midiBpm = result.value(QStringLiteral("bpm"), 0).toInt();
                    const int songBpm = m_engine ? m_engine->tempo() : 120;

                    // Store pending state and show confirmation dialog
                    m_pendingGenreParts  = genreParts;
                    m_pendingGmParts     = gmParts;
                    m_pendingMidiBpm     = midiBpm;
                    m_pendingImportTitle = title;
                    emit midiImportConfirm(title, midiBpm, songBpm,
                                           m_activeGenre, hasGmData);
                    return;
                }
            }
            // Plugin priority: 1) caller hint (unless sf2player stale default)
            //                 2) RPC result  3) active genre  4) tripleoscillator
            // sf2player is hardcoded by Python browse results — treat as "no preference"
            QString instr = plugin;
            if (instr == QStringLiteral("sf2player"))
                instr.clear();
            if (instr.isEmpty())
                instr = result.value(QStringLiteral("instrument")).toString();
            if (instr == QStringLiteral("sf2player"))
                instr.clear();
            if (instr.isEmpty() && !m_activeGenre.isEmpty()) {
                const GenreModeCfg* gcfg = findGenreMode(m_activeGenre);
                if (gcfg && gcfg->instruments[0].name[0])
                    instr = QString(gcfg->instruments[0].plugin);
            }
            if (instr.isEmpty())
                instr = QStringLiteral("tripleoscillator");
            QVariantMap part;
            part[QStringLiteral("name")]       = title;
            part[QStringLiteral("midi_path")]  = result.value("midi_path").toString();
            part[QStringLiteral("color")]      = QStringLiteral("#64b5f6");
            part[QStringLiteral("note_count")] = 0;
            part[QStringLiteral("instrument")] = instr;
            emit composeReady(QVariantList{part}, "Imported: " + title);
            emit libraryFileImported(title);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::confirmMidiImport(bool useMidiBpm, bool useGenrePresets)
{
    if (m_pendingGenreParts.isEmpty() && m_pendingGmParts.isEmpty())
        return;

    // Apply MIDI BPM if requested
    if (useMidiBpm && m_pendingMidiBpm > 0 && m_engine)
        m_engine->setTempo(m_pendingMidiBpm);

    const QVariantList& parts = useGenrePresets ? m_pendingGenreParts : m_pendingGmParts;
    const QString title = m_pendingImportTitle;
    emit composeReady(parts, QStringLiteral("Imported: ") + title);
    emit libraryFileImported(title);

    // Clear pending state
    m_pendingGenreParts.clear();
    m_pendingGmParts.clear();
    m_pendingMidiBpm = 0;
    m_pendingImportTitle.clear();
}

void AIBackend::cancelMidiImport()
{
    m_pendingGenreParts.clear();
    m_pendingGmParts.clear();
    m_pendingMidiBpm = 0;
    m_pendingImportTitle.clear();
}

void AIBackend::startMidicapsDownload()
{
    m_client->startMidicapsDownload([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok) return;
            emit midicapsStatusUpdate(
                result.value(QStringLiteral("status")).toString(),
                result.value(QStringLiteral("progress"), 0.0).toDouble(),
                result.value(QStringLiteral("files_extracted"), 0).toInt(),
                result.value(QStringLiteral("bytes_downloaded"), 0LL).toLongLong(),
                result.value(QStringLiteral("total_bytes"),      0LL).toLongLong());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::checkMidicapsStatus()
{
    m_client->midicapsLibraryStatus([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok) return;
            emit midicapsStatusUpdate(
                result.value(QStringLiteral("status")).toString(),
                result.value(QStringLiteral("progress"), 0.0).toDouble(),
                result.value(QStringLiteral("files_extracted"), 0).toInt(),
                result.value(QStringLiteral("bytes_downloaded"), 0LL).toLongLong(),
                result.value(QStringLiteral("total_bytes"),      0LL).toLongLong());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::testDatabases()
{
    appendLog(QStringLiteral("[INFO] Testing database connections…"));
    m_client->testDatabases([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok) {
                appendLog(QStringLiteral("[ERROR] test_databases RPC failed"));
                return;
            }
            const QVariantList rows = result.value(QStringLiteral("results")).toList();
            for (const QVariant& v : rows) {
                const QVariantMap r = v.toMap();
                const QString name  = r.value(QStringLiteral("name")).toString();
                const bool    dbOk  = r.value(QStringLiteral("ok")).toBool();
                const int     count = r.value(QStringLiteral("count")).toInt();
                const int     ms    = r.value(QStringLiteral("ms")).toInt();
                const QString err   = r.value(QStringLiteral("error")).toString();
                if (dbOk) {
                    appendLog(QString("[INFO] %1: OK — %2 results (%3 ms)")
                              .arg(name).arg(count).arg(ms));
                } else {
                    appendLog(QString("[ERROR] %1: FAILED — %2 (%3 ms)")
                              .arg(name).arg(err).arg(ms));
                }
            }
            appendLog(QStringLiteral("[INFO] Database test complete."));
        }, Qt::QueuedConnection);
    });
}

QString AIBackend::newSessionId() const
{
    return QUuid::createUuid().toString(QUuid::WithoutBraces);
}

QVariantMap AIBackend::dawContext() const
{
    QVariantMap ctx;
    // Include existing MIDI note pitches so the compose agent can detect the
    // session key and ensure new tracks are harmonically coherent.
    if (m_engine) {
        const QVariantList notes = m_engine->existingMidiNotes();
        if (!notes.isEmpty())
            ctx["existing_notes"] = notes;
    }
    return ctx;
}

void AIBackend::regenerateBar(const QString& sessionId, const QString& partName,
                               int barIndex, const QVariantMap& ctx)
{
    setGenerating(true);
    QVariantMap p;
    p["session_id"] = sessionId;
    p["part_name"]  = partName;
    p["bar_index"]  = barIndex;
    for (auto it = ctx.cbegin(); it != ctx.cend(); ++it)
        p[it.key()] = it.value();

    m_client->regenerateBar(p, [this, partName, barIndex](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, partName, barIndex]() {
            setGenerating(false);
            if (!ok || result.contains("error")) {
                setError("Regenerate bar failed: " + result.value("error").toString());
                return;
            }
            const QString midiPath = result.value("midi_path").toString();
            const QVariantList notes = result.value("notes").toList();
            emit regenerateBarReady(partName, barIndex, notes, midiPath);
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Session context
// ---------------------------------------------------------------------------

void AIBackend::setActiveGenre(const QString& genre)
{
    if (m_activeGenre == genre) return;
    m_activeGenre = genre;
    emit activeGenreChanged(genre);
}

void AIBackend::setGenreMode(const QString& modeKey)
{
    // Read QSettings overrides (for both built-in and custom genres)
    QSettings settings;
    const QString overridePrefix = (modeKey == QStringLiteral("custom"))
        ? QStringLiteral("Wavy/GenreCustom/")
        : QStringLiteral("Wavy/GenreOverrides/") + modeKey + "/";
    const bool hasOverrides = !settings.value(overridePrefix + "bpm").isNull();

    // 1. Apply to DAW (sets BPM, time sig, master FX, instrument tracks)
    if (modeKey == QStringLiteral("custom")) {
        // Custom genre: read everything from QSettings
        const int bpm   = settings.value(overridePrefix + "bpm", 120).toInt();
        const int tsNum = settings.value(overridePrefix + "timeSigNum", 4).toInt();
        const int tsDen = settings.value(overridePrefix + "timeSigDen", 4).toInt();

        if (m_engine) {
            m_engine->setTempo(bpm);
            m_engine->setTimeSignature(tsNum, tsDen);
        }
#ifdef WAVY_LMMS_CORE
        if (auto* lmmsEng = qobject_cast<LmmsEngine*>(m_engine)) {
            lmmsEng->clearMasterFx();
            // Read FX from settings
            const QByteArray fxJson = settings.value(overridePrefix + "masterFx").toByteArray();
            if (!fxJson.isEmpty()) {
                QJsonDocument doc = QJsonDocument::fromJson(fxJson);
                if (doc.isArray()) {
                    for (const auto& v : doc.array())
                        lmmsEng->addFxToMaster(v.toString());
                }
            }
            // Create instrument tracks from saved config
            const QVariantList instrConfig = getGenreInstrumentConfig(modeKey);
            lmmsEng->createCustomInstrumentTracks(instrConfig);
        }
#endif
    } else {
        // Built-in genre: apply static config, then overlay QSettings overrides
#ifdef WAVY_LMMS_CORE
        if (auto* lmmsEng = qobject_cast<LmmsEngine*>(m_engine)) {
            lmmsEng->applyGenreMode(modeKey);
            // Overlay BPM/time sig overrides if present
            if (hasOverrides) {
                const GenreModeCfg* cfg = findGenreMode(modeKey);
                const int bpm   = settings.value(overridePrefix + "bpm", cfg ? cfg->bpm : 120).toInt();
                const int tsNum = settings.value(overridePrefix + "timeSigNum", cfg ? cfg->timeSigNum : 4).toInt();
                const int tsDen = settings.value(overridePrefix + "timeSigDen", cfg ? cfg->timeSigDen : 4).toInt();
                m_engine->setTempo(bpm);
                m_engine->setTimeSignature(tsNum, tsDen);
                // Overlay FX
                const QByteArray fxJson = settings.value(overridePrefix + "masterFx").toByteArray();
                if (!fxJson.isEmpty()) {
                    QJsonDocument doc = QJsonDocument::fromJson(fxJson);
                    if (doc.isArray()) {
                        lmmsEng->clearMasterFx();
                        for (const auto& v : doc.array())
                            lmmsEng->addFxToMaster(v.toString());
                    }
                }
            }
        } else
#endif
        {
            // Fallback via base EngineAPI (BPM + time sig at minimum)
            if (m_engine) {
                const GenreModeCfg* cfg = findGenreMode(modeKey);
                if (cfg) {
                    const int bpm   = settings.value(overridePrefix + "bpm", cfg->bpm).toInt();
                    const int tsNum = settings.value(overridePrefix + "timeSigNum", cfg->timeSigNum).toInt();
                    const int tsDen = settings.value(overridePrefix + "timeSigDen", cfg->timeSigDen).toInt();
                    m_engine->setTempo(bpm);
                    m_engine->setTimeSignature(tsNum, tsDen);
                }
            }
        }
    }

    // 2. Update active genre property (shared with Chat/Library tabs)
    if (m_activeGenre != modeKey) {
        m_activeGenre = modeKey;
        emit activeGenreChanged(modeKey);
    }

    // 3. Build + push session context to Python backend
    QVariantMap ctx;
    ctx[QStringLiteral("genre")] = modeKey;

    if (modeKey == QStringLiteral("custom")) {
        ctx[QStringLiteral("key")]         = settings.value(overridePrefix + "key", "C").toString();
        ctx[QStringLiteral("scale")]       = settings.value(overridePrefix + "scale", "major").toString();
        ctx[QStringLiteral("bpm")]         = settings.value(overridePrefix + "bpm", 120).toInt();
        ctx[QStringLiteral("chord_style")] = settings.value(overridePrefix + "chordStyle", "default").toString();
        ctx[QStringLiteral("drum_style")]  = settings.value(overridePrefix + "drumStyle", "default").toString();
    } else {
        const GenreModeCfg* cfg = findGenreMode(modeKey);
        if (cfg) {
            ctx[QStringLiteral("key")]         = hasOverrides ? settings.value(overridePrefix + "key", QString(cfg->defaultKey)).toString() : QString(cfg->defaultKey);
            ctx[QStringLiteral("scale")]       = hasOverrides ? settings.value(overridePrefix + "scale", QString(cfg->defaultScale)).toString() : QString(cfg->defaultScale);
            ctx[QStringLiteral("bpm")]         = hasOverrides ? settings.value(overridePrefix + "bpm", cfg->bpm).toInt() : cfg->bpm;
            ctx[QStringLiteral("chord_style")] = hasOverrides ? settings.value(overridePrefix + "chordStyle", QString(cfg->chordStyle)).toString() : QString(cfg->chordStyle);
            ctx[QStringLiteral("drum_style")]  = hasOverrides ? settings.value(overridePrefix + "drumStyle", QString(cfg->drumStyle)).toString() : QString(cfg->drumStyle);
        }
    }

    // Use overridden instruments if saved, otherwise static table
    const QVariantList overriddenConfig = getGenreInstrumentConfig(modeKey);
    QVariantList palette;
    for (int i = 0; i < overriddenConfig.size(); ++i)
        palette.append(overriddenConfig.at(i).toMap().value(QStringLiteral("name")));
    ctx[QStringLiteral("instrument_palette")] = palette;
    setSessionContext(ctx);
}

void AIBackend::setSessionContext(const QVariantMap& ctx)
{
    m_client->setSessionContext(ctx, [this, ctx](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, ctx]() {
            if (ok) {
                m_sessionContext = result.value("context").toMap();
                if (m_sessionContext.isEmpty()) m_sessionContext = ctx;
            } else {
                m_sessionContext = ctx; // optimistic update
            }
            emit sessionContextChanged(m_sessionContext);
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Chord suggestions
// ---------------------------------------------------------------------------

void AIBackend::getChordSuggestions(const QString& prompt, const QVariantMap& ctx)
{
    if (prompt.trimmed().isEmpty()) return;
    setGenerating(true);

    QVariantMap p;
    p["prompt"] = prompt.trimmed();
    for (auto it = ctx.cbegin(); it != ctx.cend(); ++it)
        p[it.key()] = it.value();

    m_client->chordSuggestions(p, [this, prompt](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, prompt]() {
            setGenerating(false);
            if (!ok || result.contains("error")) {
                setError("Chord suggestions failed: " + result.value("error").toString());
                return;
            }
            const QString label = QString("Chord progression for: %1").arg(prompt);
            QVariantMap wData;
            wData["chords"]        = result.value("chords");
            wData["key"]           = result.value("key");
            wData["scale"]         = result.value("scale");
            wData["originalPrompt"] = prompt;
            m_chatMessages->addMessage("wavy", label, {}, "chords", wData);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::insertChord(const QVariantList& pitches, int barIndex)
{
    QVariantMap action;
    action["type"]       = "insert_chord";
    action["pitches"]    = pitches;
    action["bar_index"]  = barIndex;
    action["duration_beats"] = 2.0;
    emit actionsReady({ action });
}

// ---------------------------------------------------------------------------
// Beat builder
// ---------------------------------------------------------------------------

void AIBackend::buildBeat(const QString& prompt, const QVariantMap& ctx)
{
    if (prompt.trimmed().isEmpty()) return;
    setGenerating(true);

    QVariantMap p;
    p["prompt"] = prompt.trimmed();
    for (auto it = ctx.cbegin(); it != ctx.cend(); ++it)
        p[it.key()] = it.value();

    m_client->beatBuilder(p, [this, prompt](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, prompt]() {
            setGenerating(false);
            if (!ok || result.contains("error")) {
                setError("Beat builder failed: " + result.value("error").toString());
                return;
            }
            const QString label = QString("Beat grid for: %1").arg(prompt);
            QVariantMap wData;
            wData["rows"]          = result.value("rows");
            wData["bpm"]           = result.value("bpm", 120);
            wData["bars"]          = result.value("bars", 1);
            wData["originalPrompt"] = prompt;
            m_chatMessages->addMessage("wavy", label, {}, "beat_grid", wData);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::insertBeatPattern(const QVariantList& rows, int bpm, int bars)
{
    QVariantMap action;
    action["type"]  = "insert_beat_pattern";
    action["rows"]  = rows;
    action["bpm"]   = bpm;
    action["bars"]  = bars;
    emit actionsReady({ action });
}

// ---------------------------------------------------------------------------
// Genre FX / Pitch correction / Arpeggiator / Granular (v0.9.5)
// ---------------------------------------------------------------------------

void AIBackend::applyTrackFx(const QString& audioPath, const QString& genre,
                               const QString& role)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus("Applying FX…");

    QVariantMap p;
    p[QStringLiteral("audio_path")] = audioPath;
    p[QStringLiteral("genre")]      = genre;
    p[QStringLiteral("role")]       = role;

    m_client->callAsync(QStringLiteral("apply_track_fx"), p,
                        [this, audioPath](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, audioPath]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("FX processing failed.")).toString());
                return;
            }
            QString outPath = result.value(QStringLiteral("audio_path"),
                                           audioPath).toString();
            QString name = QFileInfo(outPath).baseName();
            emit audioReady(name, outPath, 0.0);
            setStatus(QStringLiteral("FX applied."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::pitchCorrectAudio(const QString& audioPath, const QString& key,
                                    const QString& scale, double strength)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Applying pitch correction…"));

    QVariantMap p;
    p[QStringLiteral("audio_path")] = audioPath;
    p[QStringLiteral("key")]        = key;
    p[QStringLiteral("scale")]      = scale;
    p[QStringLiteral("strength")]   = strength;

    m_client->callAsync(QStringLiteral("pitch_correct_audio"), p,
                        [this, audioPath](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, audioPath]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Pitch correction failed.")).toString());
                return;
            }
            QString outPath   = result.value(QStringLiteral("audio_path"),
                                              audioPath).toString();
            QString trackName = result.value(QStringLiteral("track_name"),
                                              QStringLiteral("Auto-Tuned")).toString();
            emit audioReady(trackName, outPath, 0.0);
            setStatus(QStringLiteral("Pitch correction applied."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::generateArpeggio(const QVariantList& chordNotes, int bpm,
                                   const QString& style, int bars)
{
    setGenerating(true);
    setStatus(QStringLiteral("Generating arpeggio…"));

    QVariantMap p;
    p[QStringLiteral("chord_notes")] = chordNotes;
    p[QStringLiteral("bpm")]         = bpm;
    p[QStringLiteral("style")]       = style;
    p[QStringLiteral("bars")]        = bars;

    m_client->callAsync(QStringLiteral("generate_arpeggio"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Arpeggio generation failed.")).toString());
                return;
            }
            QVariantList parts = result.value(QStringLiteral("parts")).toList();
            if (!parts.isEmpty()) {
                emit composeReady(parts, QStringLiteral("Arpeggio generated"));
            }
            setStatus(QStringLiteral("Arpeggio inserted."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::granularChopAudio(const QString& audioPath, double grainMs,
                                    double pitchSpread, double density)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Processing granular…"));

    QVariantMap p;
    p[QStringLiteral("audio_path")]   = audioPath;
    p[QStringLiteral("grain_ms")]     = grainMs;
    p[QStringLiteral("pitch_spread")] = pitchSpread;
    p[QStringLiteral("density")]      = density;

    m_client->callAsync(QStringLiteral("granular_chop_audio"), p,
                        [this, audioPath](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, audioPath]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Granular processing failed.")).toString());
                return;
            }
            QString outPath   = result.value(QStringLiteral("audio_path"),
                                              audioPath).toString();
            QString trackName = result.value(QStringLiteral("track_name"),
                                              QStringLiteral("Granular Pad")).toString();
            emit audioReady(trackName, outPath, 0.0);
            setStatus(QStringLiteral("Granular pad created."));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// NCS Toolkit (v0.9.9)
// ---------------------------------------------------------------------------

void AIBackend::generateRiser(const QString& riserType, int bpm, double bars)
{
    setGenerating(true);
    setStatus(QStringLiteral("Generating riser…"));

    QVariantMap p;
    p[QStringLiteral("riser_type")] = riserType;
    p[QStringLiteral("bpm")]        = bpm;
    p[QStringLiteral("bars")]       = bars;

    m_client->callAsync(QStringLiteral("generate_riser"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Riser generation failed.")).toString());
                return;
            }
            QString path = result.value(QStringLiteral("audio_path")).toString();
            emit riserReady(path);
            setStatus(QStringLiteral("Riser ready."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::applySidechainPump(const QString& audioPath, int bpm,
                                    double depth, double releaseMs)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Applying sidechain pump…"));

    QVariantMap p;
    p[QStringLiteral("audio_path")]  = audioPath;
    p[QStringLiteral("bpm")]         = bpm;
    p[QStringLiteral("depth")]       = depth;
    p[QStringLiteral("release_ms")]  = releaseMs;

    m_client->callAsync(QStringLiteral("apply_sidechain_pump"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Sidechain pump failed.")).toString());
                return;
            }
            QString path = result.value(QStringLiteral("audio_path")).toString();
            emit sidechainReady(path);
            emit audioReady(QStringLiteral("Sidechain Pumped"), path, 0.0);
            setStatus(QStringLiteral("Sidechain pump applied."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::getNcsSongStructure(const QString& genre, const QString& key,
                                     const QString& scale, int bpm)
{
    setGenerating(true);
    setStatus(QStringLiteral("Generating song structure…"));

    QVariantMap p;
    p[QStringLiteral("genre")] = genre;
    p[QStringLiteral("key")]   = key;
    p[QStringLiteral("scale")] = scale;
    p[QStringLiteral("bpm")]   = bpm;

    m_client->callAsync(QStringLiteral("ncs_song_structure"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Song structure failed.")).toString());
                return;
            }
            QVariantList sections = result.value(QStringLiteral("sections")).toList();
            emit ncsSongStructureReady(sections);
            setStatus(QStringLiteral("Song structure ready."));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Stem extraction
// ---------------------------------------------------------------------------

void AIBackend::extractStems(const QString& audioPath, const QString& mode)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus("Extracting stems…");

    const int numStems = (mode == "2stem") ? 2 : 4;
    appendLog(QString("[extractStems] path=%1 mode=%2 stems=%3")
                  .arg(audioPath).arg(mode).arg(numStems));

    QVariantMap p;
    p["audio_path"] = audioPath;
    p["stems"]      = numStems;   // 2-stem = vocals+instru, 4-stem = full Demucs

    m_client->splitStems(p, [this, audioPath, numStems](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, audioPath, numStems]() {
            setGenerating(false);
            // Log raw result JSON for debugging
            const QString rawJson = QString::fromUtf8(
                QJsonDocument::fromVariant(result).toJson(QJsonDocument::Compact));
            appendLog(QString("[extractStems] raw result: %1").arg(rawJson.left(400)));

            if (!ok || result.contains("error")) {
                const QString err = result.value("error").toString();
                appendLog(QString("[extractStems] FAILED ok=%1 error=%2")
                              .arg(ok ? "true" : "false").arg(err));
                setError("Stem extraction failed: " + err);
                return;
            }
            // Python may return stems as a list [{name,path},...] or as a
            // dict {name:path,...} (old server / no normalization).  Handle both.
            QVariantList stems;
            const QVariant stemsVar = result.value("stems");
            if (stemsVar.canConvert<QVariantMap>() &&
                stemsVar.metaType() != QMetaType::fromType<QVariantList>()) {
                const QVariantMap dict = stemsVar.toMap();
                for (auto it = dict.constBegin(); it != dict.constEnd(); ++it) {
                    QVariantMap entry;
                    entry["name"] = it.key();
                    entry["path"] = it.value().toString();
                    stems.append(entry);
                }
                appendLog(QString("[extractStems] dict→list conversion: %1 stems").arg(stems.size()));
            } else {
                stems = stemsVar.toList();
            }
            appendLog(QString("[extractStems] stems list size: %1").arg(stems.size()));
            setStatus(QString("%1 stems extracted").arg(stems.size()));
            emit stemsExtracted(stems);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::insertStemFile(const QString& stemPath, const QString& stemName)
{
    emit audioReady(stemName.isEmpty() ? "Stem" : stemName, stemPath, 0.0);
}

QVariantList AIBackend::getSongAudioTracks() const
{
    if (m_engine)
        return m_engine->songAudioTracks();
    return {};
}

void AIBackend::previewAudio(const QString& path)
{
    if (!path.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}

// ---------------------------------------------------------------------------
// SoundFont Manager
// ---------------------------------------------------------------------------

QVariantList AIBackend::getAvailableSoundfonts()
{
    // Synchronous RPC — fast check of filesystem
    QVariantList result;
    QVariantMap params;
    bool done = false;
    m_client->callAsync(QStringLiteral("list_soundfonts"), params,
                        [&result, &done](bool ok, const QVariantMap& r) {
        if (ok && !r.contains(QStringLiteral("error")))
            result = r.value(QStringLiteral("soundfonts")).toList();
        done = true;
    });
    // Spin briefly for sync call (ZMQ REQ/REP is fast)
    QElapsedTimer t; t.start();
    while (!done && t.elapsed() < 3000)
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
    return result;
}

void AIBackend::downloadSoundfont(const QString& name)
{
    if (name.isEmpty()) return;
    setGenerating(true);
    setStatus(QStringLiteral("Downloading ") + name + QStringLiteral("..."));

    QVariantMap p;
    p[QStringLiteral("name")] = name;

    m_client->callAsync(QStringLiteral("download_soundfont"), p,
                        [this, name](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, name]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(QStringLiteral("Download failed: ")
                         + result.value(QStringLiteral("error")).toString());
                return;
            }
            const QString path = result.value(QStringLiteral("path")).toString();
            setStatus(name + QStringLiteral(" installed."));
            emit soundfontDownloaded(name, path);

            // Auto-set as default SF2 for GeneralUser GS (best quality/size ratio)
            if (name == QStringLiteral("GeneralUser GS"))
                setDefaultSoundfont(path);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::setDefaultSoundfont(const QString& path)
{
#ifdef WAVY_LMMS_CORE
    if (!path.isEmpty()) {
        lmms::ConfigManager::inst()->setSF2File(path);
        appendLog(QStringLiteral("[SoundFont] Default SF2 set to: ") + path);
    }
#else
    Q_UNUSED(path)
#endif
}

// ---------------------------------------------------------------------------
// Genre instrument config
// ---------------------------------------------------------------------------

QVariantList AIBackend::getAvailablePlugins()
{
#ifdef WAVY_LMMS_CORE
    if (auto* lmmsEng = qobject_cast<LmmsEngine*>(m_engine))
        return lmmsEng->availableInstrumentPlugins();
#endif
    // Hardcoded fallback for non-LMMS builds
    QVariantList result;
    for (const char* p : {"tripleoscillator","lb302","monstro","organic",
                          "opulenz","bitinvader","kicker","sf2player"}) {
        QVariantMap entry;
        entry[QStringLiteral("name")]        = QString(p);
        entry[QStringLiteral("displayName")] = QString(p);
        result.append(entry);
    }
    return result;
}

QStringList AIBackend::getPresetsForPlugin(const QString& plugin)
{
#ifdef WAVY_LMMS_CORE
    if (auto* lmmsEng = qobject_cast<LmmsEngine*>(m_engine))
        return lmmsEng->presetsForPlugin(plugin);
#endif
    return {};
}

bool AIBackend::addInstrumentTrack(const QString& pluginName, const QString& trackName,
                                    const QString& preset, const QString& samplePath)
{
#ifdef WAVY_LMMS_CORE
    if (auto* lmmsEng = qobject_cast<LmmsEngine*>(m_engine))
        return lmmsEng->addEmptyInstrumentTrack(pluginName, trackName, preset, samplePath);
#endif
    return false;
}

QVariantList AIBackend::getGenreInstrumentConfig(const QString& genreKey)
{
    // Check QSettings for user overrides first
    QSettings settings;
    const QString settingsKey = QStringLiteral("Wavy/GenreInstruments/") + genreKey;
    const QByteArray saved = settings.value(settingsKey).toByteArray();
    if (!saved.isEmpty()) {
        QJsonDocument doc = QJsonDocument::fromJson(saved);
        if (doc.isArray()) {
            const QJsonArray jsonArr = doc.array();
            QVariantList result;
            for (int i = 0; i < jsonArr.size(); ++i)
                result.append(jsonArr.at(i).toObject().toVariantMap());
            if (!result.isEmpty())
                return result;
        }
    }

    // "custom" genre with no saved data → return 1 default TripleOscillator
    if (genreKey == QStringLiteral("custom")) {
        QVariantList result;
        QVariantMap slot;
        slot[QStringLiteral("name")]   = QStringLiteral("Lead");
        slot[QStringLiteral("plugin")] = QStringLiteral("tripleoscillator");
        slot[QStringLiteral("preset")] = QString();
        slot[QStringLiteral("color")]  = QStringLiteral("#3498DB");
        result.append(slot);
        return result;
    }

    // Fall back to static GenreModes.h table
    const GenreModeCfg* cfg = findGenreMode(genreKey);
    if (!cfg) return {};

    QVariantList result;
    for (int i = 0; i < 10 && cfg->instruments[i].name[0]; ++i) {
        const InstrumentDef& def = cfg->instruments[i];
        QVariantMap slot;
        slot[QStringLiteral("name")]   = QString(def.name);
        slot[QStringLiteral("plugin")] = QString(def.plugin);
        slot[QStringLiteral("preset")] = QString(def.preset);
        slot[QStringLiteral("color")]  = QColor(QRgb(def.color)).name();
        result.append(slot);
    }
    return result;
}

void AIBackend::saveGenreInstrumentOverride(const QString& genreKey,
                                             const QVariantList& instrSlots)
{
    QJsonArray arr;
    for (int i = 0; i < instrSlots.size(); ++i) {
        const QVariantMap m = instrSlots.at(i).toMap();
        arr.append(QJsonObject::fromVariantMap(m));
    }

    QSettings settings;
    const QString settingsKey = QStringLiteral("Wavy/GenreInstruments/") + genreKey;
    const QByteArray json = QJsonDocument(arr).toJson(QJsonDocument::Compact);
    settings.setValue(settingsKey, json);
    qDebug() << "[AIBackend] saveGenreInstrumentOverride" << genreKey << instrSlots.size() << "slots";
    emit genreInstrumentConfigChanged(genreKey);
}

void AIBackend::resetGenreInstrumentDefaults(const QString& genreKey)
{
    QSettings settings;
    settings.remove(QStringLiteral("Wavy/GenreInstruments/") + genreKey);
    qDebug() << "[AIBackend] resetGenreInstrumentDefaults" << genreKey;
    emit genreInstrumentConfigChanged(genreKey);
}

// ---------------------------------------------------------------------------
// Instrument Catalog (v0.14.0)
// ---------------------------------------------------------------------------

void AIBackend::searchInstruments(const QString& query, const QString& category,
                                   const QString& source, int offset, int limit)
{
    QVariantMap p;
    if (!query.isEmpty())    p[QStringLiteral("query")]    = query;
    if (!category.isEmpty()) p[QStringLiteral("category")] = category;
    if (!source.isEmpty())   p[QStringLiteral("source")]   = source;
    p[QStringLiteral("offset")] = offset;
    p[QStringLiteral("limit")]  = limit;

    m_client->callAsync(QStringLiteral("list_instruments"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error")).toString());
                return;
            }
            emit instrumentSearchResults(
                result.value(QStringLiteral("items")).toList(),
                result.value(QStringLiteral("total")).toInt(),
                result.value(QStringLiteral("has_more")).toBool());
        }, Qt::QueuedConnection);
    });
}

void AIBackend::getInstrumentDetails(const QString& instrumentId)
{
    if (instrumentId.isEmpty()) return;
    QVariantMap p;
    p[QStringLiteral("id")] = instrumentId;

    m_client->callAsync(QStringLiteral("get_instrument_details"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error")).toString());
                return;
            }
            emit instrumentDetailsReady(result);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::downloadInstrumentPack(const QString& packName)
{
    if (packName.isEmpty()) return;
    setGenerating(true);
    setStatus(QStringLiteral("Downloading ") + packName + QStringLiteral("..."));

    QVariantMap p;
    p[QStringLiteral("name")] = packName;

    m_client->callAsync(QStringLiteral("download_instrument_pack"), p,
                        [this, packName](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, packName]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(QStringLiteral("Download failed: ")
                         + result.value(QStringLiteral("error")).toString());
                return;
            }
            const QString path = result.value(QStringLiteral("path")).toString();
            setStatus(packName + QStringLiteral(" installed."));
            emit instrumentPackDownloaded(packName, path);
        }, Qt::QueuedConnection);
    });
}

void AIBackend::listInstrumentPacks()
{
    QVariantMap p;
    m_client->callAsync(QStringLiteral("list_instrument_packs"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error")).toString());
                return;
            }
            emit instrumentPacksListed(result.value(QStringLiteral("packs")).toList());
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Audio editing (v0.12.0)
// ---------------------------------------------------------------------------

void AIBackend::extendAudio(const QString& audioPath, double extendSec,
                             const QString& prompt)
{
    if (audioPath.isEmpty()) { setError("Select an audio file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Extending audio…"));

    QVariantMap p;
    p[QStringLiteral("audio_path")]  = audioPath;
    p[QStringLiteral("extend_sec")]  = extendSec;
    if (!prompt.isEmpty())
        p[QStringLiteral("prompt")] = prompt;

    m_client->callAsync(QStringLiteral("extend_music"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Audio extend failed.")).toString());
                return;
            }
            const QString path = result.value(QStringLiteral("audio_path")).toString();
            const double dur = result.value(QStringLiteral("duration"), 0.0).toDouble();
            emit audioReady(QStringLiteral("Extended"), path, dur);
            setStatus(QStringLiteral("Audio extended."));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// MIDI AI tools (v0.12.0)
// ---------------------------------------------------------------------------

void AIBackend::midiExtend(const QString& midiPath, int barsToAdd,
                            const QString& prompt)
{
    if (midiPath.isEmpty()) { setError("Select a MIDI file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Extending MIDI…"));

    QVariantMap p;
    p[QStringLiteral("midi_path")]    = midiPath;
    p[QStringLiteral("bars_to_add")]  = barsToAdd;
    if (!prompt.isEmpty())
        p[QStringLiteral("prompt")] = prompt;
    if (m_engine)
        p[QStringLiteral("bpm")] = m_engine->tempo();

    m_client->callAsync(QStringLiteral("midi_extend"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("MIDI extend failed.")).toString());
                return;
            }
            const QString path = result.value(QStringLiteral("midi_path")).toString();
            emit midiFileReady(path);
            setStatus(QString("MIDI extended by %1 bars.").arg(
                result.value(QStringLiteral("bars_added"), 0).toInt()));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::midiRecompose(const QString& midiPath, int startBar,
                               int endBar, const QString& style)
{
    if (midiPath.isEmpty()) { setError("Select a MIDI file first."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Recomposing MIDI…"));

    QVariantMap p;
    p[QStringLiteral("midi_path")]  = midiPath;
    p[QStringLiteral("start_bar")]  = startBar;
    p[QStringLiteral("end_bar")]    = endBar;
    if (!style.isEmpty())
        p[QStringLiteral("style")] = style;
    if (m_engine)
        p[QStringLiteral("bpm")] = m_engine->tempo();

    m_client->callAsync(QStringLiteral("midi_recompose"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("MIDI recompose failed.")).toString());
                return;
            }
            const QString path = result.value(QStringLiteral("midi_path")).toString();
            emit midiFileReady(path);
            setStatus(QStringLiteral("MIDI recomposed."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::midiLayer(const QString& midiPath, const QString& layerType,
                           const QString& key, const QString& scale)
{
    if (midiPath.isEmpty()) { setError("Select a MIDI file first."); return; }
    setGenerating(true);
    setStatus(QString("Generating %1 layer…").arg(layerType));

    QVariantMap p;
    p[QStringLiteral("midi_path")]   = midiPath;
    p[QStringLiteral("layer_type")]  = layerType;
    if (!key.isEmpty())
        p[QStringLiteral("key")] = key;
    if (!scale.isEmpty())
        p[QStringLiteral("scale")] = scale;
    if (m_engine)
        p[QStringLiteral("bpm")] = m_engine->tempo();

    m_client->callAsync(QStringLiteral("midi_layer"), p,
                        [this, layerType](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result, layerType]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("MIDI layer failed.")).toString());
                return;
            }
            // Emit as a single-part composeReady so it creates a new track
            const QString path = result.value(QStringLiteral("midi_path")).toString();
            const QString role = result.value(QStringLiteral("role"), layerType).toString();
            QVariantMap part;
            part[QStringLiteral("name")]       = role;
            part[QStringLiteral("midi_path")]  = path;
            part[QStringLiteral("note_count")] = result.value(QStringLiteral("note_count"), 0);
            part[QStringLiteral("color")]      = QStringLiteral("#81c784");
            emit composeReady(QVariantList{part},
                              QString("Added %1 layer").arg(role));
            setStatus(QString("%1 layer added.").arg(role));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// AI FX Chain (v0.12.0)
// ---------------------------------------------------------------------------

void AIBackend::textToFxChain(const QString& prompt, const QString& audioPath)
{
    if (prompt.trimmed().isEmpty()) { setError("Describe the sound you want."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Building FX chain…"));

    QVariantMap p;
    p[QStringLiteral("prompt")] = prompt.trimmed();
    if (!audioPath.isEmpty())
        p[QStringLiteral("audio_path")] = audioPath;

    m_client->callAsync(QStringLiteral("text_to_fx_chain"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("FX chain failed.")).toString());
                return;
            }
            const QVariantList chain = result.value(QStringLiteral("fx_chain")).toList();
            const QString outPath = result.value(QStringLiteral("audio_path")).toString();
            if (!outPath.isEmpty()) {
                emit audioReady(QStringLiteral("AI FX"), outPath, 0.0);
            }
            emit fxChainApplied(chain, outPath);
            setStatus(QString("Applied %1 FX.").arg(chain.size()));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Reference track analysis (v0.12.0)
// ---------------------------------------------------------------------------

void AIBackend::analyzeReference(const QString& audioPath)
{
    if (audioPath.isEmpty()) { setError("Select a reference audio file."); return; }
    setGenerating(true);
    setStatus(QStringLiteral("Analyzing reference track…"));

    QVariantMap p;
    p[QStringLiteral("audio_path")] = audioPath;

    m_client->callAsync(QStringLiteral("analyze_reference"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Reference analysis failed.")).toString());
                return;
            }
            emit referenceAnalyzed(result);
            setStatus(QStringLiteral("Reference analyzed."));
        }, Qt::QueuedConnection);
    });
}

void AIBackend::analyzeSongMaterial()
{
    if (!m_engine) { setError("No engine connected."); return; }
    const QVariantList tracks = m_engine->songAudioTracks();
    if (tracks.isEmpty()) { setError("No audio tracks in Song Editor."); return; }

    setGenerating(true);
    setStatus(QStringLiteral("Analyzing song material…"));

    // Collect all audio paths from Song Editor tracks
    QVariantList paths;
    for (const auto& t : tracks)
        paths.append(t.toMap().value(QStringLiteral("path")));

    QVariantMap p;
    p[QStringLiteral("audio_paths")] = paths;

    m_client->callAsync(QStringLiteral("analyze_song_material"), p,
                        [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            setGenerating(false);
            if (!ok || result.contains(QStringLiteral("error"))) {
                setError(result.value(QStringLiteral("error"),
                         QStringLiteral("Song analysis failed.")).toString());
                return;
            }
            emit songMaterialAnalyzed(result);
            setStatus(QStringLiteral("Song material analyzed."));
        }, Qt::QueuedConnection);
    });
}

// ---------------------------------------------------------------------------
// Mix fix dispatch
// ---------------------------------------------------------------------------

void AIBackend::applyMixFix(const QVariantMap& fixAction)
{
    if (fixAction.isEmpty()) return;
    emit actionsReady({ fixAction });
    setStatus("Mix fix applied: " + fixAction.value("type").toString());
}

// ---------------------------------------------------------------------------
// Console
// ---------------------------------------------------------------------------

void AIBackend::appendLog(const QString& msg)
{
    const QString line = QDateTime::currentDateTime().toString("[hh:mm:ss] ") + msg;
    m_consoleLog += line + "\n";
    emit consoleLogChanged();
}

void AIBackend::clearConsole()
{
    m_consoleLog.clear();
    emit consoleLogChanged();
}

void AIBackend::updateApiKeys(const QVariantMap& keys)
{
    m_client->callAsync("update_api_keys", keys,
        [this](bool ok, const QVariantMap& result) {
            if (ok) {
                const QStringList updated = result.value("updated").toStringList();
                QMetaObject::invokeMethod(this, [this, updated]() {
                    appendLog("[Settings] API keys updated: " + updated.join(", "));
                }, Qt::QueuedConnection);
            } else {
                QMetaObject::invokeMethod(this, [this]() {
                    appendLog("[Settings] Failed to push API keys to backend");
                }, Qt::QueuedConnection);
            }
        });
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

void AIBackend::checkStatus()
{
    m_client->checkStatus([this](bool ok, const QVariantMap&) {
        QMetaObject::invokeMethod(this, [this, ok]() {
            emit connectedChanged();
            setStatus(ok ? "Backend connected" : "Backend offline");
        }, Qt::QueuedConnection);
    });
}

void AIBackend::savePersona(const QString& name, const QString& voiceId,
                             double stability, double similarity)
{
    QVariantMap p;
    p["name"]       = name;
    p["voice_id"]   = voiceId;
    p["stability"]  = stability;
    p["similarity"] = similarity;

    m_client->savePersona(p, [this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok) setError(result.value("error").toString());
            else setStatus("Persona saved");
        }, Qt::QueuedConnection);
    });
}

QString AIBackend::browseAudioFile()
{
    return QFileDialog::getOpenFileName(
        nullptr, "Select Audio", {}, "Audio (*.wav *.mp3 *.flac *.ogg)");
}

QStringList AIBackend::browseAudioFiles()
{
    return QFileDialog::getOpenFileNames(
        nullptr, "Select Audio Files", {}, "Audio (*.wav *.mp3 *.flac)");
}

void AIBackend::insertGeneration(int index)
{
    if (index < 0 || index >= m_generations->rowCount()) return;
    const auto& e = m_generations->entryAt(index);
    emit insertRequested(e.audioPath, "AI Generated", e.sections);
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

QStringList AIBackend::recentProjects() const
{
#ifdef WAVY_LMMS_CORE
    return lmms::ConfigManager::inst()->recentlyOpenedProjects();
#else
    return {};
#endif
}

void AIBackend::openProject(const QString& path)
{
    emit projectOpenRequested(path);
}

// ---------------------------------------------------------------------------
// Model / Voice refresh
// ---------------------------------------------------------------------------

void AIBackend::refreshModels()
{
    m_modelNames.clear();
    m_modelIds.clear();

    // Always offer ElevenLabs
    m_modelNames << "ElevenLabs Music";
    m_modelIds   << "elevenlabs_music";

    // Check for local/cloud models via ModelManager
    if (m_modelManager) {
        for (const auto& info : m_modelManager->models()) {
            if (info.downloaded || info.isCloudApi) {
                m_modelNames << info.displayName;
                m_modelIds   << info.name;
            }
        }
    }

    emit modelsChanged();
}

void AIBackend::refreshVoices()
{
    m_client->elevenLabsListVoices([this](bool ok, const QVariantMap& result) {
        QMetaObject::invokeMethod(this, [this, ok, result]() {
            if (!ok) return;

            m_voiceNames.clear();
            m_voiceData.clear();

            const QVariantList voices = result.value("voices").toList();
            for (const auto& v : voices) {
                auto m = v.toMap();
                m_voiceNames << m.value("name").toString();
                m_voiceData  << v;
            }

            if (m_voiceNames.isEmpty()) {
                m_voiceNames << "George (Default)";
                QVariantMap def;
                def["voice_id"] = "JBFqnCBsd6RMkjVDRZzb";
                def["name"]     = "George (Default)";
                m_voiceData << def;
            }

            emit voicesChanged();
        }, Qt::QueuedConnection);
    });
}
