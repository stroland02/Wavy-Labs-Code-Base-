#pragma once

#include "EngineAPI.h"

// ---------------------------------------------------------------------------
// StubEngine — EngineAPI stub for standalone dev harness.
// Logs all calls, tracks state in memory. No real DAW.
// ---------------------------------------------------------------------------

class StubEngine : public EngineAPI
{
    Q_OBJECT

public:
    explicit StubEngine(QObject* parent = nullptr);

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
    int  playPositionTicks() const override { return 0; }
    int  cpuLoad() const override { return 0; }

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

    void createNewProject() override;
    void openProject() override;
    void saveProject() override;

private:
    int  m_tempo{120};
    int  m_masterVolume{100};
    int  m_masterPitch{0};
    int  m_timeSigNumerator{4};
    int  m_timeSigDenominator{4};
    bool m_playing{false};
    bool m_paused{false};
    bool m_recording{false};
    bool m_metronomeActive{false};
    QStringList m_trackNames;
};
