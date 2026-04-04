"""
ElevenLabs API providers — TTS, Voice Cloning (Instant + Professional),
Speech-to-Speech, Music, SFX, Voice Isolator, Scribe (STT),
Forced Alignment, AI Dubbing, Voice Remixing.

All providers use the `elevenlabs` PyPI SDK.
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path

from loguru import logger

import soundfile as sf

import config


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_sdk():
    """Import and return the elevenlabs SDK; raise ImportError if missing."""
    try:
        import elevenlabs  # noqa: F811
        return elevenlabs
    except ImportError:
        raise ImportError(
            "elevenlabs package not installed. "
            "Run: pip install elevenlabs"
        )


def _require_key() -> str:
    """Return the API key or raise RuntimeError."""
    key = config.ELEVENLABS_API_KEY
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. "
            "Get a key at https://elevenlabs.io and set it as an environment variable."
        )
    return key


# Cached ElevenLabs client — reused across all providers
_cached_client = None
_cached_key: str | None = None


def _get_client():
    """Return a cached ElevenLabs client (recreated if the API key changes)."""
    global _cached_client, _cached_key
    el = _require_sdk()
    key = _require_key()
    if _cached_client is None or _cached_key != key:
        _cached_client = el.ElevenLabs(api_key=key)
        _cached_key = key
    return _cached_client, el


def _save_audio(audio_iter, path: Path) -> Path:
    """Write a streaming audio response to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for chunk in audio_iter:
            f.write(chunk)
    return path


def _unique_path(directory: Path, prefix: str, ext: str = ".mp3") -> Path:
    """Generate a unique file path in the given directory."""
    ts = int(time.time() * 1000)
    return directory / f"{prefix}_{ts}{ext}"


# ---------------------------------------------------------------------------
# 1. Text-to-Speech
# ---------------------------------------------------------------------------

class ElevenLabsTTSProvider:
    """Generate speech from text using ElevenLabs TTS."""

    def generate(
        self,
        text: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",  # George (default)
        model: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        seed: int = -1,
        language_code: str = "",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs TTS: voice={voice_id} model={model} len={len(text)}")

        kwargs: dict = dict(
            text=text,
            voice_id=voice_id,
            model_id=model,
            voice_settings=el.VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=use_speaker_boost,
            ),
        )
        if seed >= 0:
            kwargs["seed"] = seed
        if language_code:
            kwargs["language_code"] = language_code

        audio_iter = client.text_to_speech.convert(**kwargs)

        out = _unique_path(Path(config.VOCALS_DIR), "el_tts")
        _save_audio(audio_iter, out)

        info = sf.info(str(out))
        logger.info(f"ElevenLabs TTS complete: {out.name} ({info.duration:.1f}s)")

        return {
            "audio_path": str(out),
            "duration": info.duration,
            "sample_rate": info.samplerate,
            "voice_id": voice_id,
        }


# ---------------------------------------------------------------------------
# 2. Instant Voice Cloning
# ---------------------------------------------------------------------------

