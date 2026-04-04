#ifdef WAVY_LMMS_CORE

#include "LmmsEngine.h"
#include "../QML/GenreModes.h"

#include "Song.h"
#include "Engine.h"
#include "MainWindow.h"
#include "Track.h"
#include "SampleTrack.h"
#include "SampleClip.h"
#include "InstrumentTrack.h"
#include "Instrument.h"
#include "PatternTrack.h"
#include "AutomationClip.h"
#include "Mixer.h"
#include "MixerView.h"
#include "EffectChain.h"
#include "Effect.h"
#include "MidiClip.h"
#include "Note.h"
#include "TimePos.h"
#include "PianoRoll.h"
#include "AudioEngine.h"

#include "ConfigManager.h"
#include "ImportFilter.h"
#include "PluginFactory.h"
#include <QColor>
#include <QDir>
#include <QDomDocument>
#include <QFile>
#include <QDebug>
#include <QMap>
#include <QMetaObject>
#include <algorithm>
#include <cmath>

// LMMS ticks per beat in 4/4 time (DefaultTicksPerBar = 192, / 4 beats = 48)
static constexpr int LMMS_TICKS_PER_BEAT = lmms::DefaultTicksPerBar / 4;  // 48

// ── Shared MIDI binary parser ────────────────────────────────────────────────
struct ParsedMidiNote {
    uint32_t startTick;
    uint32_t endTick;
    int      key;
    int      vel;
};

/// Parse all note-on/off events from a Standard MIDI File stored in `data`.
/// Returns an empty vector if the file is invalid or contains no notes.
/// `ppqOut` is set to the file's ticks-per-quarter-note value.
static std::vector<ParsedMidiNote> parseMidiNotes(const QByteArray& data,
                                                   uint16_t* ppqOut = nullptr)
{
    std::vector<ParsedMidiNote> result;

    if (data.size() < 14 || data.mid(0, 4) != "MThd")
        return result;

    auto u16 = [&](int off) -> uint16_t {
        return (uint8_t(data[off]) << 8) | uint8_t(data[off + 1]);
    };
    auto u32 = [&](int off) -> uint32_t {
        return (uint8_t(data[off]) << 24) | (uint8_t(data[off+1]) << 16)
             | (uint8_t(data[off+2]) << 8) | uint8_t(data[off+3]);
    };

    if (u32(4) != 6) return result;
    uint16_t ppq = u16(12);
    if (ppq == 0) ppq = 480;
    if (ppqOut) *ppqOut = ppq;

    int chunkPos = 14;
    while (chunkPos + 8 <= data.size()) {
        if (data.mid(chunkPos, 4) != "MTrk") {
            chunkPos += 8 + u32(chunkPos + 4);
            continue;
        }
        int trkEnd = chunkPos + 8 + u32(chunkPos + 4);
        int pos = chunkPos + 8;

        auto readVLQ = [&](int& p) -> uint32_t {
            uint32_t val = 0;
            for (int i = 0; i < 4 && p < trkEnd; ++i) {
                uint8_t b = uint8_t(data[p++]);
                val = (val << 7) | (b & 0x7F);
                if (!(b & 0x80)) break;
            }
            return val;
        };

        std::vector<ParsedMidiNote> pending;
        uint32_t absTick = 0;
        uint8_t runStatus = 0;

        while (pos < trkEnd) {
            uint32_t delta = readVLQ(pos);
            absTick += delta;
            if (pos >= trkEnd) break;

            uint8_t status = uint8_t(data[pos]);
            if (status & 0x80) {
                if (status != 0xFF && status != 0xF0 && status != 0xF7)
                    runStatus = status;
                pos++;
            } else {
                status = runStatus;
            }

            if (status == 0xFF) {
                if (pos < trkEnd) pos++;
                uint32_t len = readVLQ(pos);
                pos += static_cast<int>(len);
            } else {
                uint8_t type = status & 0xF0;
                if (type == 0x90 && pos + 1 < trkEnd) {
                    int key = uint8_t(data[pos++]);
                    int vel = uint8_t(data[pos++]);
                    if (vel > 0) {
                        pending.push_back({absTick, 0, key, vel});
                    } else {
                        for (auto it2 = pending.rbegin(); it2 != pending.rend(); ++it2) {
                            if (it2->key == key) {
                                it2->endTick = absTick;
                                result.push_back(*it2);
                                pending.erase((it2 + 1).base());
                                break;
                            }
                        }
                    }
                } else if (type == 0x80 && pos + 1 < trkEnd) {
                    int key = uint8_t(data[pos++]); pos++;
                    for (auto it2 = pending.rbegin(); it2 != pending.rend(); ++it2) {
                        if (it2->key == key) {
                            it2->endTick = absTick;
                            result.push_back(*it2);
                            pending.erase((it2 + 1).base());
                            break;
                        }
                    }
                } else if (type == 0xC0 || type == 0xD0) {
                    if (pos < trkEnd) pos++;
                } else if (type == 0xF0 || type == 0xF7) {
                    uint32_t len = readVLQ(pos);
                    pos += static_cast<int>(len);
                } else {
                    if (pos + 1 < trkEnd) pos += 2;
                    else pos++;
                }
            }
        }
        for (auto& n : pending) { n.endTick = absTick; result.push_back(n); }
        chunkPos = trkEnd;
    }
    return result;
}

// ---------------------------------------------------------------------------

LmmsEngine::LmmsEngine(QObject* parent)
    : EngineAPI(parent)
{
}

lmms::Song* LmmsEngine::song() const
{
    return lmms::Engine::getSong();
}

// ── Transport ────────────────────────────────────────────────────────────────

int LmmsEngine::tempo() const
{
    auto* s = song();
    return s ? static_cast<int>(s->tempoModel().value()) : 120;
}

void LmmsEngine::setTempo(int bpm)
{
    auto* s = song();
    if (s) {
        bpm = std::clamp(bpm, 10, 999);
        s->tempoModel().setValue(bpm);
        emit tempoChanged(bpm);  // update TransportBar BPM display
        qDebug() << "[LmmsEngine] setTempo" << bpm;
    }
}

void LmmsEngine::setMasterPitch(int semitones)
{
    auto* s = song();
    if (s) {
        s->setMasterPitch(semitones);
        qDebug() << "[LmmsEngine] setMasterPitch" << semitones;
    }
}

void LmmsEngine::play()
{
    auto* s = song();
    if (s) s->playSong();
}

