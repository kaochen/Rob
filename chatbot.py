#!/usr/bin/env python3


import json
import sys
import os
import signal
import time
import subprocess
import wave
import numpy as np
from pathlib import Path

import src.settings as settings
import src.speech_to_text as stt
import src.text_to_speech as tts
import src.llm as llm

### Setup Localization
import gettext
gettext.install('messages', localedir='locales', names=['gettext'])


# Optional GPIO stop button
try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("📝 GPIO not available - running without button support")

# ===== Configuration =====
STOP_BUTTON_PIN = 22

# Preferred capture settings (we’ll auto-fallback if device refuses)
PREF_SAMPLE_RATE = 16000
PREF_CHANNELS = 1

# VAD settings
FRAME_MS = 30
SILENCE_THRESHOLD = 120   # Base RMS
END_SILENCE_MS = 800
MIN_SPEECH_MS = 300
MAX_RECORDING_MS = 15000

# Models
WHISPER_MODEL = "small"
LLM_MODEL = "gemma3:1b"
TTS_VOICE = "ff_siwis"
TTS_SPEED = 1.1

# Conversation
AUTO_RESTART_DELAY = 1.5
WAKE_WORDS = ["hey computer", "okay computer", "hey assistant"]

# Temp file
TEMP_WAV = Path("/tmp/recording.wav")

# Optional: force a specific PipeWire source (id or name)
MIC_TARGET = os.environ.get("MIC_TARGET")

# ===== Init =====

def init_button():
    if not GPIO_AVAILABLE:
        return None
    try:
        btn = Button(STOP_BUTTON_PIN, pull_up=True, bounce_time=0.1)
        print(_("🔘 Stop button ready on GPIO 22"))
        return btn
    except Exception:
        print(_("⚠️  GPIO pins not accessible"))
        return None

# ===== Helpers =====
def check_stop(stop_button):
    return bool(stop_button and stop_button.is_pressed)

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

def record_with_vad(timeout_seconds=30, stop_button=None):
    """Record audio until silence is detected (VAD). Returns (bytes, rate, channels) or (None, None, None)."""
    print("🎤 Listening... (speak now)")
    if MIC_TARGET:
        print(f"   🎯 Using source target: {MIC_TARGET}")

    proc, rate, ch, first_chunk, err = _select_record_pipeline(MIC_TARGET)
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
            if check_stop(stop_button):
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


def record_fixed_seconds(seconds=3, stop_button=None):
    print(f"🎙️  Recording ~{seconds}s for test...")
    if MIC_TARGET:
        print(f"   🎯 Using source target: {MIC_TARGET}")

    proc, rate, ch, first_chunk, err = _select_record_pipeline(MIC_TARGET)
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
            if check_stop(stop_button):
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

# ===== Main =====
def main():
    global MIC_TARGET
    args = sys.argv[1:]
    if "--mic-target" in args:
        try:
            MIC_TARGET = args[args.index("--mic-target") + 1]
        except Exception:
            print("⚠️  Usage: --mic-target <source-id-or-name>")

    def shutdown_handler(sig, frame):
        print("\n\n👋 Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    if len(args) > 0:
        if args[0] == "--help":
            print("Voice Chatbot - USB Mic + USB Speaker")
            print("\nUsage: python3 chatbot.py [--mic-target <id-or-name>] [--test]")
            print("  --mic-target   Force a specific PipeWire source (from `wpctl status`)")
            print("  --test         Record ~3s and play back (quick audio sanity check)")
            sys.exit(0)
        elif args[0] == "--test" or "--test" in args:
            stop_button = init_button()
            data, rate, ch = record_fixed_seconds(seconds=3, stop_button=stop_button)
            if not data:
                print("❌ No audio captured during test.")
                sys.exit(1)
            out = Path("/tmp/test.wav")
            save_wav(data, out, sample_rate=rate, channels=ch)
            print("▶️  Playing back test recording...")
            subprocess.run(["aplay", str(out)], check=False)
            print("✅ Audio test complete!")
            sys.exit(0)

    #read settings
    settings_dict = settings.load_settings()
    #init models
    llm_name = llm.init_llm()
   
    #init speech-to-text
    stt_model = settings.read_setting("stt.model", settings_dict, default_value=WHISPER_MODEL)
    whisper_model = stt.init_speak_to_text(stt_model)
    print(f"✅ Loaded settings: Whisper={stt_model}")

    #init text-to-speech
    tts_voice = tts.init_text_to_speech()

    stop_button = init_button()

    print("\n" + "="*50)
    print("🤖 VOICE CHATBOT READY!")
    print("="*50)
    print("Setup:")
    print("  • Microphone: USB (PipeWire default source)")
    print("  • Speaker: USB (PipeWire default sink)")
    print(f"  • Stop: {'GPIO 22 button or Ctrl+C' if stop_button else 'Press Ctrl+C'}")
    if MIC_TARGET:
        print(f"  • Mic target override: {MIC_TARGET}")
    print("\nListening for speech...\n")

    #Stored conversation, keep it short for raspberry pi
    conversation_history = []
    fichier_conversation = "conversation.json"

    # Load previous conversation if exists
    if os.path.exists(fichier_conversation):
        with open(fichier_conversation, 'r', encoding='utf-8') as f:
            conversation_history = json.load(f)

    while True:
        try:
            if check_stop(stop_button):
                print("\n⏹️  Stop button pressed")
                break
            print("⏳ Waiting for speech...")
            audio_data, rate, ch = record_with_vad(timeout_seconds=30, stop_button=stop_button)

            if audio_data:
                print("📝 Processing captured audio...")
                save_wav(audio_data, TEMP_WAV, sample_rate=rate, channels=ch)
                user_text = stt.transcribe_audio(whisper_model, TEMP_WAV)

                if user_text:
                    print(f"📝 You said: \"{user_text}\"")
                    goodbye_words = ["goodbye", "bye", "stop", "exit", "quit", "shut down", "turn off"]
                    matched_word = next((w for w in goodbye_words if w in user_text.lower()), None)
                    if matched_word:
                        print(f"Found goodbye word: {matched_word}")
                        tts.synthesize_and_play("Goodbye!", voice=tts_voice)
                        break

                    ## Generate response from LLM and update conversation history
                    reply, conversation_history = llm.generate_response(user_text, conversation_history, llm_name)

                    print(f"🤖 Assistant: \"{reply}\"\n")
                    llm.print_conversation_history(conversation_history)
                    tts.synthesize_and_play(reply, voice=tts_voice)

                    print(f"⏳ Ready again in {AUTO_RESTART_DELAY}s...")
                    time.sleep(AUTO_RESTART_DELAY)
                    print("🎤 Listening...\n")
                else:
                    print("❓ No speech detected in the captured audio\n")
            else:
                print("💤 No speech detected, still listening...\n")
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\n⌨️  Interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Restarting in 3 seconds...\n")
            time.sleep(3)

    # Backup conversation history on exit
    with open(fichier_conversation, 'w', encoding='utf-8') as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=4)
        print(f"💾 Conversation history saved to {fichier_conversation}")

    print("\n👋 Goodbye!")
    print("="*50)

if __name__ == "__main__":
    main()
