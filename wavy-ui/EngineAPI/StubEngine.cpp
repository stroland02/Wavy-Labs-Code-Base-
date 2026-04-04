#include "StubEngine.h"
#include <QDebug>

StubEngine::StubEngine(QObject* parent)
    : EngineAPI(parent)
{
}

int StubEngine::tempo() const { return m_tempo; }

void StubEngine::setTempo(int bpm)
{
    m_tempo = std::clamp(bpm, 10, 999);
    qDebug() << "[StubEngine] setTempo" << m_tempo;
}

void StubEngine::setMasterPitch(int semitones)
{
    m_masterPitch = std::clamp(semitones, -12, 12);
    qDebug() << "[StubEngine] setMasterPitch" << m_masterPitch;
}

int  StubEngine::masterPitch() const { return m_masterPitch; }
int  StubEngine::timeSigNumerator() const { return m_timeSigNumerator; }
int  StubEngine::timeSigDenominator() const { return m_timeSigDenominator; }
bool StubEngine::isMetronomeActive() const { return m_metronomeActive; }
void StubEngine::setMetronomeActive(bool active)
{
    m_metronomeActive = active;
    qDebug() << "[StubEngine] setMetronomeActive" << active;
}

void StubEngine::setTimeSignature(int numerator, int denominator)
{
    m_timeSigNumerator   = numerator;
    m_timeSigDenominator = denominator;
    qDebug() << "[StubEngine] setTimeSignature" << numerator << "/" << denominator;
}

void StubEngine::play()   { m_playing = true; m_paused = false; emit playbackStateChanged(); }
void StubEngine::pause()  { m_paused = !m_paused; emit playbackStateChanged(); }
void StubEngine::stop()   { m_playing = false; m_paused = false; emit playbackStateChanged(); }
void StubEngine::record() { m_recording = true; m_playing = true; emit playbackStateChanged(); }

bool StubEngine::isPlaying() const   { return m_playing && !m_paused; }
bool StubEngine::isPaused() const    { return m_paused; }
bool StubEngine::isRecording() const { return m_recording; }

int  StubEngine::masterVolume() const { return m_masterVolume; }
void StubEngine::setMasterVolume(int vol) { m_masterVolume = std::clamp(vol, 0, 200); emit masterVolumeChanged(m_masterVolume); }

int StubEngine::trackCount() const { return m_trackNames.size(); }

QStringList StubEngine::trackNames() const { return m_trackNames; }

void StubEngine::addTrack(const QString& type, const QString& name)
{
    m_trackNames.append(name);
    qDebug() << "[StubEngine] addTrack" << type << name;
    emit trackListChanged();
}

void StubEngine::deleteTrack(int index)
{
    if (index >= 0 && index < m_trackNames.size()) {
        m_trackNames.removeAt(index);
        emit trackListChanged();
    }
    qDebug() << "[StubEngine] deleteTrack" << index;
}

void StubEngine::duplicateTrack(int index)
{
    if (index >= 0 && index < m_trackNames.size()) {
        m_trackNames.insert(index + 1, m_trackNames.at(index) + " (copy)");
        emit trackListChanged();
    }
    qDebug() << "[StubEngine] duplicateTrack" << index;
}

void StubEngine::setTrackVolume(int trackIndex, double volume)
{
    qDebug() << "[StubEngine] setTrackVolume track" << trackIndex << "→" << volume;
}

void StubEngine::setTrackPan(int trackIndex, double pan)
{
    qDebug() << "[StubEngine] setTrackPan track" << trackIndex << "→" << pan;
}

void StubEngine::addClip(int trackIndex, int bar, int lengthBars)
{
    qDebug() << "[StubEngine] addClip track" << trackIndex
             << "bar" << bar << "len" << lengthBars;
}

void StubEngine::transposeClip(int trackIndex, int clipIndex, int semitones)
{
    qDebug() << "[StubEngine] transposeClip track" << trackIndex
             << "clip" << clipIndex << "semitones" << semitones;
}

void StubEngine::insertAudioTrack(const QString& name,
                                   const QString& audioPath,
                                   const QColor&  color)
{
    m_trackNames.append(name);
    qDebug() << "[StubEngine] insertAudioTrack" << name
             << audioPath << "color:" << color.name();
    emit trackListChanged();
}

void StubEngine::insertAudioTrackWithSections(const QString& name,
                                               const QString& audioPath,
                                               const QColor&  color,
                                               const QVariantList& sections)
{
    m_trackNames.append(name);
    qDebug() << "[StubEngine] insertAudioTrackWithSections" << name
             << audioPath << sections.size() << "sections";
    Q_UNUSED(color);
    emit trackListChanged();
}