void LmmsEngine::pause()
{
    auto* s = song();
    if (s) s->togglePause();
}

void LmmsEngine::stop()
{
    auto* s = song();
    if (s) s->stop();
}

void LmmsEngine::record()
{
    auto* s = song();
    if (s) s->record();
}

bool LmmsEngine::isPlaying() const
{
    auto* s = song();
    return s ? s->isPlaying() : false;
}

bool LmmsEngine::isPaused() const
{
    auto* s = song();
    return s ? s->isPaused() : false;
}

bool LmmsEngine::isRecording() const
{
    auto* s = song();
    return s ? s->isRecording() : false;
}

int LmmsEngine::masterVolume() const
{
    auto* s = song();
    return s ? s->masterVolume() : 100;
}

void LmmsEngine::setMasterVolume(int vol)
{
    auto* s = song();
    if (s) s->setMasterVolume(std::clamp(vol, 0, 200));
}

int LmmsEngine::masterPitch() const
{
    auto* s = song();
    return s ? s->masterPitch() : 0;
}

int LmmsEngine::timeSigNumerator() const
{
    auto* s = song();
    return s ? s->getTimeSigModel().getNumerator() : 4;
}

int LmmsEngine::timeSigDenominator() const
{
    auto* s = song();
    return s ? s->getTimeSigModel().getDenominator() : 4;
}

bool LmmsEngine::isMetronomeActive() const
{
    // LMMS does not expose metronome state via a simple boolean;
    // return false as default — the button is cosmetic for now.
    return false;
}

int LmmsEngine::playPositionTicks() const
{
    auto* s = song();
    return s ? static_cast<int>(s->getPlayPos().getTicks()) : 0;
}

int LmmsEngine::cpuLoad() const
{
    auto* ae = lmms::Engine::audioEngine();
    return ae ? ae->cpuLoad() : 0;
}

void LmmsEngine::setMetronomeActive(bool active)
{
    // Toggle metronome via MainWindow's toolbar action if available.
    // LMMS hides metronome state in its toolbar; we invoke the slot by name.
    if (m_mainWindow)
        QMetaObject::invokeMethod(m_mainWindow, "toggleMetronome",
                                  Q_ARG(bool, active));
    qDebug() << "[LmmsEngine] setMetronomeActive" << active;
}

void LmmsEngine::setTimeSignature(int numerator, int denominator)
{
    auto* s = song();
    if (!s) return;
    s->getTimeSigModel().setNumerator(std::clamp(numerator, 1, 32));
    s->getTimeSigModel().setDenominator(std::clamp(denominator, 1, 32));
    qDebug() << "[LmmsEngine] setTimeSignature" << numerator << "/" << denominator;
}

// ── Tracks ───────────────────────────────────────────────────────────────────

int LmmsEngine::trackCount() const
{
    auto* s = song();
    return s ? static_cast<int>(s->tracks().size()) : 0;
}

QStringList LmmsEngine::trackNames() const
{
    QStringList names;
    auto* s = song();
    if (s) {
        for (auto* t : s->tracks())
            names.append(t->name());
    }
    return names;
}

void LmmsEngine::addTrack(const QString& type, const QString& name)
{
    auto* s = song();
    if (!s) return;

    lmms::Track::Type tt = lmms::Track::Type::Sample;
    if (type == "beat" || type == "pattern")
        tt = lmms::Track::Type::Pattern;
    else if (type == "automation")
        tt = lmms::Track::Type::Automation;

    lmms::Track* t = lmms::Track::create(tt, s);
    if (t) t->setName(name);
    qDebug() << "[LmmsEngine] addTrack" << type << name;
}

void LmmsEngine::deleteTrack(int index)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (index >= 0 && index < static_cast<int>(tracks.size()))
        s->removeTrack(tracks.at(index));
}

void LmmsEngine::duplicateTrack(int index)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (index >= 0 && index < static_cast<int>(tracks.size()))
        tracks.at(index)->clone();
}

void LmmsEngine::setTrackVolume(int trackIndex, double volume)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;

    auto* it = dynamic_cast<lmms::InstrumentTrack*>(tracks.at(trackIndex));
    if (it) {
        it->setVolume(static_cast<int>(volume * 100.0));
    } else {
        auto* st = dynamic_cast<lmms::SampleTrack*>(tracks.at(trackIndex));
        if (st)
            st->volumeModel()->setValue(static_cast<float>(volume * 100.0f));
        else
            qWarning() << "[LmmsEngine] setTrackVolume: unsupported track type at" << trackIndex;
    }
}

void LmmsEngine::setTrackPan(int trackIndex, double pan)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;

    auto* it = dynamic_cast<lmms::InstrumentTrack*>(tracks.at(trackIndex));
    if (it) {
        it->panningModel()->setValue(static_cast<float>(pan * 100.0));
    } else {
        auto* st = dynamic_cast<lmms::SampleTrack*>(tracks.at(trackIndex));
        if (st)
            st->panningModel()->setValue(static_cast<float>(pan * 100.0f));
        else
            qWarning() << "[LmmsEngine] setTrackPan: unsupported track type at" << trackIndex;
    }
}

// ── Clips ────────────────────────────────────────────────────────────────────

void LmmsEngine::addClip(int trackIndex, int bar, int lengthBars)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;

    lmms::TimePos pos(bar * lmms::DefaultTicksPerBar);
    auto* clip = tracks.at(trackIndex)->createClip(pos);
    if (clip)
        clip->changeLength(lmms::TimePos(lengthBars * lmms::DefaultTicksPerBar));
}

void LmmsEngine::transposeClip(int trackIndex, int clipIndex, int semitones)
{
    if (semitones == 0) return;
    auto* s = song();
    if (!s) return;

    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;

    lmms::Track* track = tracks.at(trackIndex);
    if (!track) return;

    lmms::Clip* rawClip = track->getClip(static_cast<std::size_t>(clipIndex));
    auto* midiClip = dynamic_cast<lmms::MidiClip*>(rawClip);
    if (!midiClip) {
        qWarning() << "[LmmsEngine] transposeClip: clip" << clipIndex
                   << "on track" << trackIndex << "is not a MidiClip";
        return;
    }

    track->lock();
    for (lmms::Note* note : midiClip->notes()) {
        if (note)
            note->setKey(std::clamp(note->key() + semitones, 0, lmms::NumKeys - 1));
    }
    track->unlock();

    emit midiClip->dataChanged();
    qDebug() << "[LmmsEngine] transposeClip track" << trackIndex
             << "clip" << clipIndex << "semitones" << semitones;
}

