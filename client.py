from main import generate_ai_reply


def aiprocess(command):
    try:
        reply = generate_ai_reply(command)
        print(reply)
        return reply
    except Exception as error:
        print(f"Gemini error: {error}")
        return None


if __name__ == "__main__":
    aiprocess("how is the weather today?")
