import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
import tempfile
import os

SAMPLE_RATE = 16000
DURATION = 5

print("🎤 Say something...")

temp_filename = None

try:
    print("🎤 Listening for 5 seconds...")

    recording = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32"
    )

    sd.wait()

    print("✅ Recording finished.")

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".wav"
    ) as temp_file:
        temp_filename = temp_file.name

    sf.write(
        temp_filename,
        recording,
        SAMPLE_RATE
    )

    print("🔄 Converting speech to text...")

    recognizer = sr.Recognizer()

    with sr.AudioFile(temp_filename) as source:
        audio = recognizer.record(source)

    text = recognizer.recognize_google(audio)

    print("✅ You said:", text)

except sr.UnknownValueError:
    print("❌ I couldn't understand your voice.")

except sr.RequestError as e:
    print("❌ Speech recognition error:", e)

except Exception as e:
    print("❌ Error:", e)

finally:
    if temp_filename and os.path.exists(temp_filename):
        os.remove(temp_filename)