// ── Audio Track Insertion ────────────────────────────────────────────────────

void LmmsEngine::insertAudioTrack(const QString& name,
                                   const QString& audioPath,
                                   const QColor&  color)
{
    if (audioPath.isEmpty()) return;
    auto* s = song();
    if (!s) return;

    auto* track = dynamic_cast<lmms::SampleTrack*>(
        lmms::Track::create(lmms::Track::Type::Sample, s));
    if (!track) return;
    track->setName(name);
    track->setColor(color);
    auto* clip = dynamic_cast<lmms::SampleClip*>(
        track->createClip(lmms::TimePos(0)));
    if (clip) {
        clip->setSampleFile(audioPath);
        clip->updateLength();
    }
    qDebug() << "[LmmsEngine] insertAudioTrack" << name << audioPath;
}

void LmmsEngine::insertAudioTrackWithSections(const QString& name,
                                                const QString& audioPath,
                                                const QColor&  color,
                                                const QVariantList& sections)
{
    if (audioPath.isEmpty()) return;
    auto* s = song();
    if (!s) return;

    auto* track = dynamic_cast<lmms::SampleTrack*>(
        lmms::Track::create(lmms::Track::Type::Sample, s));
    if (!track) return;
    track->setName(name);
    track->setColor(color);

    if (sections.isEmpty()) {
        auto* clip = dynamic_cast<lmms::SampleClip*>(
            track->createClip(lmms::TimePos(0)));
        if (clip) {
            clip->setSampleFile(audioPath);
            clip->updateLength();
        }
        return;
    }

    const float framesPerTick = lmms::Engine::framesPerTick(
        lmms::Engine::audioEngine()->outputSampleRate());
    lmms::tick_t positionTicks = 0;

    for (const QVariant& sv : sections) {
        const QVariantMap sec = sv.toMap();
        const double startSec = sec.value("start_sec", 0.0).toDouble();
        const double endSec   = sec.value("end_sec", startSec).toDouble();
        if (endSec <= startSec) continue;

        auto* clip = dynamic_cast<lmms::SampleClip*>(
            track->createClip(lmms::TimePos(positionTicks)));
        if (!clip) continue;
        clip->setSampleFile(audioPath);
        const int sr = clip->sample().sampleRate();
        if (sr <= 0) continue;
        const lmms::f_cnt_t startFrame = static_cast<lmms::f_cnt_t>(startSec * sr);
        const lmms::f_cnt_t endFrame   = static_cast<lmms::f_cnt_t>(endSec * sr);
        clip->setSampleStartFrame(startFrame);
        clip->setSamplePlayLength(endFrame);
        const lmms::f_cnt_t sectionFrames = endFrame - startFrame;
        clip->changeLength(lmms::TimePos::fromFrames(sectionFrames, framesPerTick));
        positionTicks += clip->length();
    }
}

void LmmsEngine::insertStemTracks(const QStringList& audioPaths,
                                   const QStringList& stemNames)
{
    static const QMap<QString, QColor> STEM_COLORS = {
        {"vocals",    QColor("#e74c3c")},
        {"drums",     QColor("#f39c12")},
        {"bass",      QColor("#3498db")},
        {"piano",     QColor("#9b59b6")},
        {"guitar",    QColor("#2ecc71")},
        {"other",     QColor("#95a5a6")},
        {"no_vocals", QColor("#7f8c8d")},
    };

    for (int i = 0; i < audioPaths.size() && i < stemNames.size(); ++i) {
        const QString& stemName = stemNames.at(i);
        const QColor color = STEM_COLORS.value(stemName.toLower(), QColor("#4fc3f7"));
        insertAudioTrack(stemName, audioPaths.at(i), color);
    }
}

// ── Mixer ────────────────────────────────────────────────────────────────────

int LmmsEngine::mixerChannelCount() const
{
    auto* mixer = lmms::Engine::mixer();
    return mixer ? static_cast<int>(mixer->numChannels()) : 0;
}

QString LmmsEngine::mixerChannelName(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return {};
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_name : QString();
}

void LmmsEngine::setMixerChannelName(int channel, const QString& name)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) chan->m_name = name;
}

float LmmsEngine::mixerChannelVolume(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return 1.0f;
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_volumeModel.value() : 1.0f;
}

void LmmsEngine::setMixerChannelVolume(int channel, float volume)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) chan->m_volumeModel.setValue(volume);
}

bool LmmsEngine::mixerChannelMuted(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return false;
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_muteModel.value() : false;
}

void LmmsEngine::setMixerChannelMuted(int channel, bool muted)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) chan->m_muteModel.setValue(muted);
}

bool LmmsEngine::mixerChannelSoloed(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return false;
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_soloModel.value() : false;
}

void LmmsEngine::setMixerChannelSoloed(int channel, bool soloed)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) {
        chan->m_soloModel.setValue(soloed);
        mixer->toggledSolo();
    }
}

float LmmsEngine::mixerChannelPeakLeft(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return 0.0f;
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_peakLeft : 0.0f;
}

float LmmsEngine::mixerChannelPeakRight(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return 0.0f;
    auto* chan = mixer->mixerChannel(channel);
    return chan ? chan->m_peakRight : 0.0f;
}

void LmmsEngine::resetMixerChannelPeaks(int channel)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) {
        chan->m_peakLeft = 0.0f;
        chan->m_peakRight = 0.0f;
    }
}

QColor LmmsEngine::mixerChannelColor(int channel) const
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return {};
    auto* chan = mixer->mixerChannel(channel);
    if (chan && chan->color().has_value())
        return chan->color().value();
    return QColor();
}

void LmmsEngine::setMixerChannelColor(int channel, const QColor& color)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;
    auto* chan = mixer->mixerChannel(channel);
    if (chan) chan->setColor(color);
}

QVariantList LmmsEngine::mixerChannelSends(int channel) const
{
    QVariantList result;
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return result;
    auto* chan = mixer->mixerChannel(channel);
    if (!chan) return result;

    for (auto* route : chan->m_sends) {
        QVariantMap send;
        send["receiver"] = route->receiverIndex();
        send["amount"] = route->amount()->value();
        result.append(send);
    }
    return result;
}

