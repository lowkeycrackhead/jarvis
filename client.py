from google import genai
import os
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
chat = client.chats.create(model="gemini-3.6-flash")


def aiprocess(command):
    try:
        response = chat.send_message(command)
        reply = response.text or "I could not generate a response."
        print(reply)
        
    except Exception as error:
        print(f"Gemini error: {error}")


aiprocess('how is the weather today?')