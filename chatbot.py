#!/usr/bin/env python3


import json
from logging import warning
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

import os
import gettext
import locale
from tabulate import tabulate

def setup_translation():
    # 1. Detect the user's locale settings
    lang, _ = locale.getlocale(locale.LC_MESSAGES)  # Exemple : ('fr_FR', 'UTF-8')
    if lang is None:
        # If failed to detect, fallback to environment variable or default to English
        lang = os.getenv('LANG', 'en_US').split('.')[0]
        lang = lang.split('_')[0]

    # 2. Setup gettext translation based on detected language
    localedir = os.path.join(os.path.dirname(__file__), 'locales')
    translation = gettext.translation(
        'messages',  # domain name
        localedir=localedir,
        languages=[lang],
        fallback=True  # Use fallback to avoid errors if translation files are missing
    )
    translation.install()

    return translation

# Optional GPIO stop button
try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("📝 GPIO not available - running without button support")

# ===== Configuration =====
STOP_BUTTON_PIN = 22

WHISPER_MODEL = "small"  # Options: tiny, base, small, medium, large

# Conversation
AUTO_RESTART_DELAY = 1.5

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
        warning = _("Stop button ready on GPIO 22")
        print(f"🔘 {warning}")
        return btn
    except Exception:
        warning = _("WARNING: GPIO pins not accessible")
        print(f"⚠️ {warning}")
        return None

# ===== Helpers =====
def check_stop(stop_button):
    return bool(stop_button and stop_button.is_pressed)

# ===== Main =====
def main():
    setup_translation()  # Initialize localization and get the translation function
    global MIC_TARGET
    args = sys.argv[1:]
    if "--mic-target" in args:
        try:
            MIC_TARGET = args[args.index("--mic-target") + 1]
        except Exception:
            warning = _("Usage: --mic-target <source-id-or-name>")
            print(f"⚠️ {warning}")

    def shutdown_handler(sig, frame):
        warning = _("Received shutdown signal")
        print(f"⚠️ {warning}")
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
    goodbye_words = settings.read_setting("llm.goodbye_words", settings_dict, default_value=["goodbye", "bye", "quit", "exit", "stop", "see you", "farewell"])

    #init text-to-speech
    tts_voice = tts.init_text_to_speech(settings.read_setting("tts.voice", settings_dict, default_value="alba"),settings.read_setting("tts.language", settings_dict, default_value="english"))

    stop_button = init_button()

    #Stored conversation, keep it short for raspberry pi
    conversation_history = []
    fichier_conversation = "conversation.json"

    # Load previous conversation if exists
    if os.path.exists(fichier_conversation):
        with open(fichier_conversation, 'r', encoding='utf-8') as f:
            conversation_history = json.load(f)

    ## Welcome message
    print("\n" + "="*50)
    msg_hello = _("I am ready!")
    print(f"🤖 {msg_hello}")
    tts.synthesize_and_play(msg_hello, voice=tts_voice)
    print("="*50)

    ## Main loop
    while True:
        try:
            if check_stop(stop_button):
                warning = _(" Stop button pressed")
                print(f"\n⏹️ {warning}")
                break
            print("⏳ Waiting for speech...")
            audio_data, rate, ch = stt.record_with_vad(timeout_seconds=30, stop=check_stop(stop_button), mic_target=MIC_TARGET)

            if audio_data:
                ## Transcribe audio to text
                start_time = time.time()
                warning = _(" Stop button pressed")
                print(f"📝 {warning}")
                stt.save_wav(audio_data, TEMP_WAV, sample_rate=rate, channels=ch)
                user_text = stt.transcribe_audio(whisper_model, TEMP_WAV)
                transcribe_time = time.time() - start_time
                print(f"✅ Transcription completed in {transcribe_time:.2f}s: \"{user_text}\"")
                
                ## Check for goodbye words and generate response if not found
                if user_text:
                    warning = _("You said:")
                    print(f"📝 {warning} \"{user_text}\"")
                    matched_word = next((w for w in goodbye_words if w in user_text.lower()), None)
                    if matched_word:
                        print(f"Found goodbye word: {matched_word}")
                        break

                    ## Generate response from LLM and update conversation history
                    reply_start_time = time.time()
                    reply, conversation_history = llm.generate_response(user_text, conversation_history, llm_name)
                    warning = _("Assistant:")
                    reply_time = time.time() - reply_start_time
                    warning += f" (response generated in {reply_time:.2f}s)"
                    print(f"🤖 {warning} \"{reply}\"")
                    ##
                    ##llm.print_conversation_history(conversation_history)

                    ## Synthesize and play the response
                    tts_start_time = time.time()
                    tts.synthesize_and_play(reply, voice=tts_voice)
                    tts_time = time.time() - tts_start_time
                    warning = _("Response played in {tts_time:.2f}s").format(tts_time=tts_time)
                    print(f"🔊 {warning}\n")

                    total_time = time.time() - start_time
                    print("⏱️  Timing breakdown:")
                    print(tabulate([
                        ["Transcription", f"{transcribe_time:.2f}s"],
                        ["LLM Response", f"{reply_time:.2f}s"],
                        ["Text-to-Speech", f"{tts_time:.2f}s"],
                        ["Total", f"{total_time:.2f}s"]
                    ], headers=["Step", "Time"], tablefmt="grid"))

                    ##
                    warning = _("Ready again in {AUTO_RESTART_DELAY} seconds...").format(AUTO_RESTART_DELAY=AUTO_RESTART_DELAY)
                    print(f"⏳ {warning}")
                    time.sleep(AUTO_RESTART_DELAY)

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

    msg_goodbye = _("Goodbye")
    tts.synthesize_and_play(msg_goodbye, voice=tts_voice)
    print(f"\n👋 {msg_goodbye}")
    print("="*50)

if __name__ == "__main__":
    main()