void LmmsEngine::addReverbToChannel(int channel, double wetAmount)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer || channel < 0 || channel >= static_cast<int>(mixer->numChannels())) return;

    lmms::MixerChannel* chan = mixer->mixerChannel(channel);
    if (!chan) return;

    lmms::EffectChain& chain = chan->m_fxChain;
    lmms::Effect* effect = lmms::Effect::instantiate("reverbsc", &chain, nullptr);
    if (!effect) {
        qWarning() << "[LmmsEngine] addReverbToChannel: failed to instantiate reverbsc";
        return;
    }

    const float wetClamped = static_cast<float>(std::clamp(wetAmount, 0.0, 1.0));
    QDomDocument doc;
    QDomElement el = doc.createElement("effect");
    el.setAttribute("on",  "1");
    el.setAttribute("wet", QString::number(wetClamped, 'f', 4));
    QDomElement ctrl = doc.createElement("ReverbSCControls");
    ctrl.setAttribute("input_gain",  "1.0");
    ctrl.setAttribute("size",        "0.85");
    ctrl.setAttribute("color",       "0.5");
    ctrl.setAttribute("output_gain", "1.0");
    el.appendChild(ctrl);
    effect->loadSettings(el);

    chain.appendEffect(effect);
    qDebug() << "[LmmsEngine] addReverbToChannel ch" << channel << "wet" << wetClamped;
}

void LmmsEngine::applyAutoMix(const QVariantList& suggestions)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer) return;
    for (const QVariant& sv : suggestions) {
        const QVariantMap s = sv.toMap();
        const int ch = s.value("channel", -1).toInt();
        if (ch < 0 || ch >= static_cast<int>(mixer->numChannels())) continue;
        auto* chan = mixer->mixerChannel(ch);
        if (!chan) continue;
        if (s.contains("gain_db")) {
            const float gain = std::pow(10.f, s["gain_db"].toFloat() / 20.f);
            chan->m_volumeModel.setValue(gain * 100.f);
        }
    }
}

// ── Arrangement ──────────────────────────────────────────────────────────

int LmmsEngine::songLengthBars() const
{
    auto* s = song();
    return s ? static_cast<int>(s->length()) : 0;
}

bool LmmsEngine::trackMuted(int trackIndex) const
{
    auto* s = song();
    if (!s) return false;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return false;
    return tracks.at(trackIndex)->isMuted();
}

void LmmsEngine::setTrackMuted(int trackIndex, bool muted)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;
    tracks.at(trackIndex)->setMuted(muted);
}

bool LmmsEngine::trackSoloed(int trackIndex) const
{
    auto* s = song();
    if (!s) return false;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return false;
    return tracks.at(trackIndex)->isSolo();
}

void LmmsEngine::setTrackSoloed(int trackIndex, bool soloed)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;
    tracks.at(trackIndex)->setSolo(soloed);
}

QColor LmmsEngine::trackColor(int trackIndex) const
{
    auto* s = song();
    if (!s) return {};
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return {};
    auto c = tracks.at(trackIndex)->color();
    return c.has_value() ? c.value() : QColor();
}

void LmmsEngine::setTrackColor(int trackIndex, const QColor& color)
{
    auto* s = song();
    if (!s) return;
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return;
    tracks.at(trackIndex)->setColor(color);
}

QString LmmsEngine::trackType(int trackIndex) const
{
    auto* s = song();
    if (!s) return {};
    const auto& tracks = s->tracks();
    if (trackIndex < 0 || trackIndex >= static_cast<int>(tracks.size())) return {};
    switch (tracks.at(trackIndex)->type()) {
    case lmms::Track::Type::Sample:     return "sample";
    case lmms::Track::Type::Pattern:    return "pattern";
    case lmms::Track::Type::Automation: return "automation";
    default:                            return "instrument";
    }
}

// ── Session analysis ─────────────────────────────────────────────────────────

QVariantList LmmsEngine::existingMidiNotes() const
{
    auto* s = song();
    if (!s) return {};

    QVariantList pitches;
    for (auto* track : s->tracks()) {
        auto* it = dynamic_cast<lmms::InstrumentTrack*>(track);
        if (!it) continue;
        for (auto* clipBase : it->getClips()) {
            auto* mc = dynamic_cast<lmms::MidiClip*>(clipBase);
            if (!mc) continue;
            for (const lmms::Note* n : mc->notes()) {
                pitches.append(n->key());
            }
        }
    }
    return pitches;
}

QVariantList LmmsEngine::songAudioTracks() const
{
    auto* s = song();
    if (!s) {
        qDebug() << "[songAudioTracks] no song";
        return {};
    }

    QVariantList result;
    int totalTracks = 0, sampleTracks = 0;
    for (auto* track : s->tracks()) {
        ++totalTracks;
        auto* st = dynamic_cast<lmms::SampleTrack*>(track);
        if (!st) continue;
        ++sampleTracks;
        // Find the first clip with a non-empty file path
        QString firstPath;
        int numClips = static_cast<int>(st->getClips().size());
        for (auto* clipBase : st->getClips()) {
            auto* sc = dynamic_cast<lmms::SampleClip*>(clipBase);
            QString sf = sc ? sc->sampleFile() : QString();
            qDebug() << "[songAudioTracks] track=" << st->name()
                     << "clips=" << numClips << "sampleFile=" << sf;
            if (sc && !sf.isEmpty()) {
                firstPath = sf;
                break;
            }
        }
        if (firstPath.isEmpty()) {
            qDebug() << "[songAudioTracks] skipping" << st->name() << "(no path)";
            continue;
        }
        QVariantMap entry;
        entry["name"] = st->name();
        entry["path"] = firstPath;
        result.append(entry);
    }
    qDebug() << "[songAudioTracks] total=" << totalTracks
             << "sampleTracks=" << sampleTracks
             << "returned=" << result.size();
    return result;
}

// ── MIDI ─────────────────────────────────────────────────────────────────────

void LmmsEngine::importMidiToActiveClip(const QString& midiPath)
{
    if (m_pianoRoll) {
        QMetaObject::invokeMethod(m_pianoRoll,
            [pr = m_pianoRoll, path = midiPath]() {
                pr->importNotesFromMidi(path);
            }, Qt::QueuedConnection);
    }
}

void LmmsEngine::importMidiFile(const QString& midiPath)
{
    auto* s = song();
    if (!s || midiPath.isEmpty()) return;
    if (!QFile::exists(midiPath)) {
        qWarning() << "[LmmsEngine] importMidiFile: file not found:" << midiPath;
        return;
    }
    qDebug() << "[LmmsEngine] importMidiFile:" << midiPath;
    lmms::ImportFilter::import(midiPath, s);
}

