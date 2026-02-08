import sys
import os
from pathlib import Path
from faster_whisper import WhisperModel

### Setup Localization
import gettext
gettext.install('messages', localedir='locales', names=['gettext'])

def init_speak_to_text(model_name="small"):
    print(_("  Loading Whisper..."))
    whisper = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        download_root=str(Path.home() / ".cache" / "whisper")
    )
    print(_("✅ Whisper is up and running!\n"))
    return whisper


def transcribe_audio(whisper_model, audio_path):
    print("🧠 Transcribing...")
    try:
        segments, info = whisper_model.transcribe(
            str(audio_path),
            language="fr",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            )
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip() if text else None
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return None