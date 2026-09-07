import speech_recognition as sr
import webbrowser
from google import genai
from google.genai import types
import os
from gtts import gTTS
from pygame import mixer
import time
import pywhatkit
from datetime import datetime
mixer.init()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
chat = client.chats.create(model="gemini-3.6-flash",config=types.GenerateContentConfig(
        system_instruction="""
        You are Jarvis, a concise and helpful voice assistant.
        Address the user as Sir.
        give short and crisp responses, and avoid unnecessary explanations.
        """
    ))
recognizer=sr.Recognizer()
def speak(text):
    filename = "jarvis_response.mp3"

    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(filename)

    mixer.music.load(filename)
    mixer.music.play()

    while mixer.music.get_busy():
        time.sleep(0.1)

    mixer.music.unload()
    os.remove(filename)

def aiprocess(command):
    try:
        response = chat.send_message(command)
        reply = response.text or "I could not generate a response."
        print(reply)
        speak(reply)
    except Exception as error:
        print(f"Gemini error: {error}")
        speak("Sorry, I could not process that request.")


def current_datetime_response(command):
    """Return a spoken response for a time, date, or day request."""
    now = datetime.now()
    command = command.lower()

    if "time" in command and any(word in command for word in ("date", "day", "today")):
        return f"It is {now.strftime('%I:%M %p')}, {now.strftime('%A, %B %d, %Y')}, Sir."
    if "time" in command:
        return f"It is {now.strftime('%I:%M %p')}, Sir."
    if "day" in command:
        return f"Today is {now.strftime('%A')}, Sir."
    return f"Today is {now.strftime('%A, %B %d, %Y')}, Sir."


def processcommand(c):
    command = c.lower()

    if command.strip() in {"stop", "exit", "quit"}:
        speak("Shutting down, Sir.")
        return True

    elif any(word in command for word in ("time", "date", "day", "today")):
        speak(current_datetime_response(command))


    elif any(word in command for word in ("time", "date", "day", "today")):
        speak(current_datetime_response(command))

    elif 'open google' in command:
        webbrowser.open('https://google.com')
    elif 'open facebook' in command:
        webbrowser.open('https://facebook.com')
    elif 'open whatsapp' in command:
        webbrowser.open('https://web.whatsapp.com')
    elif 'open instagram' in command:
        webbrowser.open('https://instagram.com')
    elif 'open twitter' in command:
        webbrowser.open('https://twitter.com')
    elif 'open gmail' in command:
        webbrowser.open('https://mail.google.com')
    elif 'open github' in command:
        webbrowser.open('https://github.com')
    elif 'open reddit' in command:
        webbrowser.open('https://reddit.com')
    elif 'open youtube' in command:
        webbrowser.open('https://youtube.com')
    elif command.startswith('play'):
        song = command.replace('play', '', 1).strip()

        if song:
            speak(f"Playing {song}, Sir.")
            pywhatkit.playonyt(song)
        else:
            speak("Please tell me the song name, Sir.")
    else:
                # let the AI handle the command

        aiprocess(c)

    return False


if __name__ == '__main__':
    speak('initializing jarvis....')
    while True:
        #listen for the wake word 'jarvis'
        #obtain audio from the microphone
        r=sr.Recognizer()

        #recognize speech using google
        print('recognizing')
        try:
            with sr.Microphone() as source:
               print('listening...')
               audio= r.listen( source,timeout=2,phrase_time_limit=2)
            word=r.recognize_google(audio)
            print(repr(word))
            if('jarvis' in word.lower()):
                speak('yes sir')
                #listen for command
                with sr.Microphone() as source:
                    print('jarvis active')
                    audio=r.listen(source)
                    command=r.recognize_google(audio)
                    if 'thank you' in command.lower() or 'thanks' in command.lower():
                        speak('you are welcome, sir.')
                        break

                    if processcommand(command):
                        break



        except Exception as e:
            print('google error; {0}' .format(e))  




   
              