void LmmsEngine::createMidiTrack(const QString& name,
                                  const QString& midiPath,
                                  const QColor&  color,
                                  int            bars,
                                  const QString& instrument,
                                  const QString& presetName,
                                  int            startBar,
                                  double         reverbWet,
                                  int            gmPatch)
{
    auto* s = song();
    if (!s || midiPath.isEmpty()) return;

    // Create InstrumentTrack and load the requested instrument plugin
    auto* it = dynamic_cast<lmms::InstrumentTrack*>(
        lmms::Track::create(lmms::Track::Type::Instrument, s));
    if (!it) return;
    it->setColor(color);
    const bool isDrumKit = (instrument == QStringLiteral("sf2player-drums"));
    const bool isSf2 = (instrument == QStringLiteral("sf2player"));
    const bool isAfp = (instrument == QStringLiteral("audiofileprocessor"));
    const QString plugin = instrument.isEmpty() ? QStringLiteral("tripleoscillator")
                           : (isDrumKit || isSf2) ? QStringLiteral("sf2player") : instrument;
    it->loadInstrument(plugin);
    // Set name AFTER loadInstrument — loadInstrument overwrites name with plugin displayName
    it->setName(name);
    if (isAfp && !presetName.isEmpty()) {
        // AudioFileProcessor: preset field = sample file path (relative to factory samples)
        if (lmms::Instrument* instr = it->instrument()) {
            QMetaObject::invokeMethod(instr, "setAudioFile",
                Q_ARG(QString, presetName),
                Q_ARG(bool, false));
        }
    } else if (isDrumKit) {
        // Bank 128 = GM percussion bank; each note maps to a distinct drum sound in GeneralUser GS
        if (lmms::Instrument* instr = it->instrument()) {
            if (auto* m = instr->childModel("bank"))  m->setValue(128.0f);
            if (auto* m = instr->childModel("patch")) m->setValue(0.0f);
        }
    } else if (isSf2 && gmPatch >= 0) {
        // Set GM program patch on sf2player for faithful instrument mapping
        if (lmms::Instrument* instr = it->instrument()) {
            if (auto* m = instr->childModel("bank"))  m->setValue(0.0f);
            if (auto* m = instr->childModel("patch")) m->setValue(static_cast<float>(gmPatch));
        }
    } else if (!presetName.isEmpty()) {
        loadXpfPreset(it, presetName);
    }

    // Create a MidiClip at the requested start bar position
    auto* clip = dynamic_cast<lmms::MidiClip*>(
        it->createClip(lmms::TimePos(startBar * lmms::DefaultTicksPerBar)));
    if (!clip) {
        qWarning() << "[LmmsEngine] createMidiTrack: failed to create MidiClip for" << name;
        return;
    }
    // Parse the MIDI file
    QFile f(midiPath);
    if (!f.open(QIODevice::ReadOnly)) {
        qWarning() << "[LmmsEngine] createMidiTrack: cannot open" << midiPath;
        return;
    }
    const QByteArray data = f.readAll();
    f.close();

    uint16_t ppq = 0;
    auto finishedNotes = parseMidiNotes(data, &ppq);
    if (finishedNotes.empty()) {
        qWarning() << "[LmmsEngine] createMidiTrack: no notes parsed from" << midiPath;
        return;
    }

    // Convert MIDI ticks → LMMS ticks
    const double scale = double(LMMS_TICKS_PER_BEAT) / ppq;
    int maxEndLmms = 0;
    for (auto& mn : finishedNotes) {
        int startT = int(mn.startTick * scale + 0.5);
        int lenT   = int((mn.endTick - mn.startTick) * scale + 0.5);
        if (lenT < 1) lenT = 1;
        // Round velocity: +63 avoids truncating vel=1-2 to silent (integer division fix)
        const int lmmsVel = (mn.vel * 100 + 63) / 127;
        lmms::Note note(lmms::TimePos(lenT), lmms::TimePos(startT),
                        mn.key, lmmsVel);
        clip->addNote(note, false);
        maxEndLmms = std::max(maxEndLmms, startT + lenT);
    }

    // Set clip length from actual note content — round up to the next full bar
    const int tpbar = lmms::DefaultTicksPerBar;
    const int contentBars = (maxEndLmms + tpbar - 1) / tpbar;
    clip->changeLength(lmms::TimePos(std::max(1, contentBars) * tpbar));
    clip->rearrangeAllNotes();
    clip->updateLength();

    qDebug() << "[LmmsEngine] createMidiTrack" << name
             << "plugin:" << plugin
             << "notes:" << finishedNotes.size()
             << "reverbWet:" << reverbWet;

    // Per-track reverb: assign to a new mixer channel and add ReverbSC
    if (reverbWet > 0.001 && it) {
        auto* mixer = lmms::Engine::mixer();
        if (mixer) {
            // Find next unused mixer channel (skip 0 = master), or create one
            const int numCh = static_cast<int>(mixer->numChannels());
            int targetCh = -1;
            for (int ch = 1; ch < numCh; ++ch) {
                auto* mch = mixer->mixerChannel(ch);
                if (mch && mch->m_name.isEmpty()) {
                    targetCh = ch;
                    break;
                }
            }
            if (targetCh < 0) {
                // All existing channels are used — create a new one
                targetCh = mixer->createChannel();
            }
            if (targetCh > 0) {
                // Route the instrument track to this mixer channel
                it->mixerChannelModel()->setValue(targetCh);
                // Name the mixer channel after the track
                mixer->mixerChannel(targetCh)->m_name = name;
                // Add reverb to the mixer channel
                addReverbToChannel(targetCh, reverbWet);
                qDebug() << "[LmmsEngine] createMidiTrack: routed" << name
                         << "to mixer ch" << targetCh << "with reverb" << reverbWet;
            }
        }
    }
}

