#pragma once

#include <QColor>
#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>

// ---------------------------------------------------------------------------
// EngineAPI — pure abstract interface decoupling UI from any DAW engine.
//
// Concrete implementations:
//   LmmsEngine  — wraps LMMS Engine/Song/Mixer (WAVY_LMMS_CORE build)
//   StubEngine  — logs calls, no real DAW (standalone dev harness)
//
// All methods are called from the GUI thread.
// ---------------------------------------------------------------------------

class EngineAPI : public QObject
{
    Q_OBJECT

public:
    using QObject::QObject;
    ~EngineAPI() override = default;

    // ── Transport ────────────────────────────────────────────────────────────

    virtual int  tempo() const = 0;
    virtual void setTempo(int bpm) = 0;

    virtual void setMasterPitch(int semitones) = 0;

    virtual void setTimeSignature(int numerator, int denominator) = 0;

    virtual void play() = 0;
    virtual void pause() = 0;
    virtual void stop() = 0;
    virtual void record() = 0;

    virtual bool isPlaying() const = 0;
    virtual bool isPaused() const = 0;
    virtual bool isRecording() const = 0;

    virtual int  masterVolume() const = 0;
    virtual void setMasterVolume(int vol) = 0;

    virtual int  masterPitch() const = 0;
    virtual int  timeSigNumerator() const = 0;
    virtual int  timeSigDenominator() const = 0;
    virtual bool isMetronomeActive() const = 0;
    virtual void setMetronomeActive(bool active) = 0;

    /// Playback position in ticks (192 ticks per bar; 48 ticks per quarter-note beat).
    virtual int  playPositionTicks() const = 0;

    /// CPU load of the audio engine, 0–100 %.
    virtual int  cpuLoad() const = 0;

    // ── Tracks ───────────────────────────────────────────────────────────────

    virtual int         trackCount() const = 0;
    virtual QStringList trackNames() const = 0;

    /// @param type  "sample", "pattern", "automation"
    virtual void addTrack(const QString& type, const QString& name) = 0;
    virtual void deleteTrack(int index) = 0;
    virtual void duplicateTrack(int index) = 0;

    /// volume: 0.0–2.0 (1.0 = 100%)
    virtual void setTrackVolume(int trackIndex, double volume) = 0;
    /// pan: -1.0 … 1.0
    virtual void setTrackPan(int trackIndex, double pan) = 0;

    // ── Clips ────────────────────────────────────────────────────────────────

    virtual void addClip(int trackIndex, int bar, int lengthBars) = 0;
    virtual void transposeClip(int trackIndex, int clipIndex, int semitones) = 0;

    // ── Audio Track Insertion ────────────────────────────────────────────────

    virtual void insertAudioTrack(const QString& name,
                                  const QString& audioPath,
                                  const QColor&  color) = 0;

    /// Insert a track with multiple clips, one per section.
    /// sections: list of maps with "start_sec", "end_sec", "label".
    virtual void insertAudioTrackWithSections(const QString& name,
                                              const QString& audioPath,
                                              const QColor&  color,
                                              const QVariantList& sections) = 0;

    /// Insert multiple stems as separate color-coded SampleTracks.
    virtual void insertStemTracks(const QStringList& audioPaths,
                                  const QStringList& stemNames) = 0;

    // ── Mixer ────────────────────────────────────────────────────────────────

    virtual int  mixerChannelCount() const = 0;

    virtual QString mixerChannelName(int channel) const = 0;
    virtual void    setMixerChannelName(int channel, const QString& name) = 0;

    virtual float mixerChannelVolume(int channel) const = 0;
    virtual void  setMixerChannelVolume(int channel, float volume) = 0;

    virtual bool mixerChannelMuted(int channel) const = 0;
    virtual void setMixerChannelMuted(int channel, bool muted) = 0;

    virtual bool mixerChannelSoloed(int channel) const = 0;
    virtual void setMixerChannelSoloed(int channel, bool soloed) = 0;

    /// Peak levels (0.0–1.0+). Updated by audio engine each period.
    virtual float mixerChannelPeakLeft(int channel) const = 0;
    virtual float mixerChannelPeakRight(int channel) const = 0;
    virtual void  resetMixerChannelPeaks(int channel) = 0;

    virtual QColor mixerChannelColor(int channel) const = 0;
    virtual void   setMixerChannelColor(int channel, const QColor& color) = 0;

    /// Send routing: returns list of {receiverChannel, amount} pairs.
    virtual QVariantList mixerChannelSends(int channel) const = 0;

    virtual void addReverbToChannel(int channel, double wetAmount) = 0;

    /// Apply a list of auto-mix gain suggestions.
    /// Each map: {"channel": int, "gain_db": float}
    virtual void applyAutoMix(const QVariantList& suggestions) = 0;

