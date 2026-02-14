import sys
import os
import subprocess
import numpy as np
import wave
import time

from pathlib import Path
from faster_whisper import WhisperModel

### Setup Localization
import gettext
gettext.install('messages', localedir='locales', names=['gettext'])

# Preferred capture settings (we’ll auto-fallback if device refuses)
PREF_SAMPLE_RATE = 16000
PREF_CHANNELS = 1

# VAD settings
FRAME_MS = 30
SILENCE_THRESHOLD = 120   # Base RMS
END_SILENCE_MS = 800
MIN_SPEECH_MS = 300
MAX_RECORDING_MS = 15000


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
    
def _spawn_pw_cat_record(rate, channels, target):
    cmd = [
        "pw-cat", "--record", "-",
        "--format", "s16",
        "--rate", str(rate),
        "--channels", str(channels)
    ]
    if target:
        cmd += ["--target", str(target)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def _select_record_pipeline(target):
    """
    Try a few (rate,channels) combos so we don't crash if the device
    refuses 16k mono. Returns (proc, rate, channels, first_chunk or None, err_text).
    """
    attempts = [
        (PREF_SAMPLE_RATE, PREF_CHANNELS),  # 16k / mono
        (PREF_SAMPLE_RATE, 2),              # 16k / stereo
        (48000, PREF_CHANNELS),             # 48k / mono
        (48000, 2),                         # 48k / stereo
    ]
    for rate, ch in attempts:
        proc = _spawn_pw_cat_record(rate, ch, target)
        bytes_per_sample = 2
        frame_bytes = int(rate * FRAME_MS / 1000) * bytes_per_sample * ch
        chunk = proc.stdout.read(frame_bytes)
        if chunk:
            return proc, rate, ch, chunk, ""
        err = (proc.stderr.read() or b"").decode("utf-8", errors="ignore")
        try:
            proc.terminate(); proc.wait(timeout=0.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if err.strip():
            print(f"   ⚠️  pw-cat refused {rate}Hz/{ch}ch: {err.strip()}")
        else:
            print(f"   ⚠️  pw-cat produced no data at {rate}Hz/{ch}ch, retrying...")
    return None, None, None, None, "No working pw-cat configuration found"

def record_with_vad(timeout_seconds=30, stop=False, mic_target=None):
    """Record audio until silence is detected (VAD). Returns (bytes, rate, channels) or (None, None, None)."""
    print("🎤 Listening... (speak now)")
    mic_target = mic_target or os.getenv("MIC_TARGET")
    if mic_target:
        print(f"   🎯 Using source target: {mic_target}")

    proc, rate, ch, first_chunk, err = _select_record_pipeline(mic_target)
    if not proc:
        print(f"❌ {err}")
        return None, None, None

    bytes_per_sample = 2
    frame_bytes = int(rate * FRAME_MS / 1000) * bytes_per_sample * ch
    audio_buffer = bytearray()

    try:
        # Quick calibration (~300ms)
        noise_samples = []
        if first_chunk:
            s = np.frombuffer(first_chunk, dtype=np.int16).astype(np.float32)
            noise_samples.append(float(np.sqrt(np.mean(s * s))))
        for _ in range(9):
            chunk = proc.stdout.read(frame_bytes)
            if chunk:
                s = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                noise_samples.append(float(np.sqrt(np.mean(s * s))))
        noise_floor = float(np.median(noise_samples)) if noise_samples else 50.0
        threshold = max(SILENCE_THRESHOLD, noise_floor * 1.8)
        print(f"   📏 Noise floor: {noise_floor:.1f}  |  Threshold: {threshold:.1f}")

        is_speaking = False
        silence_ms = 0
        speech_ms = 0
        total_ms = 0
        start = time.time()

        if first_chunk is not None:
            samples = np.frombuffer(first_chunk, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples * samples)))
            level = int(rms / 100)
            print(f"\r  Level: {'▁'*min(level,20):<20} ", end="", flush=True)
            if rms > threshold:
                is_speaking = True
                speech_ms = FRAME_MS
                audio_buffer.extend(first_chunk)

        while True:
            if stop:
                raise KeyboardInterrupt

            if (time.time() - start) > timeout_seconds:
                if not is_speaking:
                    return None, None, None
                break

            chunk = proc.stdout.read(frame_bytes)
            if not chunk:
                err = (proc.stderr.read() or b"").decode("utf-8", errors="ignore").strip()
                if err:
                    print(f"\n❗ pw-cat: {err}")
                break

            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples * samples)))
            level = int(rms / 100)
            print(f"\r  Level: {'▁'*min(level,20):<20} ", end="", flush=True)

            if is_speaking:
                audio_buffer.extend(chunk)
                if rms < threshold:
                    silence_ms += FRAME_MS
                else:
                    silence_ms = 0
                    speech_ms += FRAME_MS

                if silence_ms >= END_SILENCE_MS and speech_ms >= MIN_SPEECH_MS:
                    dur_s = len(audio_buffer) / (rate * bytes_per_sample * ch)
                    print(f"\n  ✓ Recorded {dur_s:.1f}s")
                    break
                elif total_ms >= MAX_RECORDING_MS:
                    print("\n  ✓ Max recording length")
                    break
            else:
                if rms > threshold:
                    is_speaking = True
                    speech_ms = FRAME_MS
                    silence_ms = 0
                    audio_buffer.extend(chunk)
                    print("\n  💬 Speech detected!")

            total_ms += FRAME_MS

    except KeyboardInterrupt:
        print("\n  ⏹️  Recording stopped")
        audio_buffer = None
    finally:
        try:
            proc.terminate(); proc.wait(timeout=0.8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if audio_buffer and len(audio_buffer) > 1000:
        return bytes(audio_buffer), rate, ch
    return None, None, None

def save_wav(audio_data, filepath, sample_rate, channels):
    with wave.open(str(filepath), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)


def record_fixed_seconds(seconds=3, stop=False, mic_target=None):
    print(f"🎙️  Recording ~{seconds}s for test...")
    if mic_target:
        print(f"   🎯 Using source target: {mic_target}")

    proc, rate, ch, first_chunk, err = _select_record_pipeline(mic_target)
    if not proc:
        print(f"❌ {err}")
        return None, None, None

    bytes_per_sample = 2
    frame_bytes = int(rate * FRAME_MS / 1000) * bytes_per_sample * ch
    total_frames = int((seconds * 1000) / FRAME_MS)
    buf = bytearray()
    if first_chunk:
        buf.extend(first_chunk)

    try:
        for _ in range(total_frames - (1 if first_chunk else 0)):
            if stop:
                break
            chunk = proc.stdout.read(frame_bytes)
            if not chunk:
                err = (proc.stderr.read() or b"").decode("utf-8", errors="ignore").strip()
                if err:
                    print(f"❗ pw-cat: {err}")
                break
            buf.extend(chunk)
    finally:
        try:
            proc.terminate(); proc.wait(timeout=0.8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    return (bytes(buf), rate, ch) if buf else (None, None, None)