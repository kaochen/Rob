import os
from xml.parsers.expat import model

import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
from scipy.io.wavfile import write

from pocket_tts import TTSModel
from pocket_tts import TTSModel, export_model_state
import scipy.io.wavfile
import torch


def init_text_to_speech(model="jean",lang="french_24l"):
    print(_("  Initializing Text-to-Speech with the voice of model '{model}'...").format(model=model))
    try:
        tts = TTSModel.load_model(language=lang, temp=0.5, lsd_decode_steps=5, eos_threshold=-3.0)

        cuda_available = torch.cuda.is_available()
        if not cuda_available:
            msg = _("CUDA is not available. TTS synthesis may be slow.")
            torch.set_num_threads(1)
            print(f"⚠️ {msg}")
        else:
            tts.to("cuda")
            msg = _("CUDA is available. TTS synthesis should be faster.")
            print(f"✅ {msg}")                

        
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
    """Synthesize text to speech and play it via sounddevice."""
    voice, voice_state = voice if voice else init_text_to_speech()
    stream = sd.OutputStream(
        samplerate=voice.sample_rate,
        channels=1,
        dtype="float32",
    )
    stream.start()

    # Ensure the text ends with a punctuation mark for better TTS output
    if not text.endswith((".", "!", "?")):
        text += "."

    try:
        # Synthesize the text
        voice_message = voice.generate_audio(voice_state, text)

        # 1. Change the way we handle the audio data based on its type (generator or single block)
        # 2. Add a small initial silence to prevent clicks at the start of playback
        if hasattr(voice_message, "__iter__") and not isinstance(
            voice_message, (np.ndarray, torch.Tensor)
        ):
            # If voice_message is a generator, iterate through it
            stream.write(
                np.zeros(1024, dtype=np.float32)
            )  # Silence initial anti-clic
            for chunk in voice_message:
                audio_data = _to_numpy(chunk)
                stream.write(audio_data)
        else:
            # If voice_message is a single block
            audio_data = _to_numpy(voice_message)
            stream.write(
                np.zeros(1024, dtype=np.float32)
            )  # Silence initial anti-clic
            stream.write(audio_data)

    except Exception as e:
        msg = _("Error during TTS synthesis")
        print(f"❌ {msg}: {e}")
    finally:
        stream.stop()
        stream.close()


def _to_numpy(audio):
    # Convert audio data to a contiguous NumPy array of type float32.
    if isinstance(audio, np.ndarray):
        # If it's already a NumPy array, ensure it's float32 and contiguous
        audio = np.asarray(audio, dtype=np.float32)

    if isinstance(audio, torch.Tensor):
        # if it's a PyTorch tensor, detach it from the computation graph, move it to CPU, and convert to NumPy
        audio = audio.detach().cpu().numpy()

    audio = np.asarray(audio, dtype=np.float32)

    # Ensure the array is contiguous in memory for efficient processing
    if not audio.flags["C_CONTIGUOUS"]:
        audio = np.ascontiguousarray(audio)
    return audio