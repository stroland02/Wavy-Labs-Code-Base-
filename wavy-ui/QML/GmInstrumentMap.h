#pragma once

#include <QString>
#include <cstring>

// ---------------------------------------------------------------------------
// GmInstrumentMap.h — header-only GM program → category → genre-specific
// plugin/preset/reverb mapping for smart MIDI import.
//
// Default strategy: use sf2player with the actual GM patch number so MIDI
// files sound as intended (piano = piano, strings = strings, etc.).
// Genre overrides swap in LMMS synth plugins with curated presets.
//
// Special plugin values:
//   "sf2player"       → SF2 player, set patch to gmPatch field
//   "sf2player-drums" → SF2 player, bank 128 (GM percussion kit)
// ---------------------------------------------------------------------------

enum class GmCategory {
    Piano,         // GM 0-7
    ChromaticPerc, // GM 8-15
    Organ,         // GM 16-23
    Guitar,        // GM 24-31
    Bass,          // GM 32-39
    Strings,       // GM 40-55 (strings + ensemble)
    Brass,         // GM 56-63
    Woodwind,      // GM 64-79 (reed + pipe)
    SynthLead,     // GM 80-87
    SynthPad,      // GM 88-103 (synth pad + synth fx)
    Drums,         // GM 112-119 (percussive) + 128 (drum channel)
    Other,         // GM 104-111 (ethnic), 120-127 (sfx)
    _Count
};

static constexpr int kGmCategoryCount = static_cast<int>(GmCategory::_Count);

struct GmMapping {
    const char* plugin;      // "sf2player", "sf2player-drums", or synth name
    const char* preset;      // XPF preset path (synths only) or ""
    int         gmPatch;     // GM patch number for sf2player (0-127), -1 = use from MIDI
    float       reverbWet;   // 0.0 = dry, 1.0 = full wet
};

// ---------------------------------------------------------------------------
// GM program → category
// ---------------------------------------------------------------------------

inline GmCategory gmProgramToCategory(int program)
{
    if (program == 128)                     return GmCategory::Drums;
    if (program < 0 || program > 127)       return GmCategory::Other;
    if (program <=  7)                      return GmCategory::Piano;
    if (program <= 15)                      return GmCategory::ChromaticPerc;
    if (program <= 23)                      return GmCategory::Organ;
    if (program <= 31)                      return GmCategory::Guitar;
    if (program <= 39)                      return GmCategory::Bass;
    if (program <= 55)                      return GmCategory::Strings;
    if (program <= 63)                      return GmCategory::Brass;
    if (program <= 79)                      return GmCategory::Woodwind;
    if (program <= 87)                      return GmCategory::SynthLead;
    if (program <= 103)                     return GmCategory::SynthPad;
    if (program <= 111)                     return GmCategory::Other;
    return GmCategory::Drums; // 112-119 percussive
}

// ---------------------------------------------------------------------------
// Category string → enum (for Python→C++ bridge)
// ---------------------------------------------------------------------------

inline GmCategory categoryFromString(const QString& str)
{
    const QByteArray s = str.toLower().toUtf8();
    if (s == "piano")          return GmCategory::Piano;
    if (s == "chromatic_perc") return GmCategory::ChromaticPerc;
    if (s == "organ")          return GmCategory::Organ;
    if (s == "guitar")         return GmCategory::Guitar;
    if (s == "bass")           return GmCategory::Bass;
    if (s == "strings")        return GmCategory::Strings;
    if (s == "brass")          return GmCategory::Brass;
    if (s == "woodwind")       return GmCategory::Woodwind;
    if (s == "synth_lead")     return GmCategory::SynthLead;
    if (s == "synth_pad")      return GmCategory::SynthPad;
    if (s == "drums")          return GmCategory::Drums;
    return GmCategory::Other;
}

// ---------------------------------------------------------------------------
// Default mapping — sf2player with representative GM patch per category.
// MIDI files were composed for GM instruments, so sf2player gives faithful
// playback.  gmPatch = -1 means "use the actual GM program from the MIDI".
// ---------------------------------------------------------------------------

