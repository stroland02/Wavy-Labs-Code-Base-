#include "EngineAPI.h"

#include <QDebug>
#include <algorithm>

// ---------------------------------------------------------------------------
// dispatchActions — shared action-map parser that calls virtual methods.
// Dispatches a list of action maps to the appropriate virtual methods.
// ---------------------------------------------------------------------------

void EngineAPI::dispatchActions(const QVariantList& actions)
{
    for (const QVariant& a : actions) {
        const QVariantMap action = a.toMap();
        const QString type = action.value("type").toString();

        if (type == "add_track") {
            addTrack(action.value("track_type", "sample").toString(),
                     action.value("name", "New Track").toString());

        } else if (type == "delete_track") {
            const int idx = action.value("track_index", -1).toInt();
            if (idx >= 0) deleteTrack(idx);

        } else if (type == "duplicate_track") {
            const int idx = action.value("track_index", -1).toInt();
            if (idx >= 0) duplicateTrack(idx);

        } else if (type == "set_tempo") {
            setTempo(std::clamp(action.value("bpm", 120).toInt(), 10, 999));

        } else if (type == "set_volume") {
            setTrackVolume(action.value("track_index", 0).toInt(),
                           action.value("volume", 1.0).toDouble());

        } else if (type == "set_pan") {
            setTrackPan(action.value("track_index", 0).toInt(),
                        action.value("pan", 0.0).toDouble());

        } else if (type == "transpose_clip") {
            transposeClip(action.value("track_index", 0).toInt(),
                          action.value("clip_index",  0).toInt(),
                          action.value("semitones",   0).toInt());

        } else if (type == "add_pattern") {
            addClip(action.value("track_index", 0).toInt(),
                    action.value("bar",         0).toInt(),
                    action.value("length_bars", 4).toInt());

        } else if (type == "set_reverb") {
            addReverbToChannel(action.value("channel", 0).toInt(),
                               action.value("amount",  0.4).toDouble());

        } else if (type == "set_key") {
            static const QMap<QString, int> KEY_SEMITONES = {
                {"C", 0}, {"C#", 1}, {"Db", 1}, {"D", 2}, {"D#", 3}, {"Eb", 3},
                {"E", 4}, {"F", 5}, {"F#", 6}, {"Gb", 6}, {"G", 7}, {"G#", 8},
                {"Ab", 8}, {"A", 9}, {"A#", 10}, {"Bb", 10}, {"B", 11}
            };
            const QString key = action.value("key", "C").toString();
            setMasterPitch(KEY_SEMITONES.value(key.left(2), 0));

        } else if (type == "set_time_signature") {
            setTimeSignature(
                std::clamp(action.value("numerator",   4).toInt(), 1, 32),
                std::clamp(action.value("denominator", 4).toInt(), 1, 32));

        } else if (type == "add_audio_track") {
            insertAudioTrack(
                action.value("track_name", "AI Track").toString(),
                action.value("audio_path").toString(),
                QColor(action.value("color", "#4fc3f7").toString()));

        } else if (type == "create_midi_track") {
            createMidiTrack(
                action.value("name",       "AI Track").toString(),
                action.value("midi_path",  "").toString(),
                QColor(action.value("color", "#9b59b6").toString()),
                action.value("bars",       4).toInt(),
                action.value("instrument", "tripleoscillator").toString(),
                action.value("preset_name", "").toString(),
                action.value("start_bar",  0).toInt(),
                action.value("reverb_wet", 0.0).toDouble(),
                action.value("gm_patch",  -1).toInt());

        } else if (type == "import_midi_file") {
            importMidiFile(action.value("midi_path", "").toString());

        } else if (type == "replace_notes_in_bar") {
            replaceNotesInBar(action.value("track_name", "").toString(),
                              action.value("bar_index",  0).toInt(),
                              action.value("midi_path",  "").toString());

        } else if (type == "insert_chord") {
            QList<int> pitches;
            for (const QVariant& p : action.value("pitches").toList())
                pitches << p.toInt();
            insertChordToActiveClip(pitches,
                                    action.value("bar_index",      0).toInt(),
                                    action.value("duration_beats", 2.0).toDouble());

        } else if (type == "insert_beat_pattern") {
            insertBeatPattern(action.value("rows").toList(),
                              action.value("bpm",  120).toInt(),
                              action.value("bars",   1).toInt());

        } else {
            qWarning() << "[EngineAPI] Unknown action type:" << type;
        }
    }
}