void LmmsEngine::loadXpfPreset(lmms::InstrumentTrack* it, const QString& presetName)
{
    if (!it || presetName.isEmpty()) return;

    // Resolve full path: <lmms data dir>/presets/<presetName>
    const QString dataDir = lmms::ConfigManager::inst()->dataDir();
    const QString path = dataDir + QStringLiteral("presets/") + presetName;

    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        qWarning() << "[LmmsEngine] loadXpfPreset: cannot open" << path;
        return;
    }
    QDomDocument doc;
    if (!doc.setContent(&f)) {
        qWarning() << "[LmmsEngine] loadXpfPreset: parse error" << path;
        return;
    }
    f.close();

    // Navigate XML hierarchy to reach <instrument name="plugin"> element.
    // XPF format: <lmms-project> → <instrumenttracksettings> → <instrumenttrack> → <instrument>
    QDomElement root = doc.documentElement();
    QDomElement itElem;
    if (root.tagName() == QLatin1String("lmms-project") ||
        root.tagName() == QLatin1String("multimedia-project") ||
        root.tagName() == QLatin1String("multimediaproject"))
    {
        QDomElement its = root.firstChildElement("instrumenttracksettings");
        if (its.isNull()) its = root.firstChildElement("track");
        itElem = its.firstChildElement("instrumenttrack");
    } else if (root.tagName() == QLatin1String("instrumenttrack")) {
        itElem = root;
    }

    QDomElement instrElem;
    if (!itElem.isNull())
        instrElem = itElem.firstChildElement("instrument");

    lmms::Instrument* instr = it->instrument();
    if (instr && !instrElem.isNull()) {
        // LMMS InstrumentTrack passes firstChildElement of <instrument> to restoreState,
        // i.e. the plugin-specific element like <tripleoscillator .../> or <lb302 .../>
        QDomElement pluginElem = instrElem.firstChildElement();
        if (!pluginElem.isNull()) {
            instr->restoreState(pluginElem);
            qDebug() << "[LmmsEngine] loadXpfPreset loaded" << presetName;
        } else {
            qWarning() << "[LmmsEngine] loadXpfPreset: empty <instrument> in" << path;
        }
    } else if (instr && !itElem.isNull()) {
        // Fallback: older XPF format where plugin element (e.g. <audiofileprocessor>,
        // <OPL2>, <lb302>) sits directly inside <instrumenttrack> without <instrument>
        // wrapper.  Scan children and pick the first non-standard element.
        static const QStringList kStdChildren = {
            "eldata", "chordcreator", "arpeggiator", "midiport", "fxchain"
        };
        QDomElement bareElem;
        for (auto n = itElem.firstChildElement(); !n.isNull(); n = n.nextSiblingElement()) {
            if (!kStdChildren.contains(n.tagName())) {
                bareElem = n;
                break;
            }
        }
        if (!bareElem.isNull()) {
            instr->restoreState(bareElem);
            qDebug() << "[LmmsEngine] loadXpfPreset loaded (bare <"
                     << bareElem.tagName() << ">)" << presetName;
        } else {
            qWarning() << "[LmmsEngine] loadXpfPreset: no plugin element in" << path;
        }
    } else {
        qWarning() << "[LmmsEngine] loadXpfPreset: no <instrument> element in" << path;
    }
}

void LmmsEngine::replaceNotesInBar(const QString& trackName, int barIndex,
                                     const QString& midiPath)
{
    auto* s = song();
    if (!s || midiPath.isEmpty()) return;

    // Find InstrumentTrack by name
    lmms::InstrumentTrack* it = nullptr;
    for (auto* t : s->tracks()) {
        if (t->name() == trackName) {
            it = dynamic_cast<lmms::InstrumentTrack*>(t);
            if (it) break;
        }
    }
    if (!it) {
        qWarning() << "[LmmsEngine] replaceNotesInBar: track not found:" << trackName;
        return;
    }

    auto* clip = dynamic_cast<lmms::MidiClip*>(it->getClip(0));
    if (!clip) return;

    const int barStart = barIndex * lmms::DefaultTicksPerBar;
    const int barEnd   = barStart + lmms::DefaultTicksPerBar;

    // Remove existing notes in bar range (collect first to avoid iterator invalidation)
    it->lock();
    std::vector<lmms::Note*> toRemove;
    for (lmms::Note* note : clip->notes()) {
        if (note && note->pos() >= barStart && note->pos() < barEnd)
            toRemove.push_back(note);
    }
    for (lmms::Note* note : toRemove)
        clip->removeNote(note);
    it->unlock();

    // Parse MIDI and insert notes into existing clip
    QFile f(midiPath);
    if (!f.open(QIODevice::ReadOnly)) return;
    const QByteArray data = f.readAll();
    f.close();

    uint16_t ppq = 0;
    auto finished = parseMidiNotes(data, &ppq);
    if (ppq == 0) return;
    const double scale = double(lmms::DefaultTicksPerBar) / ppq;

    for (auto& mn : finished) {
        int startT = int(mn.startTick * scale + 0.5) + barStart;
        int lenT   = std::max(1, int((mn.endTick - mn.startTick) * scale + 0.5));
        lmms::Note note(lmms::TimePos(lenT), lmms::TimePos(startT),
                        mn.key, mn.vel * 100 / 127);
        clip->addNote(note, false);
    }
    clip->rearrangeAllNotes();
    clip->updateLength();
    qDebug() << "[LmmsEngine] replaceNotesInBar" << trackName << "bar" << barIndex;
}

void LmmsEngine::insertChordToActiveClip(const QList<int>& pitches, int barIndex,
                                           double durationBeats)
{
    if (!m_pianoRoll || pitches.isEmpty()) return;
    QMetaObject::invokeMethod(m_pianoRoll, [pr = m_pianoRoll, pitches, barIndex, durationBeats]() {
        auto* clip = const_cast<lmms::MidiClip*>(pr->currentMidiClip());
        if (!clip) return;
        const int startTick = barIndex * lmms::DefaultTicksPerBar;
        const int lenTick   = std::max(1, int(durationBeats * lmms::DefaultTicksPerBar));
        for (int pitch : pitches) {
            lmms::Note note(lmms::TimePos(lenTick), lmms::TimePos(startTick),
                            std::clamp(pitch, 0, lmms::NumKeys - 1), 75);
            clip->addNote(note, false);
        }
        clip->rearrangeAllNotes();
        clip->updateLength();
    }, Qt::QueuedConnection);
    qDebug() << "[LmmsEngine] insertChordToActiveClip bar" << barIndex
             << "pitches" << pitches.size();
}