static const GmMapping kDefaultGmMap[kGmCategoryCount] = {
    //                 plugin           preset  gmPatch  reverbWet
    /* Piano        */ { "sf2player",       "",    -1,     0.15f },
    /* ChromaticPerc*/ { "sf2player",       "",    -1,     0.15f },
    /* Organ        */ { "sf2player",       "",    -1,     0.12f },
    /* Guitar       */ { "sf2player",       "",    -1,     0.12f },
    /* Bass         */ { "sf2player",       "",    -1,     0.00f },
    /* Strings      */ { "sf2player",       "",    -1,     0.25f },
    /* Brass        */ { "sf2player",       "",    -1,     0.15f },
    /* Woodwind     */ { "sf2player",       "",    -1,     0.15f },
    /* SynthLead    */ { "sf2player",       "",    -1,     0.10f },
    /* SynthPad     */ { "sf2player",       "",    -1,     0.25f },
    /* Drums        */ { "sf2player-drums", "",    -1,     0.00f },
    /* Other        */ { "sf2player",       "",    -1,     0.10f },
};

// ---------------------------------------------------------------------------
// Genre override table — swap sf2player for genre-specific synth presets
// ---------------------------------------------------------------------------

struct GenreGmOverride {
    const char*  genreKey;
    GmMapping    map[kGmCategoryCount];
};

