#pragma once

#include <QString>
#include <cstring>

// ---------------------------------------------------------------------------
// GenreModes.h — header-only static genre config table.
// Used by TransportBar (populate combo), LmmsEngine (apply DAW params),
// AIBackend (push session context to Python backend).
//
// Plugins available in LMMS_MINIMAL build:
//   tripleoscillator  — 3-osc subtractive; leads, pads, 808-ish bass
//   lb302             — acid/resonant mono bass synth
//   monstro           — complex 3-osc w/ mod matrix; aggressive/dubstep
//   organic           — 8-osc additive; warm pads, soul, ambient
//   opulenz           — OPL2 FM synthesis; jazz piano, organ, bells
//   bitinvader        — wavetable; harsh/digital leads, DnB reese
//   kicker            — drum/kick oscillator
//
// Preset paths are relative to <lmms-data>/presets/ and use the XPF format.
// Empty string "" = load plugin with default parameters.
// ---------------------------------------------------------------------------

struct InstrumentDef {
    const char* name;    // track display name, e.g. "Supersaw Lead"
    const char* plugin;  // plugin internal name
    const char* preset;  // relative XPF path OR "" for defaults
    unsigned int color;  // 0xRRGGBB track color
};

struct GenreModeCfg {
    const char* key;           // internal key e.g. "future_bass"
    const char* displayName;   // shown in ComboBox
    int  bpm;
    int  timeSigNum;
    int  timeSigDen;
    const char* defaultKey;    // music key e.g. "A"
    const char* defaultScale;  // "major" | "minor"
    const char* masterFx[6];   // nullptr-terminated list of FX names
    InstrumentDef instruments[10]; // empty name = sentinel; slots 0-5 synths, 6-9 drums
    const char* chordStyle;    // e.g. "future_bass_chords"
    const char* drumStyle;     // e.g. "future_bass"
};

// instruments[0] = lead/melody role
// instruments[1] = bass role (mapped from MIDI bass channels on import)
// instruments[2-5] = additional textures
// instruments[6-9] = drum kit (audiofileprocessor WAV/OGG samples)

