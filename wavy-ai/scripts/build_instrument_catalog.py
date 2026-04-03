#!/usr/bin/env python3
"""Build the instrument catalog JSON from presets, samples, and GM data.

Usage:
    python wavy-ai/scripts/build_instrument_catalog.py

Output:
    wavy-ai/data/instrument_catalog.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
PRESETS_DIR = ROOT / "lmms-core" / "data" / "presets"
SAMPLES_DIR = ROOT / "lmms-core" / "data" / "samples"
OUTPUT = ROOT / "wavy-ai" / "data" / "instrument_catalog.json"

# ── Categories ───────────────────────────────────────────────────────────────
CATEGORIES = [
    "piano", "chromatic_perc", "organ", "guitar", "bass",
    "strings", "brass", "woodwind", "synth_lead", "synth_pad",
    "drums", "other",
]

# Plugins actually compiled in our LMMS_MINIMAL build
# (Nescaline, SID, Vibed, Watsyn are NOT built — skip their presets)
BUILT_PLUGINS = {
    "audiofileprocessor", "bitinvader", "kicker", "lb302",
    "monstro", "opulenz", "organic", "patman", "sf2player",
    "tripleoscillator", "xpressive",
}

# Map plugin dir name → internal plugin name (lowercase for matching)
PLUGIN_DIR_MAP = {
    "AudioFileProcessor": "audiofileprocessor",
    "BitInvader": "bitinvader",
    "Kicker": "kicker",
    "LB302": "lb302",
    "Monstro": "monstro",
    "Nescaline": "nescaline",
    "OpulenZ": "opulenz",
    "Organic": "organic",
    "SID": "sid",
    "TripleOscillator": "tripleoscillator",
    "Vibed": "vibed",
    "Watsyn": "watsyn",
    "Xpressive": "xpressive",
}

# Heuristic name → category mapping
def _guess_category(name: str, plugin: str, subdir: str = "") -> str:
    nl = name.lower()
    pl = plugin.lower()
    sl = subdir.lower()

    # Drums first
    if pl == "kicker" or sl in ("drums", "808", "beats"):
        return "drums"
    if any(w in nl for w in ("kick", "snare", "hihat", "clap", "hat", "drum", "perc", "shaker", "ride", "cymbal", "tom")):
        return "drums"

    # Bass
    if sl == "basses" or sl == "bassloops":
        return "bass"
    if any(w in nl for w in ("bass", "sub", "808_sub", "lb302", "reese")):
        return "bass"
    if pl == "lb302":
        return "bass"

    # Organ
    if any(w in nl for w in ("organ", "leslie", "combo_organ")):
        return "organ"

    # Piano / Keys
    if any(w in nl for w in ("piano", "epiano", "e-piano", "keyz", "keys")):
        return "piano"

    # Strings
    if sl == "stringsnpads":
        return "strings"
    if any(w in nl for w in ("string", "cello", "violin", "viola")):
        return "strings"

    # Brass
    if any(w in nl for w in ("brass", "trumpet", "trombone", "horn")):
        return "brass"

    # Woodwind
    if any(w in nl for w in ("clarinet", "flute", "oboe", "sax", "bagpipe")):
        return "woodwind"

    # Pads
    if any(w in nl for w in ("pad", "ambient", "drone", "texture", "ethereal", "sweep")):
        return "synth_pad"
    if pl == "organic" and "pad" not in nl and "organ" not in nl:
        return "synth_pad"

    # Chromatic percussion
    if any(w in nl for w in ("bell", "vibraphone", "kalimba", "marimba", "xylophone", "glocken", "chime")):
        return "chromatic_perc"
    if sl == "instruments":
        return "chromatic_perc"

    # Lead / synth
    if any(w in nl for w in ("lead", "stab", "arp", "supersaw", "synth", "electro")):
        return "synth_lead"

    # Guitar
    if any(w in nl for w in ("guitar",)):
        return "guitar"

    return "other"


def _name_from_filename(filename: str) -> str:
    """Convert a preset/sample filename to a human-readable name."""
    stem = Path(filename).stem
    # Convert CamelCase or snake_case to spaced
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', stem)
    name = name.replace('_', ' ').replace('-', ' ')
    # Clean up multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _tags_from_name(name: str, category: str, plugin: str) -> list[str]:
    tags = [category]
    nl = name.lower()
    if plugin:
        tags.append(plugin)
    # Add genre hints
    for kw in ("trap", "house", "jazz", "lofi", "lo-fi", "ambient", "future",
               "808", "funk", "soul", "hip hop", "hiphop", "rock", "latin",
               "acid", "synthwave", "cyberpunk", "detroit"):
        if kw in nl:
            tags.append(kw.replace(" ", "_"))
    return list(dict.fromkeys(tags))  # dedupe preserving order


# ── GM Patch names (General MIDI standard) ──────────────────────────────────
GM_PATCHES = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord",
    "Clavi", "Celesta", "Glockenspiel", "Music Box", "Vibraphone", "Marimba",
    "Xylophone", "Tubular Bells", "Dulcimer", "Drawbar Organ", "Percussive Organ",
    "Rock Organ", "Church Organ", "Reed Organ", "Accordion", "Harmonica",
    "Tango Accordion", "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)", "Electric Guitar (clean)", "Electric Guitar (muted)",
    "Overdriven Guitar", "Distortion Guitar", "Guitar harmonics", "Acoustic Bass",
    "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2", "Violin",
    "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings",
    "Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2",
    "Synth Strings 1", "Synth Strings 2", "Choir Aahs", "Voice Oohs",
    "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba",
    "Muted Trumpet", "French Horn", "Brass Section", "Synth Brass 1",
    "Synth Brass 2", "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
    "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
    "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
    "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bag pipe", "Fiddle",
    "Shanai", "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock", "Taiko Drum",
    "Melodic Tom", "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise",
    "Breath Noise", "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter",
    "Applause", "Gunshot",
]

# GM patch → category
GM_CATEGORY = {
    range(0, 8): "piano",
    range(8, 16): "chromatic_perc",
    range(16, 24): "organ",
    range(24, 32): "guitar",
    range(32, 40): "bass",
    range(40, 48): "strings",
    range(48, 56): "strings",  # ensembles + choir
    range(56, 64): "brass",
    range(64, 72): "woodwind",
    range(72, 80): "woodwind",  # pipes
    range(80, 88): "synth_lead",
    range(88, 96): "synth_pad",
    range(96, 104): "other",  # FX
    range(104, 112): "other",  # ethnic
    range(112, 120): "chromatic_perc",  # percussive
    range(120, 128): "other",  # sound effects
}

def _gm_category(patch: int) -> str:
    for r, cat in GM_CATEGORY.items():
        if patch in r:
            return cat
    return "other"

# ── External pack definitions ────────────────────────────────────────────────
EXTERNAL_PACKS = [
    {
        "pack_name": "Salamander Piano",
        "url": "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPianoV3+20161209_48khz24bit.sf2",
        "filename": "SalamanderGrandPiano.sf2",
        "size_mb": 15,
        "license": "CC-BY-3.0",
        "description": "Concert grand piano — 16 velocity layers, Public Domain samples",
    },
    {
        "pack_name": "Hydrogen GMkit",
        "url": "https://github.com/hydrogen-music/hydrogen/releases/download/1.2.3/GMkit.h2drumkit",
        "filename": "GMkit.h2drumkit",
        "size_mb": 15,
        "license": "GPL-2.0",
        "description": "Full GM drum kit — multi-velocity acoustic drums",
    },
]

VST3_REFERENCES = [
    {
        "name": "Surge XT",
        "description": "Free open-source hybrid synthesizer — wavetable, FM, subtractive, effects",
        "install_url": "https://surge-synthesizer.github.io/",
        "license": "GPL-3.0",
    },
    {
        "name": "Vital",
        "description": "Spectral warping wavetable synth — free tier available, modern UI",
        "install_url": "https://vital.audio/",
        "license": "GPL-3.0 (free tier)",
    },
    {
        "name": "Dexed",
        "description": "DX7 FM synthesizer emulation — 32 algorithms, 144 presets, free",
        "install_url": "https://asb2m10.github.io/dexed/",
        "license": "GPL-3.0",
    },
    {
        "name": "Spitfire LABS",
        "description": "Free orchestral/texture instruments — piano, strings, choir, drums",
        "install_url": "https://labs.spitfireaudio.com/",
        "license": "Freeware",
    },
]


def build_catalog() -> list[dict]:
    entries: list[dict] = []

    # ── 1. Built-in XPF presets ──────────────────────────────────────────
    if PRESETS_DIR.exists():
        for xpf in sorted(PRESETS_DIR.rglob("*.xpf")):
            rel = xpf.relative_to(PRESETS_DIR)
            plugin_dir = rel.parts[0]
            plugin = PLUGIN_DIR_MAP.get(plugin_dir, plugin_dir.lower())
            # Skip plugins not in our build
            if plugin not in BUILT_PLUGINS:
                continue
            name = _name_from_filename(xpf.name)
            cat = _guess_category(name, plugin)
            preset_rel = str(rel).replace("\\", "/")
            entry_id = f"builtin:{plugin}:{xpf.stem}"

            entries.append({
                "id": entry_id,
                "name": name,
                "plugin": plugin,
                "preset": preset_rel,
                "source": "builtin",
                "category": cat,
                "tags": _tags_from_name(name, cat, plugin),
                "license": "GPL-2.0",
                "requires_download": False,
                "pack": None,
                "gm_patch": None,
                "sf2_bank": None,
                "sample_path": None,
                "install_url": None,
                "description": f"{plugin_dir} preset",
            })

    # ── 2. Built-in audio samples ────────────────────────────────────────
    if SAMPLES_DIR.exists():
        audio_exts = {".ogg", ".wav", ".flac", ".aiff"}
        for sample in sorted(SAMPLES_DIR.rglob("*")):
            if not sample.is_file() or sample.suffix.lower() not in audio_exts:
                continue
            rel = sample.relative_to(SAMPLES_DIR)
            subdir = rel.parts[0] if len(rel.parts) > 1 else ""
            name = _name_from_filename(sample.name)
            cat = _guess_category(name, "audiofileprocessor", subdir)
            sample_rel = str(rel).replace("\\", "/")
            entry_id = f"builtin_sample:{subdir}:{sample.stem}"

            entries.append({
                "id": entry_id,
                "name": name,
                "plugin": "audiofileprocessor",
                "preset": None,
                "source": "builtin_sample",
                "category": cat,
                "tags": _tags_from_name(name, cat, "audiofileprocessor"),
                "license": "GPL-2.0",
                "requires_download": False,
                "pack": None,
                "gm_patch": None,
                "sf2_bank": None,
                "sample_path": sample_rel,
                "install_url": None,
                "description": f"Sample from {subdir or 'root'}",
            })

    # ── 3. GM SoundFont instruments (128 melodic + 1 drum kit) ───────────
    for patch_num, patch_name in enumerate(GM_PATCHES):
        cat = _gm_category(patch_num)
        entry_id = f"gm:{patch_num:03d}:{patch_name.replace(' ', '_')}"
        entries.append({
            "id": entry_id,
            "name": patch_name,
            "plugin": "sf2player",
            "preset": None,
            "source": "gm_soundfont",
            "category": cat,
            "tags": [cat, "gm", "general_midi"],
            "license": "Various (SF2-dependent)",
            "requires_download": True,
            "pack": "GM SoundFont",
            "gm_patch": patch_num,
            "sf2_bank": 0,
            "sample_path": None,
            "install_url": None,
            "description": f"GM patch {patch_num} — requires a GM SoundFont (GeneralUser GS, FluidR3, or MuseScore)",
        })

    # GM Standard Drum Kit (bank 128, patch 0)
    entries.append({
        "id": "gm:drum_kit:Standard",
        "name": "GM Standard Drum Kit",
        "plugin": "sf2player",
        "preset": None,
        "source": "gm_soundfont",
        "category": "drums",
        "tags": ["drums", "gm", "general_midi", "drum_kit"],
        "license": "Various (SF2-dependent)",
        "requires_download": True,
        "pack": "GM SoundFont",
        "gm_patch": 0,
        "sf2_bank": 128,
        "sample_path": None,
        "install_url": None,
        "description": "GM Standard Drum Kit — requires a GM SoundFont",
    })

    # ── 4. External SF2 packs ────────────────────────────────────────────
    for pack in EXTERNAL_PACKS:
        entry_id = f"external:{pack['pack_name'].replace(' ', '_')}"
        cat = "piano" if "piano" in pack["pack_name"].lower() else "drums"
        entries.append({
            "id": entry_id,
            "name": pack["pack_name"],
            "plugin": "sf2player",
            "preset": None,
            "source": "external",
            "category": cat,
            "tags": [cat, "sf2", "downloadable"],
            "license": pack["license"],
            "requires_download": True,
            "pack": pack["pack_name"],
            "gm_patch": None,
            "sf2_bank": None,
            "sample_path": None,
            "install_url": pack["url"],
            "description": pack["description"],
        })

    # ── 5. VST3 references ───────────────────────────────────────────────
    for vst in VST3_REFERENCES:
        entry_id = f"vst3:{vst['name'].replace(' ', '_')}"
        entries.append({
            "id": entry_id,
            "name": vst["name"],
            "plugin": "carlarack",
            "preset": None,
            "source": "vst3_reference",
            "category": "synth_lead",
            "tags": ["vst3", "external", "synth"],
            "license": vst["license"],
            "requires_download": True,
            "pack": None,
            "gm_patch": None,
            "sf2_bank": None,
            "sample_path": None,
            "install_url": vst["install_url"],
            "description": vst["description"],
        })

    return entries


def main():
    entries = build_catalog()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    # Summary
    sources = {}
    cats = {}
    for e in entries:
        sources[e["source"]] = sources.get(e["source"], 0) + 1
        cats[e["category"]] = cats.get(e["category"], 0) + 1

    print(f"Instrument catalog generated: {len(entries)} entries -> {OUTPUT}")
    print(f"\nBy source:")
    for s, c in sorted(sources.items()):
        print(f"  {s}: {c}")
    print(f"\nBy category:")
    for s, c in sorted(cats.items()):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()