static const GenreGmOverride kGenreGmOverrides[] = {

    // ── Future Bass ─────────────────────────────────────────────────────────
    { "future_bass", {
        /* Piano        */ { "sf2player",        "",                                     -1, 0.25f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.20f },
        /* Organ        */ { "sf2player",        "",                                     -1, 0.20f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.20f },
        /* Bass         */ { "lb302",            "LB302/GoodOldTimes.xpf",              -1, 0.00f },
        /* Strings      */ { "tripleoscillator", "TripleOscillator/FutureBass.xpf",     -1, 0.30f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.15f },
        /* SynthLead    */ { "monstro",          "Monstro/Phat.xpf",                    -1, 0.20f },
        /* SynthPad     */ { "tripleoscillator", "TripleOscillator/FutureBass.xpf",     -1, 0.30f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.10f },
    }},

    // ── House ───────────────────────────────────────────────────────────────
    { "house", {
        /* Piano        */ { "sf2player",        "",                                     -1, 0.20f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.15f },
        /* Organ        */ { "opulenz",          "OpulenZ/Combo_organ.xpf",             -1, 0.20f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.15f },
        /* Bass         */ { "lb302",            "LB302/Wavy-HouseBass.xpf",            -1, 0.00f },
        /* Strings      */ { "sf2player",        "",                                     -1, 0.25f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.15f },
        /* SynthLead    */ { "tripleoscillator", "TripleOscillator/Wavy-HouseStab.xpf", -1, 0.20f },
        /* SynthPad     */ { "sf2player",        "",                                     -1, 0.25f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.10f },
    }},

    // ── Trap ────────────────────────────────────────────────────────────────
    { "trap", {
        /* Piano        */ { "sf2player",        "",                                     -1, 0.15f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.10f },
        /* Organ        */ { "sf2player",        "",                                     -1, 0.10f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.15f },
        /* Bass         */ { "lb302",            "LB302/Wavy-SubBass.xpf",              -1, 0.00f },
        /* Strings      */ { "sf2player",        "",                                     -1, 0.20f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.10f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.10f },
        /* SynthLead    */ { "tripleoscillator", "TripleOscillator/Wavy-TrapLead.xpf",  -1, 0.15f },
        /* SynthPad     */ { "sf2player",        "",                                     -1, 0.20f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.10f },
    }},

    // ── Ambient ─────────────────────────────────────────────────────────────
    { "ambient", {
        /* Piano        */ { "sf2player",        "",                                     -1, 0.40f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.35f },
        /* Organ        */ { "sf2player",        "",                                     -1, 0.35f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.30f },
        /* Bass         */ { "sf2player",        "",                                     -1, 0.00f },
        /* Strings      */ { "organic",          "Organic/pad_rich.xpf",                -1, 0.40f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.30f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.30f },
        /* SynthLead    */ { "organic",          "Organic/pad_ethereal.xpf",            -1, 0.35f },
        /* SynthPad     */ { "organic",          "Organic/pad_rich.xpf",                -1, 0.40f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.30f },
    }},

    // ── Lo-Fi ───────────────────────────────────────────────────────────────
    { "lofi", {
        /* Piano        */ { "sf2player",        "",                                      0, 0.20f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.15f },
        /* Organ        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.15f },
        /* Bass         */ { "lb302",            "LB302/Wavy-SubBass.xpf",              -1, 0.00f },
        /* Strings      */ { "sf2player",        "",                                     -1, 0.25f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.15f },
        /* SynthLead    */ { "organic",          "Organic/Wavy-LofPad.xpf",             -1, 0.20f },
        /* SynthPad     */ { "organic",          "Organic/pad_sweep.xpf",               -1, 0.25f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.10f },
    }},

    // ── 808 — AudioFileProcessor with 808 WAV samples ─────────────────────
    { "808", {
        /* Piano        */ { "audiofileprocessor","808/808_kick.wav",                    -1, 0.10f },
        /* ChromaticPerc*/ { "audiofileprocessor","808/808_clap.wav",                    -1, 0.00f },
        /* Organ        */ { "audiofileprocessor","808/808_hihat_closed.wav",            -1, 0.00f },
        /* Guitar       */ { "audiofileprocessor","808/808_snare.wav",                   -1, 0.10f },
        /* Bass         */ { "audiofileprocessor","808/808_sub_bass.wav",                -1, 0.00f },
        /* Strings      */ { "audiofileprocessor","808/808_hihat_closed.wav",            -1, 0.10f },
        /* Brass        */ { "audiofileprocessor","808/808_clap.wav",                    -1, 0.00f },
        /* Woodwind     */ { "audiofileprocessor","808/808_hihat_closed.wav",            -1, 0.00f },
        /* SynthLead    */ { "audiofileprocessor","808/808_kick.wav",                    -1, 0.10f },
        /* SynthPad     */ { "audiofileprocessor","808/808_sub_bass.wav",                -1, 0.10f },
        /* Drums        */ { "audiofileprocessor","808/808_kick.wav",                    -1, 0.00f },
        /* Other        */ { "audiofileprocessor","808/808_snare.wav",                   -1, 0.00f },
    }},

    // ── Jazz ────────────────────────────────────────────────────────────────
    { "jazz", {
        /* Piano        */ { "sf2player",        "",                                      0, 0.20f },
        /* ChromaticPerc*/ { "sf2player",        "",                                     -1, 0.15f },
        /* Organ        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Guitar       */ { "sf2player",        "",                                     -1, 0.15f },
        /* Bass         */ { "sf2player",        "",                                     32, 0.00f },
        /* Strings      */ { "sf2player",        "",                                     -1, 0.30f },
        /* Brass        */ { "sf2player",        "",                                     -1, 0.15f },
        /* Woodwind     */ { "sf2player",        "",                                     -1, 0.15f },
        /* SynthLead    */ { "sf2player",        "",                                      0, 0.20f },
        /* SynthPad     */ { "sf2player",        "",                                     -1, 0.25f },
        /* Drums        */ { "sf2player-drums",  "",                                     -1, 0.00f },
        /* Other        */ { "sf2player",        "",                                     -1, 0.10f },
    }},
};

static constexpr int kGenreGmOverrideCount =
    static_cast<int>(sizeof(kGenreGmOverrides) / sizeof(kGenreGmOverrides[0]));

// ---------------------------------------------------------------------------
// Resolve: genre + category → GmMapping
// ---------------------------------------------------------------------------

inline const GmMapping& resolveGmMapping(const QString& genreKey, GmCategory cat)
{
    const int idx = static_cast<int>(cat);
    if (idx < 0 || idx >= kGmCategoryCount)
        return kDefaultGmMap[static_cast<int>(GmCategory::Other)];

    if (!genreKey.isEmpty() && genreKey != QStringLiteral("default")) {
        const QByteArray utf8 = genreKey.toUtf8();
        const char* k = utf8.constData();
        for (int i = 0; i < kGenreGmOverrideCount; ++i) {
            if (std::strcmp(kGenreGmOverrides[i].genreKey, k) == 0)
                return kGenreGmOverrides[i].map[idx];
        }
    }
    return kDefaultGmMap[idx];
}