void StubEngine::insertStemTracks(const QStringList& audioPaths,
                                   const QStringList& stemNames)
{
    for (const auto& n : stemNames)
        m_trackNames.append(n);
    qDebug() << "[StubEngine] insertStemTracks" << stemNames;
    Q_UNUSED(audioPaths);
    emit trackListChanged();
}

int StubEngine::mixerChannelCount() const { return 8; }

QString StubEngine::mixerChannelName(int channel) const
{
    if (channel == 0) return "Master";
    return QString("Ch %1").arg(channel);
}

void StubEngine::setMixerChannelName(int channel, const QString& name)
{
    qDebug() << "[StubEngine] setMixerChannelName ch" << channel << "→" << name;
}

float StubEngine::mixerChannelVolume(int channel) const
{
    Q_UNUSED(channel);
    return 1.0f;
}

void StubEngine::setMixerChannelVolume(int channel, float volume)
{
    qDebug() << "[StubEngine] setMixerChannelVolume ch" << channel << "→" << volume;
}

bool StubEngine::mixerChannelMuted(int channel) const { Q_UNUSED(channel); return false; }
void StubEngine::setMixerChannelMuted(int channel, bool muted)
{
    qDebug() << "[StubEngine] setMixerChannelMuted ch" << channel << "→" << muted;
}

bool StubEngine::mixerChannelSoloed(int channel) const { Q_UNUSED(channel); return false; }
void StubEngine::setMixerChannelSoloed(int channel, bool soloed)
{
    qDebug() << "[StubEngine] setMixerChannelSoloed ch" << channel << "→" << soloed;
}

float StubEngine::mixerChannelPeakLeft(int channel) const { Q_UNUSED(channel); return 0.0f; }
float StubEngine::mixerChannelPeakRight(int channel) const { Q_UNUSED(channel); return 0.0f; }
void  StubEngine::resetMixerChannelPeaks(int channel) { Q_UNUSED(channel); }

QColor StubEngine::mixerChannelColor(int channel) const { Q_UNUSED(channel); return QColor(); }
void   StubEngine::setMixerChannelColor(int channel, const QColor& color)
{
    qDebug() << "[StubEngine] setMixerChannelColor ch" << channel << "→" << color.name();
}

QVariantList StubEngine::mixerChannelSends(int channel) const
{
    Q_UNUSED(channel);
    return {};
}

void StubEngine::addReverbToChannel(int channel, double wetAmount)
{
    qDebug() << "[StubEngine] addReverbToChannel ch" << channel << "wet" << wetAmount;
}

void StubEngine::applyAutoMix(const QVariantList& suggestions)
{
    qDebug() << "[StubEngine] applyAutoMix" << suggestions.size() << "suggestions";
}

int StubEngine::songLengthBars() const { return 64; }

bool StubEngine::trackMuted(int trackIndex) const { Q_UNUSED(trackIndex); return false; }
void StubEngine::setTrackMuted(int trackIndex, bool muted)
{
    qDebug() << "[StubEngine] setTrackMuted" << trackIndex << muted;
}
bool StubEngine::trackSoloed(int trackIndex) const { Q_UNUSED(trackIndex); return false; }
void StubEngine::setTrackSoloed(int trackIndex, bool soloed)
{
    qDebug() << "[StubEngine] setTrackSoloed" << trackIndex << soloed;
}

QColor StubEngine::trackColor(int trackIndex) const { Q_UNUSED(trackIndex); return QColor("#4fc3f7"); }
void   StubEngine::setTrackColor(int trackIndex, const QColor& color)
{
    qDebug() << "[StubEngine] setTrackColor" << trackIndex << color.name();
}

QString StubEngine::trackType(int trackIndex) const
{
    Q_UNUSED(trackIndex);
    return "pattern";
}

void StubEngine::importMidiToActiveClip(const QString& midiPath)
{
    qDebug() << "[StubEngine] importMidiToActiveClip" << midiPath;
}

void StubEngine::createNewProject()
{
    m_trackNames.clear();
    m_tempo = 120;
    qDebug() << "[StubEngine] createNewProject";
    emit trackListChanged();
}

void StubEngine::openProject()
{
    qDebug() << "[StubEngine] openProject";
}

void StubEngine::saveProject()
{
    qDebug() << "[StubEngine] saveProject";
}