class ElevenLabsVoiceCloningProvider:
    """Clone a voice from audio samples."""

    def clone_instant(
        self,
        name: str,
        audio_paths: list[str],
        description: str = "",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs voice clone: name={name!r} files={len(audio_paths)}")

        files = [open(p, "rb") for p in audio_paths]
        try:
            voice = client.clone(
                name=name,
                description=description or f"Cloned voice: {name}",
                files=files,
            )
        finally:
            for f in files:
                f.close()

        logger.info(f"ElevenLabs voice cloned: id={voice.voice_id} name={voice.name}")

        return {
            "voice_id": voice.voice_id,
            "name": voice.name,
        }


# ---------------------------------------------------------------------------
# 3. Speech-to-Speech
# ---------------------------------------------------------------------------

class ElevenLabsSpeechToSpeechProvider:
    """Convert speech from one voice to another."""

    def convert(
        self,
        audio_path: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model: str = "eleven_multilingual_sts_v2",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs STS: voice={voice_id} input={audio_path}")

        with open(audio_path, "rb") as f:
            audio_iter = client.speech_to_speech.convert(
                voice_id=voice_id,
                audio=f,
                model_id=model,
            )

        out = _unique_path(Path(config.VOCALS_DIR), "el_sts")
        _save_audio(audio_iter, out)

        info = sf.info(str(out))
        logger.info(f"ElevenLabs STS complete: {out.name} ({info.duration:.1f}s)")

        return {
            "audio_path": str(out),
            "voice_id": voice_id,
        }


# ---------------------------------------------------------------------------
# 4. Music Generation (ElevenMusic)
# ---------------------------------------------------------------------------

class ElevenLabsMusicProvider:
    """Generate music using ElevenLabs music generation API."""

    def generate(
        self,
        prompt: str,
        duration: float = 30.0,
        tempo: int = 120,
        key: str = "",
        genre: str = "",
        seed: int = -1,
        force_instrumental: bool = False,
        lyrics_text: str = "",
        tier: str = "free",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        # Only include tempo/key when explicitly set (non-default) to avoid
        # polluting the prompt when the user is on Simple tab (where tempo=120 default)
        parts = [p for p in [
            genre,
            prompt,
            f"{tempo}bpm" if tempo and tempo != 120 else "",
            f"key of {key}" if key else "",
        ] if p]
        full_prompt = " ".join(parts)

        # Clamp to ElevenLabs Music limits: 10s–240s
        music_length_ms = int(max(10.0, min(duration, 240.0)) * 1000)

        logger.info(
            f"ElevenLabs music gen: prompt={full_prompt!r} "
            f"duration={music_length_ms/1000:.1f}s instrumental={force_instrumental} "
            f"custom_lyrics={bool(lyrics_text)}"
        )

        out = _unique_path(Path(config.GENERATION_DIR), "el_music")

        if lyrics_text and not force_instrumental:
            # Custom lyrics mode — parse [Section] tags for multi-section composition
            from elevenlabs.types import MusicPrompt, SongSection
            import re as _re

            # Parse section tags: [Intro], [Verse], [Chorus], [Bridge], [Outro], etc.
            section_pattern = _re.compile(r'^\[([^\]]+)\]\s*$', _re.MULTILINE)
            raw_lines = lyrics_text.splitlines()

            sections: list[SongSection] = []
            current_section_name = "main"
            current_lines: list[str] = []

            # Section-specific style hints
            _SECTION_STYLES: dict[str, list[str]] = {
                "intro": ["gentle", "building"],
                "verse": ["storytelling", "moderate energy"],
                "chorus": ["powerful", "anthemic", "hook"],
                "bridge": ["contrasting", "emotional shift"],
                "outro": ["resolving", "fading"],
                "pre-chorus": ["building tension", "anticipation"],
                "drop": ["high energy", "impactful"],
                "breakdown": ["stripped back", "minimal"],
            }

            for raw_line in raw_lines:
                match = section_pattern.match(raw_line.strip())
                if match:
                    # Save previous section
                    if current_lines:
                        sections.append((current_section_name, current_lines))
                    current_section_name = match.group(1)
                    current_lines = []
                elif raw_line.strip():
                    current_lines.append(raw_line.strip())

            # Save final section
            if current_lines:
                sections.append((current_section_name, current_lines))

            # If no section tags found, treat as single section
            if not sections:
                lines = [l for l in raw_lines if l.strip()]
                song_sections = [SongSection(
                    section_name="main",
                    positive_local_styles=[],
                    negative_local_styles=[],
                    duration_ms=music_length_ms,
                    lines=lines,
                )]
            else:
                # Distribute duration proportionally by line count
                total_lines = max(1, sum(len(lns) for _, lns in sections))
                song_sections = []
                for sec_name, sec_lines in sections:
                    sec_fraction = len(sec_lines) / total_lines
                    sec_duration = max(5000, int(music_length_ms * sec_fraction))
                    sec_key = sec_name.lower().strip()
                    local_styles = _SECTION_STYLES.get(sec_key, [])
                    song_sections.append(SongSection(
                        section_name=sec_name,
                        positive_local_styles=local_styles,
                        negative_local_styles=[],
                        duration_ms=sec_duration,
                        lines=sec_lines,
                    ))

            composition_plan = MusicPrompt(
                positive_global_styles=[full_prompt] if full_prompt else [],
                negative_global_styles=[],
                sections=song_sections,
            )
            compose_kwargs: dict = dict(
                composition_plan=composition_plan,
                model_id="music_v1",
            )
            if seed >= 0:
                compose_kwargs["seed"] = seed
            logger.info(f"[DEBUG] compose mode=composition_plan sections={len(song_sections)} "
                        f"names={[s.section_name for s in song_sections]}")
        else:
            # Auto or Instrumental — simple prompt-based
            compose_kwargs = dict(
                prompt=full_prompt,
                music_length_ms=music_length_ms,
                model_id="music_v1",
            )
            if force_instrumental:
                compose_kwargs["force_instrumental"] = True
            if seed >= 0:
                compose_kwargs["seed"] = seed
            logger.info(
                f"[DEBUG] compose mode=prompt  kwargs={{ "
                f"prompt={full_prompt!r}, "
                f"music_length_ms={music_length_ms}, "
                f"model_id='music_v1', "
                f"force_instrumental={compose_kwargs.get('force_instrumental', 'OMIT')}"
                f" }}"
            )

        logger.info(f"[DEBUG] calling client.music.compose() ...")
        response = client.music.compose(**compose_kwargs)
        logger.info(f"[DEBUG] compose() returned: type={type(response).__name__}")

        # compose() returns Iterator[bytes]
        _save_audio(response, out)

        info = sf.info(str(out))
        logger.info(
            f"[DEBUG] saved → {out.name}  duration={info.duration:.1f}s  "
            f"samplerate={info.samplerate}  channels={info.channels}"
        )
        logger.info(f"ElevenLabs music gen complete: {out.name} ({info.duration:.1f}s)")

        return {
            "audio_path": str(out),
            "duration": info.duration,
            "sample_rate": info.samplerate,
        }

    def separate_stems(
        self,
        audio_path: str,
        **_kwargs,
    ) -> dict:
        """Split an ElevenLabs-generated track into stems using the EL Music API."""
        client, el = _get_client()

        logger.info(f"ElevenLabs music stem split: input={audio_path}")

        with open(audio_path, "rb") as f:
            response = client.music.separate_stems(file=f)

        # Response is a dict/object with stem names as keys mapping to audio bytes
        stems_dir = Path(config.STEMS_DIR)
        stems_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)

        stem_paths: dict[str, str] = {}
        if isinstance(response, dict):
            for stem_name, audio_data in response.items():
                out = stems_dir / f"el_stem_{stem_name}_{ts}.mp3"
                if isinstance(audio_data, bytes):
                    out.write_bytes(audio_data)
                else:
                    _save_audio(audio_data, out)
                stem_paths[stem_name] = str(out)
        else:
            # Fallback: treat as single audio blob
            out = stems_dir / f"el_stem_output_{ts}.mp3"
            if isinstance(response, bytes):
                out.write_bytes(response)
            else:
                _save_audio(response, out)
            stem_paths["output"] = str(out)

        logger.info(f"ElevenLabs stem split complete: {list(stem_paths.keys())}")

        return {"stems": stem_paths}


# ---------------------------------------------------------------------------
# 5. Sound Effects
# ---------------------------------------------------------------------------

class ElevenLabsSFXProvider:
    """Generate sound effects from text descriptions."""

    def generate(
        self,
        text: str,
        duration_seconds: float = 5.0,
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs SFX: text={text!r} duration={duration_seconds}s")

        audio_iter = client.text_to_sound_effects.convert(
            text=text,
            duration_seconds=duration_seconds,
        )

        out = _unique_path(Path(config.SFX_DIR), "el_sfx")
        _save_audio(audio_iter, out)

        info = sf.info(str(out))
        logger.info(f"ElevenLabs SFX complete: {out.name} ({info.duration:.1f}s)")

        return {
            "audio_path": str(out),
            "duration": info.duration,
        }


# ---------------------------------------------------------------------------
# 6. Voice Isolator
# ---------------------------------------------------------------------------

class ElevenLabsVoiceIsolatorProvider:
    """Isolate vocals from audio using ElevenLabs Audio Isolation."""

    def isolate(
        self,
        audio_path: str,
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs voice isolate: input={audio_path}")

        with open(audio_path, "rb") as f:
            audio_iter = client.audio_isolation.convert(audio=f)

        out = _unique_path(Path(config.STEMS_DIR), "el_isolated")
        _save_audio(audio_iter, out)

        logger.info(f"ElevenLabs voice isolation complete: {out.name}")

        return {
            "audio_path": str(out),
        }


# ---------------------------------------------------------------------------
# 7. Scribe (Speech-to-Text)
# ---------------------------------------------------------------------------

class ElevenLabsScribeProvider:
    """Transcribe audio using ElevenLabs Scribe."""

    def transcribe(
        self,
        audio_path: str,
        language_code: str = "",
        diarize: bool = False,
        num_speakers: int = 0,
        timestamps_granularity: str = "word",
        tag_audio_events: bool = True,
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(
            f"ElevenLabs transcribe (scribe_v2): input={audio_path} "
            f"lang={language_code or 'auto'} diarize={diarize}"
        )

        stt_kwargs: dict = dict(
            file=None,  # set below
            model_id="scribe_v2",
            tag_audio_events=tag_audio_events,
            timestamps_granularity=timestamps_granularity,
        )
        if language_code:
            stt_kwargs["language_code"] = language_code
        if diarize:
            stt_kwargs["diarize"] = True
        if num_speakers > 0:
            stt_kwargs["num_speakers"] = num_speakers

        with open(audio_path, "rb") as f:
            stt_kwargs["file"] = f
            result = client.speech_to_text.convert(**stt_kwargs)

        text = result.text
        words = []
        for w in (result.words or []):
            entry = {"word": w.text, "start": w.start, "end": w.end}
            if diarize and hasattr(w, "speaker_id"):
                entry["speaker"] = w.speaker_id
            words.append(entry)

        # Save transcript
        out = _unique_path(Path(config.TRANSCRIPTS_DIR), "el_transcript", ext=".txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

        logger.info(f"ElevenLabs transcribe complete: {len(text)} chars, {len(words)} words")

        lang_from_result = getattr(result, "language_code", None)
        return {
            "text": text,
            "language": lang_from_result if isinstance(lang_from_result, str) else language_code,
            "words": words,
            "transcript_path": str(out),
        }


# ---------------------------------------------------------------------------
# 8. Forced Alignment
# ---------------------------------------------------------------------------

class ElevenLabsForcedAlignmentProvider:
    """Align text to audio timestamps using ElevenLabs."""

    def align(
        self,
        audio_path: str,
        text: str,
        language_code: str = "en",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(f"ElevenLabs forced align: input={audio_path} len={len(text)}")

        with open(audio_path, "rb") as f:
            result = client.speech_to_text.convert(
                file=f,
                model_id="scribe_v2",
                language_code=language_code or None,
                timestamps_granularity="word",
            )

        alignment = [
            {"word": w.text, "start": w.start, "end": w.end}
            for w in (result.words or [])
        ]

        logger.info(f"ElevenLabs alignment complete: {len(alignment)} words aligned")

        return {
            "alignment": alignment,
            "text": result.text,
        }


# ---------------------------------------------------------------------------
# 9. AI Dubbing
# ---------------------------------------------------------------------------

class ElevenLabsDubbingProvider:
    """Dub audio into another language using ElevenLabs."""

    def dub(
        self,
        audio_path: str,
        target_language: str,
        source_language: str = "en",
        **_kwargs,
    ) -> dict:
        client, el = _get_client()

        logger.info(
            f"ElevenLabs dub: input={audio_path} "
            f"{source_language} -> {target_language}"
        )

        with open(audio_path, "rb") as f:
            dubbing_response = client.dubbing.create(
                file=f,
                target_lang=target_language,
                source_lang=source_language,
            )

        dubbing_id = dubbing_response.dubbing_id

        # Poll for completion
        import time as _time
        for _ in range(120):  # up to 10 min
            status = client.dubbing.get(dubbing_id=dubbing_id)
            if status.status == "dubbed":
                break
            if status.status == "failed":
                raise RuntimeError(f"Dubbing failed for id={dubbing_id}")
            _time.sleep(5)
        else:
            raise RuntimeError(f"Dubbing timed out for id={dubbing_id}")

        # Download dubbed audio
        audio_iter = client.dubbing.audio.get(
            dubbing_id=dubbing_id,
            language_code=target_language,
        )

        out = _unique_path(Path(config.DUBBING_DIR), f"el_dub_{target_language}")
        _save_audio(audio_iter, out)

        logger.info(f"ElevenLabs dubbing complete: {out.name}")

        return {
            "audio_path": str(out),
            "dubbing_id": dubbing_id,
        }


# ---------------------------------------------------------------------------
# 10. Professional Voice Cloning (PVC)
# ---------------------------------------------------------------------------

class ElevenLabsProfessionalVoiceCloningProvider:
    """
    Professional Voice Cloning — higher fidelity than instant cloning.

    Flow:
      1. create()  — creates the PVC voice slot + uploads audio samples
                     + fires off training.
      2. get_training_status()  — poll until finetuning_state == "fine_tuned"
         or "failed".

    Notes:
      - Requires Creator plan or above.
      - Training typically takes 15–60 minutes.
      - language must be an ISO 639-1 code (e.g. "en", "es", "fr").
      - Recommended audio: 30+ minutes of clean, consistent speech.
    """

    def create(
        self,
        name: str,
        language: str,
        audio_paths: list[str],
        description: str = "",
        remove_background_noise: bool = False,
        **_kwargs,
    ) -> dict:
        """
        Create a PVC voice, upload samples, and kick off training.

        Returns immediately with the voice_id and initial training status.
        Use get_training_status(voice_id) to poll for completion.
        """
        client, el = _get_client()

        logger.info(
            f"ElevenLabs PVC create: name={name!r} lang={language} "
            f"files={len(audio_paths)} remove_bg={remove_background_noise}"
        )

        # Step 1 — create the voice slot
        voice_resp = client.voices.pvc.create(
            name=name,
            language=language,
            description=description or f"Professional clone: {name}",
        )
        voice_id = voice_resp.voice_id
        logger.info(f"ElevenLabs PVC voice slot created: id={voice_id}")

        # Step 2 — upload audio samples
        files = [open(p, "rb") for p in audio_paths]
        try:
            samples = client.voices.pvc.samples.create(
                voice_id=voice_id,
                files=files,
                remove_background_noise=remove_background_noise,
            )
        finally:
            for f in files:
                f.close()

        logger.info(f"ElevenLabs PVC samples uploaded: {len(samples)} sample(s)")

        # Step 3 — start training
        train_resp = client.voices.pvc.train(voice_id=voice_id)
        logger.info(f"ElevenLabs PVC training started: status={train_resp.status!r}")

        return {
            "voice_id": voice_id,
            "name": name,
            "samples_uploaded": len(samples),
            "training_status": train_resp.status,
        }

    def get_training_status(
        self,
        voice_id: str,
        **_kwargs,
    ) -> dict:
        """
        Poll the training state for a PVC voice.

        finetuning_state values: "not_started" | "queued" | "fine_tuning"
                                 | "fine_tuned" | "failed" | "delayed"
        """
        client, el = _get_client()
        voice = client.voices.get(voice_id=voice_id)

        ft = voice.fine_tuning
        state = ft.finetuning_state if ft else "unknown"
        progress = ft.progress if ft else {}
        message = ft.message if ft else ""

        logger.info(f"ElevenLabs PVC status: id={voice_id} state={state!r}")

        return {
            "voice_id": voice_id,
            "name": voice.name,
            "finetuning_state": state,
            "progress": progress,
            "message": message,
            "is_ready": state == "fine_tuned",
            "is_failed": state == "failed",
        }


# ---------------------------------------------------------------------------
# 11. Voice Remixing
# ---------------------------------------------------------------------------

class ElevenLabsVoiceRemixingProvider:
    """
    Voice Remixing — modify an existing voice's attributes (gender, accent,
    age, pacing, tone) by describing the desired changes in natural language.

    Flow:
      1. remix()       — takes an existing voice_id + description of changes,
                         returns one or more audio previews on disk plus their
                         generated_voice_ids.
      2. save_remix()  — persists a chosen preview as a permanent library voice.

    The generated_voice_id from step 1 is ephemeral; call save_remix() within
    the same session to keep it.
    """

    def remix(
        self,
        voice_id: str,
        voice_description: str,
        text: str = "",
        auto_generate_text: bool = True,
        seed: int = -1,
        guidance_scale: float | None = None,
        prompt_strength: float | None = None,
        **_kwargs,
    ) -> dict:
        """
        Generate remixed previews of an existing voice.

        Parameters
        ----------
        voice_id            : Source voice to remix (must be owned by the account).
        voice_description   : Natural-language description of desired changes,
                              e.g. "Make the voice slightly higher-pitched with
                              a British accent and slower pacing."
        text                : Sample text to speak in the preview.
                              Leave empty to auto-generate.
        auto_generate_text  : If True and text is empty, EL picks sample text.
        seed                : Reproducibility seed (-1 = random).
        guidance_scale      : How closely to follow voice_description (0–1).
        prompt_strength     : Blend between original and remixed (0=original,
                              1=full remix).

        Returns
        -------
        dict with:
          previews — list of {audio_path, generated_voice_id, duration_secs}
        """
        client, el = _get_client()

        logger.info(
            f"ElevenLabs voice remix: voice={voice_id!r} "
            f"desc={voice_description!r} auto_text={auto_generate_text}"
        )

        remix_kwargs: dict = dict(
            voice_id=voice_id,
            voice_description=voice_description,
            auto_generate_text=auto_generate_text if not text else False,
        )
        if text:
            remix_kwargs["text"] = text
        if seed >= 0:
            remix_kwargs["seed"] = seed
        if guidance_scale is not None:
            remix_kwargs["guidance_scale"] = guidance_scale
        if prompt_strength is not None:
            remix_kwargs["prompt_strength"] = prompt_strength

        response = client.text_to_voice.remix(**remix_kwargs)

        # Save previews — audio comes back as base64 strings
        out_dir = Path(config.VOCALS_DIR) / "remixes"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)

        previews = []
        for i, preview in enumerate(response.previews or []):
            ext = ".mp3" if "mp3" in (preview.media_type or "mp3") else ".wav"
            out = out_dir / f"el_remix_{ts}_{i}{ext}"
            out.write_bytes(base64.b64decode(preview.audio_base_64))
            previews.append({
                "audio_path": str(out),
                "generated_voice_id": preview.generated_voice_id,
                "duration_secs": preview.duration_secs,
            })
            logger.info(
                f"ElevenLabs remix preview {i}: "
                f"id={preview.generated_voice_id} dur={preview.duration_secs:.1f}s"
            )

        logger.info(f"ElevenLabs voice remix complete: {len(previews)} preview(s)")

        return {
            "previews": previews,
            "sample_text": response.text or "",
        }

    def save_remix(
        self,
        voice_name: str,
        voice_description: str,
        generated_voice_id: str,
        **_kwargs,
    ) -> dict:
        """
        Save a remixed preview as a permanent voice in the library.

        Parameters
        ----------
        voice_name          : Display name for the new voice.
        voice_description   : Description (typically same as passed to remix()).
        generated_voice_id  : The ephemeral ID returned by remix().

        Returns
        -------
        dict with voice_id and name of the saved voice.
        """
        client, el = _get_client()

        logger.info(
            f"ElevenLabs save remix: name={voice_name!r} "
            f"generated_id={generated_voice_id!r}"
        )

        voice = client.text_to_voice.create(
            voice_name=voice_name,
            voice_description=voice_description,
            generated_voice_id=generated_voice_id,
        )

        logger.info(
            f"ElevenLabs remix saved: voice_id={voice.voice_id} name={voice.name}"
        )

        return {
            "voice_id": voice.voice_id,
            "name": voice.name,
        }
