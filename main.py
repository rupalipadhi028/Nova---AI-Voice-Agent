import datetime
import base64
import os
import re
import subprocess
import tempfile
import time
from urllib.parse import quote_plus
import webbrowser

import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
from ollama import chat
import yt_dlp
from ddgs import DDGS


ASSISTANT_NAME = "nova"
MODEL_NAME = "llama3.2"
SAMPLE_RATE = 16000
LISTEN_DURATION = 7
LAST_YOUTUBE_RESULTS = []
LAST_WEB_RESULTS = []
LAST_SEARCH_TYPE = None

def speak(message):
    """Speak every response using the built-in Windows SAPI voice."""
    message = str(message).strip()
    if not message:
        return

    print(f"\nNova: {message}")
    try:
        # EncodedCommand avoids problems if the user says quotes or special characters.
        safe_message = message.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice.Rate = 0; "
            f"$voice.Speak('{safe_message}');"
        )
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded_script],
            check=True,
        )
    except Exception as error:
        print(f"Voice error: {error}")


def listen():
    print("\nListening...")
    temp_filename = None
    try:
        recording = sd.rec(
            int(LISTEN_DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_filename = temp_file.name

        sf.write(temp_filename, recording, SAMPLE_RATE)
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_filename) as source:
            audio = recognizer.record(source)

        command = recognizer.recognize_google(audio).lower()
        print(f"You: {command}")
        return command
    except sr.UnknownValueError:
        speak("I could not understand that. Please try again.")
    except sr.RequestError:
        speak("Sorry, I cannot connect to the speech recognition service.")
    except Exception as error:
        print(f"Microphone error: {error}")
        speak("I had a microphone problem. Please check it and try again.")
    finally:
        if temp_filename and os.path.exists(temp_filename):
            os.remove(temp_filename)
    return ""


def ask_ai(question):
    try:
        print("\nNova is thinking...")
        response = chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Nova, a helpful personal AI voice assistant. "
                        "Keep answers concise because they will be spoken aloud."
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        return response.message.content
    except Exception as error:
        print(f"Ollama error: {error}")
        return "Sorry, I cannot connect to Ollama right now. Please make sure it is running."


def open_application(app, command):
    programs = {
        "chrome": ("Chrome", "start chrome", True),
        "edge": ("Microsoft Edge", "start msedge", True),
        "notepad": ("Notepad", "notepad.exe", False),
        "calculator": ("Calculator", "calc.exe", False),
        "vscode": ("Visual Studio Code", "code", True),
    }
    name, program, use_shell = programs[app]
    speak(f"Sure. I am opening {name} now.")  # Spoken BEFORE the task.
    subprocess.Popen(program, shell=use_shell)


def close_application(app, spoken_name=None):
    processes = {
        "chrome": "chrome.exe", "edge": "msedge.exe", "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe", "vscode": "Code.exe",
    }
    name = spoken_name or app
    speak(f"Sure. I am closing {name} now.")  # Spoken BEFORE the task.
    result = subprocess.run(["taskkill", "/IM", processes[app], "/F"], capture_output=True, text=True)
    speak(f"{name} has been closed." if result.returncode == 0 else f"{name} is not currently open.")


def open_website(name, url):
    speak(f"Sure. I am opening {name} now.")  # Spoken BEFORE the task.
    webbrowser.open(url)


def get_web_results(query):
    """Return up to five normal web links for a search request."""
    try:
        results = DDGS().text(query, max_results=5)
        return [
            {"title": item["title"], "url": item["href"]}
            for item in results
            if item.get("title") and item.get("href")
        ]
    except Exception as error:
        print(f"Web lookup error: {error}")
        return []


def google_search(query):
    global LAST_WEB_RESULTS, LAST_SEARCH_TYPE
    if not query:
        speak("What would you like me to search for?")
        return
    speak(f"Sure. I am searching Google for {query} now.")  # Spoken BEFORE the task.
    LAST_WEB_RESULTS = get_web_results(query)
    LAST_SEARCH_TYPE = "web"
    webbrowser.open("https://www.google.com/search?q=" + query.replace(" ", "+"))
    if LAST_WEB_RESULTS:
        speak("I found some links. Say open that link, or say open link number one, two, three, four, or five.")


def get_youtube_results(query):
    """Return up to five YouTube video titles and URLs for a spoken query."""
    options = {"quiet": True, "extract_flat": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as youtube:
            data = youtube.extract_info(f"ytsearch5:{query}", download=False)
        results = []
        for item in data.get("entries", []):
            video_id = item.get("id")
            if video_id:
                results.append({
                    "title": item.get("title", "YouTube video"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })
        return results
    except Exception as error:
        print(f"YouTube lookup error: {error}")
        return []


def youtube_search(query):
    """Search YouTube and remember the links Nova found."""
    global LAST_YOUTUBE_RESULTS, LAST_SEARCH_TYPE
    if not query:
        speak("What would you like me to search for on YouTube?")
        return
    speak(f"Sure. I am searching YouTube for {query} now.")
    LAST_YOUTUBE_RESULTS = get_youtube_results(query)
    LAST_SEARCH_TYPE = "youtube"
    webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
    if LAST_YOUTUBE_RESULTS:
        speak("I found some results. Say open that link, or say open link number one, two, three, four, or five.")


def open_youtube_result(number=1, autoplay=False):
    """Open one of the results from Nova's latest YouTube search."""
    if not LAST_YOUTUBE_RESULTS:
        speak("I do not have a recent YouTube search. Please search YouTube first.")
        return
    if number < 1 or number > len(LAST_YOUTUBE_RESULTS):
        speak(f"I found only {len(LAST_YOUTUBE_RESULTS)} links. Please choose one of them.")
        return
    result = LAST_YOUTUBE_RESULTS[number - 1]
    speak(f"Sure. I am opening {result['title']} now.")
    suffix = "&autoplay=1" if autoplay else ""
    webbrowser.open(result["url"] + suffix)


def open_web_result(number=1):
    """Open one of the links from Nova's latest regular web search."""
    if not LAST_WEB_RESULTS:
        speak("I do not have a recent web search. Please search for something first.")
        return
    if number < 1 or number > len(LAST_WEB_RESULTS):
        speak(f"I found only {len(LAST_WEB_RESULTS)} links. Please choose one of them.")
        return
    result = LAST_WEB_RESULTS[number - 1]
    speak(f"Sure. I am opening {result['title']} now.")
    webbrowser.open(result["url"])


def play_youtube(query):
    """Find the first YouTube video for the request and open it with autoplay."""
    global LAST_YOUTUBE_RESULTS, LAST_SEARCH_TYPE
    speak(f"Sure. I am finding and playing {query} on YouTube now.")
    LAST_YOUTUBE_RESULTS = get_youtube_results(query)
    LAST_SEARCH_TYPE = "youtube"
    if LAST_YOUTUBE_RESULTS:
        open_youtube_result(1, autoplay=True)
    else:
        speak("I could not choose a video automatically, so I am opening YouTube search results.")
        webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))


def clean_youtube_play_request(request):
    """Keep only the title/topic from natural spoken YouTube requests."""
    request = request.strip()
    request = re.sub(
        r"^(?:the\s+|a\s+)?(?:song|video)(?:\s+(?:called|named|with the name))?\s+",
        "",
        request,
        flags=re.IGNORECASE,
    )
    request = re.sub(r"\s+(?:on|from)\s+youtube$", "", request, flags=re.IGNORECASE)
    return request.strip()


def close_all_browsers():
    """Close Chrome and Edge, including every open tab."""
    speak("Sure. I am closing your web browsers now.")
    closed_any = False
    for process in ("chrome.exe", "msedge.exe"):
        result = subprocess.run(
            ["taskkill", "/IM", process, "/F"], capture_output=True, text=True
        )
        closed_any = closed_any or result.returncode == 0
    if closed_any:
        speak("Your web browsers have been closed.")
    else:
        speak("Chrome and Microsoft Edge are not currently open.")


def requested_link_number(command):
    """Get a requested YouTube link number, defaulting 'that link' to the first."""
    if "that link" in command or "first link" in command:
        return 1
    match = re.search(r"(?:link|number)\s*(\d+)", command)
    if match:
        return int(match.group(1))
    words = {
        "one": 1, "first": 1, "two": 2, "second": 2, "three": 3,
        "third": 3, "four": 4, "fourth": 4, "five": 5, "fifth": 5,
    }
    return next((number for word, number in words.items() if word in command), 1)


def open_last_search_result(command):
    """Open a link from Nova's most recent YouTube or normal web search."""
    number = requested_link_number(command)
    if LAST_SEARCH_TYPE == "youtube":
        open_youtube_result(number)
    elif LAST_SEARCH_TYPE == "web":
        open_web_result(number)
    else:
        speak("Please search for something first, then ask me to open a link.")


def process_command(command):
    command = command.replace(ASSISTANT_NAME, "").strip()

    if re.search(r"\b(hello|hi|hey)\b", command):
        speak("Hello! How can I help you?")
    elif "your name" in command:
        speak("My name is Nova, your personal AI assistant.")
    elif "time" in command:
        speak("The current time is " + datetime.datetime.now().strftime("%I:%M %p"))
    elif "date" in command:
        speak("Today is " + datetime.datetime.now().strftime("%d %B %Y"))
    elif "open chrome" in command:
        open_application("chrome", command)
    elif "close chrome" in command:
        close_application("chrome")
    elif "open edge" in command:
        open_application("edge", command)
    elif "close edge" in command:
        close_application("edge")
    elif "open notepad" in command:
        open_application("notepad", command)
    elif "close notepad" in command:
        close_application("notepad")
    elif "open calculator" in command:
        open_application("calculator", command)
    elif "close calculator" in command:
        close_application("calculator")
    elif any(text in command for text in ("open vs code", "open vscode", "open visual studio code")):
        open_application("vscode", command)
    elif any(text in command for text in ("close vs code", "close vscode", "close visual studio code")):
        close_application("vscode")
    elif "open google" in command:
        open_website("Google", "https://www.google.com")
    elif any(phrase in command for phrase in ("open that link", "open first link", "open second link", "open third link", "open fourth link", "open fifth link", "open link number", "open link 1", "open link 2", "open link 3", "open link 4", "open link 5")):
        open_last_search_result(command)
    elif "open youtube" in command:
        open_website("YouTube", "https://www.youtube.com")
    elif command.startswith("search youtube for "):
        youtube_search(command.split("search youtube for", 1)[1].strip())
    elif command.startswith("search youtube "):
        youtube_search(command.split("search youtube", 1)[1].strip())
    elif command.startswith("play "):
        query = clean_youtube_play_request(command.split("play", 1)[1])
        if query:
            play_youtube(query)
        else:
            speak("What song or video would you like me to play on YouTube?")
    elif "close youtube" in command:
        close_all_browsers()
    elif "open github" in command:
        open_website("GitHub", "https://github.com")
    elif "close browser" in command or "close all tabs" in command or "close google" in command or "close github" in command:
        close_all_browsers()
    elif "search for" in command:
        google_search(command.split("search for", 1)[1].strip())
    elif command.startswith("search "):
        google_search(command.split("search", 1)[1].strip())
    elif any(word in command for word in ("stop", "exit", "quit", "goodbye")):
        speak("Goodbye! I will be here whenever you need me.")
        return False
    else:
        speak("Sure. Let me think about that.")
        speak(ask_ai(command))
    return True


def main():
    speak("Hey! I am Nova. How can I help you?")
    while True:
        command = listen()
        if not command:
            continue
        # Nova now responds to every command; saying "Nova" is optional.
        if not process_command(command):
            break


if __name__ == "__main__":
    main()
