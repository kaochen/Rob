import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
from scipy.io.wavfile import write

from pocket_tts import TTSModel
import scipy.io.wavfile

def init_text_to_speech(model="jean"):
    print(_("  Initializing Text-to-Speech with the voice of model '{model}'...").format(model=model))
    try:
        tts = TTSModel.load_model()
        voice_state = tts.get_state_for_audio_prompt(model)
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
