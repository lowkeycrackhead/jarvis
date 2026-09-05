import speech_recognition as sr
import webbrowser
import musiclibrary
from google import genai
from google.genai import types
import os
from gtts import gTTS
from pygame import mixer
import time

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

def processcommand(c):
    if 'open google' in c.lower():
        webbrowser.open('https://google.com')
    elif 'open facebook' in c.lower():
        webbrowser.open('https://facebook.com')
    elif 'open whatsapp' in c.lower():
        webbrowser.open('https://web.whatsapp.com')
    elif 'open instagram' in c.lower():
        webbrowser.open('https://instagram.com')
    elif 'open youtube' in c.lower():
        webbrowser.open('https://youtube.com')
    elif (c.lower().startswith('play')):
        song=c.lower().replace('play','',1).strip()
        link=musiclibrary.music[song]
        webbrowser.open(link)
    else:
        # let the AI handle the command
        aiprocess(c)


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

                    processcommand(command)



        except Exception as e:
            print('google error; {0}' .format(e))  




   
              