static const GenreModeCfg kGenreModes[] = {

    // ── Default — Kicker synth drums ──────────────────────────────────────
    { "default", "Default", 140, 4, 4, "C", "major",
      {nullptr,nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"Kick",  "kicker","Kicker/TrapKick.xpf",     0xE74C3C},
       {"Clap",  "kicker","Kicker/Clap.xpf",          0xF39C12},
       {"Hat",   "kicker","Kicker/HihatClosed.xpf",   0x3498DB},
       {"Snare", "kicker","Kicker/SnareLong.xpf",     0x2ECC71},
       {"","","",0},{"","","",0},
       {"","","",0},{"","","",0},{"","","",0},{"","","",0}},
      "default", "default" },

    // ── Electronic / EDM ────────────────────────────────────────────────────

    { "future_bass", "Future Bass", 128, 4, 4, "A", "minor",
      {"chorus","hall_reverb",nullptr,nullptr,nullptr,nullptr},
      {{"Future Stab",      "monstro",         "Monstro/Phat.xpf",                          0xA569BD},
       {"Pumping Bass",     "lb302",            "LB302/GoodOldTimes.xpf",                    0x1F618D},
       {"Chord Pad",        "tripleoscillator", "TripleOscillator/FutureBass.xpf",           0x7D3C98},
       {"Supersaw Arp",     "tripleoscillator", "TripleOscillator/LSP-SynthwaveSawArp.xpf",  0x8E44AD},
       {"Electro Lead",     "tripleoscillator", "TripleOscillator/LSP-CuteElectroLead.xpf",  0xE74C3C},
       {"Synthwave Pad",    "tripleoscillator", "TripleOscillator/LSP-SynthwavePad.xpf",     0xBB8FCE},
       // Drums — punchy electronic kit
       {"FB Kick",          "audiofileprocessor","drums/kick_soft01.ogg",      0xE74C3C},
       {"FB Clap",          "audiofileprocessor","drums/clap02.ogg",           0xF39C12},
       {"FB Hat",           "audiofileprocessor","drums/hihat_closed02.ogg",   0x3498DB},
       {"FB Open Hat",      "audiofileprocessor","drums/hihat_opened02.ogg",   0x2980B9}},
      "future_bass_chords","future_bass" },

    { "house", "House", 128, 4, 4, "A", "minor",
      {"chorus","hall_reverb",nullptr,nullptr,nullptr,nullptr},
      {{"House Stab",       "tripleoscillator","TripleOscillator/Wavy-HouseStab.xpf",    0x1ABC9C},
       {"House Bass",       "lb302",           "LB302/Wavy-HouseBass.xpf",               0x27AE60},
       {"Organ Pad",        "opulenz",         "OpulenZ/Combo_organ.xpf",                0x117A65},
       {"House Piano",      "tripleoscillator","TripleOscillator/LSP-HousePiano.xpf",    0x16A085},
       {"Detroit Chord",    "tripleoscillator","TripleOscillator/LSP-DetroitChord.xpf",  0x2ECC71},
       {"House Pad",        "tripleoscillator","TripleOscillator/LSP-PadHouse.xpf",      0x0E6655},
       // Drums — four-on-the-floor house kit
       {"House Kick",       "audiofileprocessor","drums/kick01.ogg",           0xE74C3C},
       {"House Clap",       "audiofileprocessor","drums/clap01.ogg",           0xF39C12},
       {"House Hat",        "audiofileprocessor","drums/hihat_closed01.ogg",   0x3498DB},
       {"House Open Hat",   "audiofileprocessor","drums/hihat_opened01.ogg",   0x2980B9}},
      "house_chords","house" },

    // ── Trap ────────────────────────────────────────────────────────────────

    { "trap", "Trap", 140, 4, 4, "F", "minor",
      {"hard_clip",nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"Melody Lead",      "tripleoscillator","TripleOscillator/Wavy-TrapLead.xpf",      0x2980B9},
       {"808 Sub",          "lb302",           "LB302/Wavy-SubBass.xpf",                  0xE74C3C},
       {"Trap Piano",       "tripleoscillator","TripleOscillator/LSP-TrapEPiano.xpf",     0x3498DB},
       {"Cyberpunk Bass",   "monstro",         "Monstro/LSP-CyberpunkBass.xpf",           0x9B59B6},
       {"Reese Bass",       "tripleoscillator","TripleOscillator/LSP-ReeseBass.xpf",      0x7D3C98},
       {"","","",0},
       // Drums — 808 trap kit
       {"Trap Kick",        "audiofileprocessor","808/808_kick.wav",           0xE74C3C},
       {"Trap Clap",        "audiofileprocessor","808/808_clap.wav",           0xF39C12},
       {"Trap Hat",         "audiofileprocessor","808/808_hihat_closed.wav",   0x3498DB},
       {"Trap Open Hat",    "audiofileprocessor","808/808_hihat_open.wav",     0x2980B9}},
      "trap_chords","trap" },

    // ── Ambient ─────────────────────────────────────────────────────────────

    { "ambient", "Ambient", 70, 4, 4, "C", "major",
      {"huge_reverb",nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"Ambient Pad",      "organic",         "Organic/pad_ethereal.xpf",                  0x5DADE2},
       {"Sub Drone",        "tripleoscillator","TripleOscillator/ResonantPad.xpf",          0x1F618D},
       {"Texture Pad",      "organic",         "Organic/pad_rich.xpf",                      0x2E4057},
       {"Synth Strings",    "tripleoscillator","TripleOscillator/LSP-SynthStrings.xpf",     0x48C9B0},
       {"Kalimba",          "tripleoscillator","TripleOscillator/LSP-Kalimba.xpf",          0x76D7C4},
       {"Smoke Synth",      "tripleoscillator","TripleOscillator/LSP-SmokeSynth.xpf",      0x85C1E9},
       // Drums — soft ambient percussion
       {"Ambient Kick",     "audiofileprocessor","drums/kick_soft02.ogg",       0xE74C3C},
       {"Ambient Snare",    "audiofileprocessor","drums/snare_muffled01.ogg",   0xF39C12},
       {"Ambient Hat",      "audiofileprocessor","drums/hihat_closed05.ogg",    0x3498DB},
       {"Ambient Ride",     "audiofileprocessor","drums/ride02.ogg",            0x1ABC9C}},
      "ambient_chords","ambient" },

    // ── Lo-Fi ───────────────────────────────────────────────────────────────

    { "lofi", "Lo-Fi", 85, 4, 4, "F", "major",
      {"tape_sat",nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"Lofi Piano",       "organic",         "Organic/Wavy-LofPad.xpf",                   0xF39C12},
       {"Warm Bass",        "lb302",            "LB302/Wavy-SubBass.xpf",                   0x784212},
       {"Vinyl Pad",        "organic",         "Organic/pad_sweep.xpf",                     0xD35400},
       {"Dreamcore Keys",   "tripleoscillator","TripleOscillator/LSP-DreamcorePiano.xpf",   0xF5B041},
       {"Lofi Keyz",        "tripleoscillator","TripleOscillator/LSP-TanakaLofiKeyz.xpf",   0xEB984E},
       {"Dream Pad",        "tripleoscillator","TripleOscillator/LSP-Traum.xpf",            0xDC7633},
       // Drums — dusty lo-fi hip hop kit
       {"Lofi Kick",        "audiofileprocessor","drums/kick_hiphop01.ogg",     0xE74C3C},
       {"Lofi Snare",       "audiofileprocessor","drums/snare_hiphop01.ogg",    0xF39C12},
       {"Lofi Hat",         "audiofileprocessor","drums/hihat_closed03.ogg",    0x3498DB},
       {"Lofi Shaker",      "audiofileprocessor","drums/shaker01.ogg",          0x1ABC9C}},
      "lofi_chords","lofi" },

    // ── Jazz ─────────────────────────────────────────────────────────────────

    { "jazz", "Jazz", 100, 4, 4, "D", "minor",
      {nullptr,nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"Jazz Piano",       "opulenz",  "OpulenZ/Epiano.xpf",              0xD4AC0D},
       {"Upright Bass",     "lb302",    "LB302/Wavy-JazzBass.xpf",        0x784212},
       {"Jazz Organ",       "opulenz",  "OpulenZ/Combo_organ.xpf",        0xCA6F1E},
       {"E Piano",          "monstro",  "Monstro/LSP-EPiano.xpf",         0xD68910},
       {"Vibraphone",       "opulenz",  "OpulenZ/Vibraphone.xpf",         0xF0B27A},
       {"Funk Bass",        "tripleoscillator","TripleOscillator/LSP-FunkBass4.xpf",  0xB7950B},
       // Drums — acoustic jazz kit
       {"Jazz Kick",        "audiofileprocessor","drums/bassdrum_acoustic01.ogg", 0xE74C3C},
       {"Jazz Snare",       "audiofileprocessor","drums/snare_acoustic01.ogg",    0xF39C12},
       {"Jazz Hat",         "audiofileprocessor","drums/hihat_closed04.ogg",      0x3498DB},
       {"Jazz Ride",        "audiofileprocessor","drums/ride01.ogg",              0x1ABC9C}},
      "jazz_chords","jazz" },

    // ── 808 — sample-based channel rack ────────────────────────────────────

    { "808", "808", 140, 4, 4, "C", "minor",
      {nullptr,nullptr,nullptr,nullptr,nullptr,nullptr},
      {{"808 Kick",     "audiofileprocessor","808/808_kick.wav",         0xE74C3C},
       {"808 Clap",     "audiofileprocessor","808/808_clap.wav",         0xF39C12},
       {"808 Hat",      "audiofileprocessor","808/808_hihat_closed.wav", 0x3498DB},
       {"808 Snare",    "audiofileprocessor","808/808_snare.wav",        0x2ECC71},
       {"808 Sub Bass", "audiofileprocessor","808/808_sub_bass.wav",     0x9B59B6},
       {"","","",0},
       {"","","",0},{"","","",0},{"","","",0},{"","","",0}},
      "trap", "trap" },
};

static constexpr int kGenreModeCount = static_cast<int>(sizeof(kGenreModes) / sizeof(kGenreModes[0]));

inline int genreModeCount() { return kGenreModeCount; }

inline const GenreModeCfg* findGenreMode(const QString& key) {
    const QByteArray utf8 = key.toUtf8();
    const char* k = utf8.constData();
    for (int i = 0; i < kGenreModeCount; ++i)
        if (std::strcmp(kGenreModes[i].key, k) == 0) return &kGenreModes[i];
    return &kGenreModes[0]; // fallback to default
}
