#pragma once

#include "EngineAPI.h"

// ---------------------------------------------------------------------------
// LmmsEngine — EngineAPI implementation wrapping LMMS Engine/Song/Mixer.
// Only compiled when WAVY_LMMS_CORE is defined.
// ---------------------------------------------------------------------------

#ifdef WAVY_LMMS_CORE

namespace lmms {
    class Song;
    class InstrumentTrack;
    namespace gui {
        class MainWindow;
        class PianoRollWindow;
    }
}

class LmmsEngine : public EngineAPI
{
    Q_OBJECT

public:
    explicit LmmsEngine(QObject* parent = nullptr);

    /// Set the piano roll window reference (for MIDI import).
    void setPianoRoll(lmms::gui::PianoRollWindow* pr) { m_pianoRoll = pr; }

    /// Set the main window reference (for project file operations).
    void setMainWindow(lmms::gui::MainWindow* win) { m_mainWindow = win; }

    // ── EngineAPI overrides ──────────────────────────────────────────────────

    int  tempo() const override;
    void setTempo(int bpm) override;
    void setMasterPitch(int semitones) override;
    void setTimeSignature(int numerator, int denominator) override;

    void play() override;
    void pause() override;
    void stop() override;
    void record() override;

    bool isPlaying() const override;
    bool isPaused() const override;
    bool isRecording() const override;

    int  masterVolume() const override;
    void setMasterVolume(int vol) override;

    int  masterPitch() const override;
    int  timeSigNumerator() const override;
    int  timeSigDenominator() const override;
    bool isMetronomeActive() const override;
    void setMetronomeActive(bool active) override;
    int  playPositionTicks() const override;
    int  cpuLoad() const override;

    int         trackCount() const override;
    QStringList trackNames() const override;
    void addTrack(const QString& type, const QString& name) override;
    void deleteTrack(int index) override;
    void duplicateTrack(int index) override;
    void setTrackVolume(int trackIndex, double volume) override;
    void setTrackPan(int trackIndex, double pan) override;

    void addClip(int trackIndex, int bar, int lengthBars) override;
    void transposeClip(int trackIndex, int clipIndex, int semitones) override;

    void insertAudioTrack(const QString& name,
                          const QString& audioPath,
                          const QColor&  color) override;
    void insertAudioTrackWithSections(const QString& name,
                                      const QString& audioPath,
                                      const QColor&  color,
                                      const QVariantList& sections) override;
    void insertStemTracks(const QStringList& audioPaths,
                          const QStringList& stemNames) override;

    int  mixerChannelCount() const override;

    QString mixerChannelName(int channel) const override;
    void    setMixerChannelName(int channel, const QString& name) override;

    float mixerChannelVolume(int channel) const override;
    void  setMixerChannelVolume(int channel, float volume) override;

    bool mixerChannelMuted(int channel) const override;
    void setMixerChannelMuted(int channel, bool muted) override;

    bool mixerChannelSoloed(int channel) const override;
    void setMixerChannelSoloed(int channel, bool soloed) override;

    float mixerChannelPeakLeft(int channel) const override;
    float mixerChannelPeakRight(int channel) const override;
    void  resetMixerChannelPeaks(int channel) override;

    QColor mixerChannelColor(int channel) const override;
    void   setMixerChannelColor(int channel, const QColor& color) override;

    QVariantList mixerChannelSends(int channel) const override;

    void addReverbToChannel(int channel, double wetAmount) override;
    void applyAutoMix(const QVariantList& suggestions) override;

    int songLengthBars() const override;

    bool trackMuted(int trackIndex) const override;
    void setTrackMuted(int trackIndex, bool muted) override;
    bool trackSoloed(int trackIndex) const override;
    void setTrackSoloed(int trackIndex, bool soloed) override;

    QColor trackColor(int trackIndex) const override;
    void   setTrackColor(int trackIndex, const QColor& color) override;

    QString trackType(int trackIndex) const override;

    void importMidiToActiveClip(const QString& midiPath) override;
    void importMidiFile(const QString& midiPath) override;
    void createMidiTrack(const QString& name, const QString& midiPath,
                         const QColor& color, int bars = 4,
                         const QString& instrument = {},
                         const QString& presetName = {},
                         int startBar = 0,
                         double reverbWet = 0.0,
                         int gmPatch = -1) override;
    void replaceNotesInBar(const QString& trackName, int barIndex,
                            const QString& midiPath) override;
    void insertChordToActiveClip(const QList<int>& pitches, int barIndex,
                                  double durationBeats) override;
    void insertBeatPattern(const QVariantList& rows, int bpm, int bars) override;

    void createNewProject() override;
    void openProject() override;
    void saveProject() override;

    QVariantList existingMidiNotes() const override;
    QVariantList songAudioTracks()   const override;

    // Genre mode — apply DAW params + FX + instrument tracks
    void applyGenreMode(const QString& modeKey);
    void clearMasterFx();
    void addFxToMaster(const QString& fxName);
    void createGenreInstrumentTracks(const QString& modeKey);
    void createCustomInstrumentTracks(const QVariantList& instrSlots);

    // Genre instrument config — plugin/preset discovery
    QVariantList availableInstrumentPlugins() const;
    QStringList  presetsForPlugin(const QString& pluginName) const;

    // Add an instrument track with a specified plugin and optional preset/sample
    bool addEmptyInstrumentTrack(const QString& pluginName, const QString& trackName,
                                  const QString& preset = {}, const QString& samplePath = {});

private:
    lmms::Song* song() const;
    void loadXpfPreset(lmms::InstrumentTrack* it, const QString& presetName);
    lmms::gui::PianoRollWindow* m_pianoRoll{nullptr};
    lmms::gui::MainWindow*      m_mainWindow{nullptr};
};

#endif // WAVY_LMMS_CORE