void LmmsEngine::insertBeatPattern(const QVariantList& rows, int bpm, int bars)
{
    auto* s = song();
    if (!s || rows.isEmpty()) return;

    const int STEPS_PER_BAR = 16;
    const int ticksPerStep  = lmms::DefaultTicksPerBar / STEPS_PER_BAR; // 12 ticks

    if (bpm > 0) setTempo(bpm);

    for (const QVariant& rv : rows) {
        const QVariantMap row = rv.toMap();
        const QString name  = row.value("name", "Drum").toString();
        const QString color = row.value("color", "#e74c3c").toString();
        const QVariantList steps = row.value("steps").toList();
        if (steps.isEmpty()) continue;

        auto* it = dynamic_cast<lmms::InstrumentTrack*>(
            lmms::Track::create(lmms::Track::Type::Instrument, s));
        if (!it) continue;
        it->setName(name);
        it->setColor(QColor(color));
        it->loadInstrument("tripleoscillator");

        auto* clip = dynamic_cast<lmms::MidiClip*>(it->createClip(lmms::TimePos(0)));
        if (!clip) continue;
        clip->changeLength(lmms::TimePos(bars * lmms::DefaultTicksPerBar));

        for (int b = 0; b < bars; ++b) {
            for (int step = 0; step < STEPS_PER_BAR && step < steps.size(); ++step) {
                if (!steps[step].toBool()) continue;
                const int startTick = b * lmms::DefaultTicksPerBar + step * ticksPerStep;
                lmms::Note note(lmms::TimePos(ticksPerStep),
                                lmms::TimePos(startTick), 60, 80);
                clip->addNote(note, false);
            }
        }
        clip->rearrangeAllNotes();
        clip->updateLength();
    }
    qDebug() << "[LmmsEngine] insertBeatPattern" << rows.size() << "rows," << bpm << "BPM";
}

// ── Genre Mode ───────────────────────────────────────────────────────────────

void LmmsEngine::applyGenreMode(const QString& modeKey)
{
    const GenreModeCfg* cfg = findGenreMode(modeKey);
    if (!cfg) return;
    // 1. DAW tempo + time signature
    setTempo(cfg->bpm);
    setTimeSignature(cfg->timeSigNum, cfg->timeSigDen);
    // 2. Master FX chain
    clearMasterFx();
    for (int i = 0; i < 6 && cfg->masterFx[i]; ++i)
        addFxToMaster(QString(cfg->masterFx[i]));
    // 3. Create genre instrument tracks (duplicate-prevention inside)
    createGenreInstrumentTracks(modeKey);
    qDebug() << "[LmmsEngine] applyGenreMode" << modeKey << "bpm=" << cfg->bpm;
}

void LmmsEngine::clearMasterFx()
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer) return;
    lmms::MixerChannel* chan = mixer->mixerChannel(0);
    if (!chan) return;
    chan->m_fxChain.clear();
    qDebug() << "[LmmsEngine] clearMasterFx: master FX chain cleared";
}

void LmmsEngine::addFxToMaster(const QString& fxName)
{
    auto* mixer = lmms::Engine::mixer();
    if (!mixer) return;
    lmms::MixerChannel* chan = mixer->mixerChannel(0);
    if (!chan) return;
    lmms::EffectChain& chain = chan->m_fxChain;

    // All reverb variants use the reverbsc plugin (only reliably available).
    // LADSPA-based effects (hard_clip, tape_sat, chorus, ncs_limiter, gain_6db)
    // are silently skipped — LADSPA may not be built.
    struct ReverbParams { float room; float damp; float wet; };
    ReverbParams params{0.0f, 0.5f, 0.0f};
    bool isReverb = true;

    if (fxName == QStringLiteral("short_reverb"))
        params = {0.45f, 0.5f, 0.25f};
    else if (fxName == QStringLiteral("hall_reverb"))
        params = {0.70f, 0.5f, 0.35f};
    else if (fxName == QStringLiteral("huge_reverb"))
        params = {0.95f, 0.5f, 0.45f};
    else if (fxName == QStringLiteral("dark_reverb"))
        params = {0.50f, 0.8f, 0.30f};
    else
        isReverb = false;

    if (!isReverb) {
        qDebug() << "[LmmsEngine] addFxToMaster: skipping" << fxName
                 << "(LADSPA effects not supported)";
        return;
    }

    lmms::Effect* effect = lmms::Effect::instantiate("reverbsc", &chain, nullptr);
    if (!effect) {
        qWarning() << "[LmmsEngine] addFxToMaster: failed to instantiate reverbsc for" << fxName;
        return;
    }
    QDomDocument doc;
    QDomElement el = doc.createElement("effect");
    el.setAttribute("on",  "1");
    el.setAttribute("wet", QString::number(params.wet, 'f', 4));
    QDomElement ctrl = doc.createElement("ReverbSCControls");
    ctrl.setAttribute("input_gain",  "1.0");
    ctrl.setAttribute("size",        QString::number(params.room, 'f', 4));
    ctrl.setAttribute("color",       QString::number(params.damp, 'f', 4));
    ctrl.setAttribute("output_gain", "1.0");
    el.appendChild(ctrl);
    effect->loadSettings(el);
    chain.appendEffect(effect);
    qDebug() << "[LmmsEngine] addFxToMaster:" << fxName
             << "room=" << params.room << "wet=" << params.wet;
}

void LmmsEngine::createGenreInstrumentTracks(const QString& modeKey)
{
    auto* s = song();
    if (!s) return;
    // Always add genre instrument tracks when user explicitly selects a genre.
    // Skip only if this genre's tracks are already present (avoid duplicates on
    // repeated selection of the same mode).
    const GenreModeCfg* cfgCheck = findGenreMode(modeKey);
    if (cfgCheck && cfgCheck->instruments[0].name[0]) {
        const QString firstName = QString(cfgCheck->instruments[0].name);
        for (auto* t : s->tracks()) {
            if (t->name() == firstName) {
                qDebug() << "[LmmsEngine] createGenreInstrumentTracks: skipped (genre tracks already present)";
                return;
            }
        }
    }
    const GenreModeCfg* cfg = findGenreMode(modeKey);
    if (!cfg) return;
    for (int i = 0; i < 10 && cfg->instruments[i].name[0]; ++i) {
        const InstrumentDef& def = cfg->instruments[i];
        auto* it = dynamic_cast<lmms::InstrumentTrack*>(
            lmms::Track::create(lmms::Track::Type::Instrument, s));
        if (!it) continue;
        it->setColor(QColor(QRgb(def.color)));
        it->loadInstrument(QString(def.plugin));
        // Set name AFTER loadInstrument — loadInstrument overwrites name with plugin displayName
        it->setName(QString(def.name));
        if (def.preset[0]) {
            if (QString(def.plugin) == QStringLiteral("audiofileprocessor")) {
                // preset field = sample file path for AudioFileProcessor
                lmms::Instrument* instr = it->instrument();
                if (instr) {
                    QMetaObject::invokeMethod(instr, "setAudioFile",
                        Q_ARG(QString, QString(def.preset)),
                        Q_ARG(bool, false));
                }
            } else {
                loadXpfPreset(it, QString(def.preset));
            }
        }
        qDebug() << "[LmmsEngine] createGenreInstrumentTracks: added" << def.name;
    }
}

