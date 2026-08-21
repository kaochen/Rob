import os
from xml.parsers.expat import model

import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
from scipy.io.wavfile import write

from pocket_tts import TTSModel
from pocket_tts import TTSModel, export_model_state
import scipy.io.wavfile

def init_text_to_speech(model="jean",lang="french_24l"):
    print(_("  Initializing Text-to-Speech with the voice of model '{model}'...").format(model=model))
    try:
        tts = TTSModel.load_model(language=lang, temp=0.5, lsd_decode_steps=5, eos_threshold=-3.0)
        #if model is a path from an audio file, check if safetensors exists, if not create it
        if(model and model.endswith(".wav")):
            filename = os.path.basename(model)
            voice_state_path = os.path.join("data/voices", filename.replace(".wav", ".safetensors"))
            if not os.path.exists(voice_state_path):
                print(f"⚠️  Voice state file '{voice_state_path}' not found. Exporting from audio prompt...")
                voice_state = tts.get_state_for_audio_prompt(model)
                export_model_state(voice_state, voice_state_path)
                print(f"✅ Voice state exported to '{voice_state_path}'")
            else:
                print(f"✅ Voice state file '{voice_state_path}' already exists. Using it.")
                voice_state = tts.get_state_for_audio_prompt(voice_state_path)
        

        msg = _("Text-to-Speech is up and running!")
        print(f"✅ {msg}\n")
    except Exception as e:
        msg = _("Failed to load TTS model")
        print(f"❌ {msg}: {e}")
        sys.exit(1)
    return tts, voice_state

def synthesize_and_play(text, voice=None):
    """
    Synthesize text to speech and play it via sounddevice.
    """
    voice, voice_state = voice if voice else init_text_to_speech();
    
    stream = sd.OutputStream(
        samplerate=voice.sample_rate,
        channels=1,
        dtype='float32',
    )
    stream.start()
    try:
        # Synthesize the text (returns a generator of AudioChunk)
        voice_message = voice.generate_audio(voice_state, text)
        stream.start()
        stream.write(np.zeros(1024, dtype=np.float32))  # Start with silence to avoid clicks
        stream.write(voice_message)  # Write the generated audio to the stream
        sd.wait()

    except Exception as e:
        msg = _("Error during TTS synthesis")
        print(f"❌ {msg}: {e}")
    finally:
        stream.stop()
        stream.close()