    // ── Arrangement ────────────────────────────────────────────────────────

    virtual int songLengthBars() const = 0;

    /// Track mute/solo state
    virtual bool trackMuted(int trackIndex) const = 0;
    virtual void setTrackMuted(int trackIndex, bool muted) = 0;
    virtual bool trackSoloed(int trackIndex) const = 0;
    virtual void setTrackSoloed(int trackIndex, bool soloed) = 0;

    /// Track color
    virtual QColor trackColor(int trackIndex) const = 0;
    virtual void   setTrackColor(int trackIndex, const QColor& color) = 0;

    /// Track type: "sample", "pattern", "automation"
    virtual QString trackType(int trackIndex) const = 0;

    // ── MIDI ─────────────────────────────────────────────────────────────────

    /// Import MIDI file into the currently active piano roll clip.
    virtual void importMidiToActiveClip(const QString& midiPath) = 0;

    /// Import a raw MIDI file the same way File → Import MIDI does:
    /// creates one InstrumentTrack per MIDI channel via ImportFilter plugin.
    virtual void importMidiFile(const QString& midiPath) { Q_UNUSED(midiPath) }

    /// Create a new InstrumentTrack and populate it from a MIDI file.
    /// name: track label shown in Song Editor.
    /// midiPath: absolute path to a MIDI file produced by the compose agent.
    /// color: track header colour.
    /// bars: expected length (used when clipping is created).
    /// instrument: plugin name to load (e.g. "tripleoscillator", "lb302", "kicker").
    /// presetName: relative path to XPF preset under lmms data/presets/ (optional).
    /// reverbWet: per-track reverb wet amount (0.0 = dry, >0 adds ReverbSC on a mixer channel).
    /// gmPatch: GM program number for sf2player (-1 = use plugin default).
    virtual void createMidiTrack(const QString& name,
                                  const QString& midiPath,
                                  const QColor&  color,
                                  int            bars = 4,
                                  const QString& instrument = {},
                                  const QString& presetName = {},
                                  int            startBar = 0,
                                  double         reverbWet = 0.0,
                                  int            gmPatch = -1) {
        Q_UNUSED(name) Q_UNUSED(midiPath) Q_UNUSED(color) Q_UNUSED(bars)
        Q_UNUSED(instrument) Q_UNUSED(presetName) Q_UNUSED(startBar)
        Q_UNUSED(reverbWet) Q_UNUSED(gmPatch)
    }

    /// Replace all notes in a single bar of a named track.
    /// barIndex: 0-based. midiPath: single-bar MIDI file (notes offset to bar 0).
    virtual void replaceNotesInBar(const QString& trackName, int barIndex,
                                    const QString& midiPath) {
        Q_UNUSED(trackName) Q_UNUSED(barIndex) Q_UNUSED(midiPath)
    }

    /// Insert a chord voicing into the active piano roll clip at barIndex.
    /// pitches: list of MIDI note numbers; durationBeats: note length.
    virtual void insertChordToActiveClip(const QList<int>& pitches, int barIndex,
                                          double durationBeats) {
        Q_UNUSED(pitches) Q_UNUSED(barIndex) Q_UNUSED(durationBeats)
    }

    /// Create drum InstrumentTracks from a 16-step beat grid.
    /// rows: [{name, color, steps:[bool×16]}]; bpm/bars for positioning.
    virtual void insertBeatPattern(const QVariantList& rows, int bpm, int bars) {
        Q_UNUSED(rows) Q_UNUSED(bpm) Q_UNUSED(bars)
    }

    // ── Session analysis ─────────────────────────────────────────────────────

    /// Return a flat list of all MIDI pitch integers currently in the Song's
    /// InstrumentTracks (used for key detection before compose).
    /// Default implementation returns empty list (StubEngine, no tracks).
    virtual QVariantList existingMidiNotes() const { return {}; }

    /// Return a list of {name, path} maps for every SampleTrack in the Song
    /// that has at least one clip with a file loaded.
    /// Used to populate the stem-split track picker in the Mix tab.
    virtual QVariantList songAudioTracks() const { return {}; }

    // ── Project ──────────────────────────────────────────────────────────────

    virtual void createNewProject() = 0;
    virtual void openProject() = 0;
    virtual void saveProject() = 0;

    // ── Batch Action Dispatch ────────────────────────────────────────────────

    /// Dispatch a list of action maps (from prompt commands / chat).
    /// Each map has a "type" key. Calls the appropriate virtual methods above.
    void dispatchActions(const QVariantList& actions);

Q_SIGNALS:
    void tempoChanged(int bpm);
    void trackListChanged();
    void playbackStateChanged();   // isPlaying/isPaused/isStopped changed
    void masterVolumeChanged(int vol);
    void mixerChannelCountChanged();
    void songLengthChanged(int bars);
};
