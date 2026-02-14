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
            data, rate, ch = stt.record_fixed_seconds(seconds=3, stop=check_stop(stop_button), mic_target=MIC_TARGET)
            if not data:
                print("❌ No audio captured during test.")
                sys.exit(1)
            out = Path("/tmp/test.wav")
            stt.save_wav(data, out, sample_rate=rate, channels=ch)
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
            audio_data, rate, ch = stt.record_with_vad(timeout_seconds=30, stop=check_stop(stop_button), mic_target=MIC_TARGET)

            if audio_data:
                print("📝 Processing captured audio...")
                stt.save_wav(audio_data, TEMP_WAV, sample_rate=rate, channels=ch)
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