void LmmsEngine::createCustomInstrumentTracks(const QVariantList& instrSlots)
{
    auto* s = song();
    if (!s || instrSlots.isEmpty()) return;

    // Duplicate-prevention: skip if first instrument name already exists
    const QString firstName = instrSlots.at(0).toMap().value(QStringLiteral("name")).toString();
    if (!firstName.isEmpty()) {
        for (auto* t : s->tracks()) {
            if (t->name() == firstName) {
                qDebug() << "[LmmsEngine] createCustomInstrumentTracks: skipped (tracks already present)";
                return;
            }
        }
    }

    for (const QVariant& v : instrSlots) {
        const QVariantMap slot = v.toMap();
        const QString name   = slot.value(QStringLiteral("name")).toString();
        const QString plugin = slot.value(QStringLiteral("plugin")).toString();
        const QString preset = slot.value(QStringLiteral("preset")).toString();
        const QString color  = slot.value(QStringLiteral("color")).toString();

        if (name.isEmpty() || plugin.isEmpty()) continue;

        auto* it = dynamic_cast<lmms::InstrumentTrack*>(
            lmms::Track::create(lmms::Track::Type::Instrument, s));
        if (!it) continue;

        if (!color.isEmpty())
            it->setColor(QColor(color));

        it->loadInstrument(plugin);
        // Set name AFTER loadInstrument — loadInstrument overwrites name with displayName
        it->setName(name);

        if (!preset.isEmpty()) {
            if (plugin == QStringLiteral("audiofileprocessor")) {
                lmms::Instrument* instr = it->instrument();
                if (instr) {
                    QMetaObject::invokeMethod(instr, "setAudioFile",
                        Q_ARG(QString, preset), Q_ARG(bool, false));
                }
            } else {
                loadXpfPreset(it, preset);
            }
        }
        qDebug() << "[LmmsEngine] createCustomInstrumentTracks: added" << name;
    }
}

// ── Plugin / Preset Discovery ─────────────────────────────────────────────

QVariantList LmmsEngine::availableInstrumentPlugins() const
{
    QVariantList result;
    auto* pf = lmms::getPluginFactory();
    if (!pf) return result;
    for (const auto* desc : pf->descriptors(lmms::Plugin::Type::Instrument)) {
        if (!desc) continue;
        QVariantMap entry;
        entry[QStringLiteral("name")]        = QString(desc->name);
        entry[QStringLiteral("displayName")] = QString(desc->displayName);
        result.append(entry);
    }
    qDebug() << "[LmmsEngine] availableInstrumentPlugins:" << result.size();
    return result;
}

bool LmmsEngine::addEmptyInstrumentTrack(const QString& pluginName, const QString& trackName,
                                           const QString& preset, const QString& samplePath)
{
    auto* s = song();
    if (!s) return false;

    auto* it = dynamic_cast<lmms::InstrumentTrack*>(
        lmms::Track::create(lmms::Track::Type::Instrument, s));
    if (!it) return false;

    it->loadInstrument(pluginName);

    // Load preset or set sample
    if (!preset.isEmpty()) {
        if (pluginName == QStringLiteral("audiofileprocessor")) {
            // preset field is the sample path for AudioFileProcessor
            lmms::Instrument* instr = it->instrument();
            if (instr) {
                QMetaObject::invokeMethod(instr, "setAudioFile",
                    Q_ARG(QString, preset), Q_ARG(bool, false));
            }
        } else {
            loadXpfPreset(it, preset);
        }
    } else if (!samplePath.isEmpty()) {
        // Explicit sample path (e.g. from catalog builtin_sample entries)
        lmms::Instrument* instr = it->instrument();
        if (instr) {
            QMetaObject::invokeMethod(instr, "setAudioFile",
                Q_ARG(QString, samplePath), Q_ARG(bool, false));
        }
    }

    // Set name AFTER loadInstrument — loadInstrument overwrites name with displayName
    if (!trackName.isEmpty())
        it->setName(trackName);

    qDebug() << "[LmmsEngine] addEmptyInstrumentTrack:" << pluginName << trackName
             << "preset=" << preset << "sample=" << samplePath;
    return true;
}

QStringList LmmsEngine::presetsForPlugin(const QString& pluginName) const
{
    QStringList result;
    if (pluginName.isEmpty()) return result;

    const QString presetsRoot = lmms::ConfigManager::inst()->factoryPresetsDir();

    // Scan for subdirectory matching plugin display name (case-insensitive)
    QDir rootDir(presetsRoot);
    if (!rootDir.exists()) return result;

    QString matchedDir;
    for (const QString& sub : rootDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        if (sub.compare(pluginName, Qt::CaseInsensitive) == 0) {
            matchedDir = sub;
            break;
        }
    }
    if (matchedDir.isEmpty()) return result;

    QDir pluginDir(presetsRoot + matchedDir);
    const QStringList xpfFiles = pluginDir.entryList(
        QStringList() << QStringLiteral("*.xpf"), QDir::Files, QDir::Name);
    for (const QString& f : xpfFiles)
        result.append(matchedDir + QStringLiteral("/") + f);

    qDebug() << "[LmmsEngine] presetsForPlugin" << pluginName << ":" << result.size();
    return result;
}

// ── Project ──────────────────────────────────────────────────────────────────

void LmmsEngine::createNewProject()
{
    auto* s = song();
    if (s) s->createNewProject();
}

void LmmsEngine::openProject()
{
    if (m_mainWindow)
        QMetaObject::invokeMethod(m_mainWindow, "openProject", Qt::QueuedConnection);
}

void LmmsEngine::saveProject()
{
    if (m_mainWindow)
        QMetaObject::invokeMethod(m_mainWindow, "saveProject", Qt::QueuedConnection);
}

#endif // WAVY_LMMS_CORE
