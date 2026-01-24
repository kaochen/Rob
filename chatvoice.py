import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
from scipy.io.wavfile import write


def synthesize_and_play(text, save_to_file=False, filename="output.wav"):
    """
    Synthesize text to speech and play it via sounddevice.

    Args:
        text (str): The text to synthesize.
        save_to_file (bool): If True, saves the result to a WAV file.
        filename (str): Name of the output file (if save_to_file=True).
    """
    model = "fr_FR-upmc-medium.onnx"
    voice = PiperVoice.load(model)

    stream = sd.OutputStream(
        samplerate=voice.config.sample_rate,
        channels=1,
        dtype='int16'
    )
    stream.start()
    try:
        # Synthesize the text (returns a generator of AudioChunk)
        audio_generator = voice.synthesize(text)
        # Extract samples from each AudioChunk and concatenate them
        audio_samples = np.concatenate([chunk.audio_int16_array for chunk in audio_generator])
        # Convert to int16 if necessary
        int_data = audio_samples.astype(np.int16)
        stream.write(int_data)
        sd.wait()

        # Save to file if requested
        if save_to_file:
            write(filename, voice.config.sample_rate, int_data)
            print(f"File saved as {filename}")

    except Exception as e:
        print(f"Erreur : {e}")
    finally:
        stream.stop()
        stream.close()

# Example
#synthesize_and_play("Bonjour, ceci est un test de synthèse vocale en français.", save_to_file=True)