import json
import os
import re
import requests
from livekit import agents, rtc
from dotenv import load_dotenv

load_dotenv()

# ------------ Load FAQ Data ------------
with open("ola_faq.json", "r") as f:
    FAQ_DATA = json.load(f)

# ------------ Lead JSON Handler ------------
LEAD_FILE = "lead.json"
lead_data = json.load(open(LEAD_FILE, "r"))


def save_lead():
    with open(LEAD_FILE, "w") as f:
        json.dump(lead_data, f, indent=4)


# ------------ Murf AI TTS ------------
def murf_tts_generate(text: str) -> bytes:
    url = "https://api.murf.ai/v1/speech/generate"

    payload = {
        "voice": os.getenv("MURF_VOICE_ID"),
        "text": text,
        "format": "mp3"
    }

    headers = {
        "apikey": os.getenv("MURF_API_KEY"),
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    audio_url = response.json()["audio_url"]
    audio_bytes = requests.get(audio_url).content
    return audio_bytes


# ------------ FAQ Search ------------
def search_faq(query):
    query_lower = query.lower()
    for item in FAQ_DATA["faq"]:
        if any(word in query_lower for word in item["q"].lower().split()):
            return item["a"]
    return None


# ------------ Conversation / SDR Logic ------------
def process_user_text(text):
    global lead_data

    text_low = text.lower()

    # End of call detector
    if any(p in text_low for p in ["that's all", "done", "thank you", "thanks", "bye"]):
        summary = (
            f"Here’s a quick summary!\n"
            f"Name: {lead_data['name']}\n"
            f"Company: {lead_data['company']}\n"
            f"Email: {lead_data['email']}\n"
            f"Role: {lead_data['role']}\n"
            f"Use Case: {lead_data['use_case']}\n"
            f"Team Size: {lead_data['team_size']}\n"
            f"Timeline: {lead_data['timeline']}\n"
            f"Our Ola team will contact you soon!"
        )
        save_lead()
        return summary

    # Collect name
    if lead_data["name"] == "":
        match = re.search(r"my name is (.*)", text_low)
        if match:
            lead_data["name"] = match.group(1).title()
            save_lead()
            return "Nice to meet you! Which company are you representing?"

        return "Hello! I'm Aisha from Ola. May I know your name?"

    # Company
    if lead_data["company"] == "":
        lead_data["company"] = text.strip()
        save_lead()
        return "Great! Could you share your email?"

    # Email
    if lead_data["email"] == "":
        if "@" in text:
            lead_data["email"] = text.strip()
            save_lead()
            return "Perfect! What's your role?"
        return "Please provide a valid email."

    # Role
    if lead_data["role"] == "":
        lead_data["role"] = text.strip()
        save_lead()
        return "Thanks! What do you want to use Ola for?"

    # Use case
    if lead_data["use_case"] == "":
        lead_data["use_case"] = text.strip()
        save_lead()
        return "Got it! What's your team size?"

    # Team Size
    if lead_data["team_size"] == "":
        lead_data["team_size"] = text.strip()
        save_lead()
        return "Great! When do you plan to start? Now, soon, or later?"

    # Timeline
    if lead_data["timeline"] == "":
        lead_data["timeline"] = text.strip().lower()
        save_lead()
        return "Awesome! How else can I help you?"

    # FAQ answering
    faq_answer = search_faq(text)
    if faq_answer:
        return faq_answer

    return "I can check that with the Ola team and get back to you."


# ------------ LiveKit Voice Agent ------------
class OlaSDR(agents.BaseAgent):
    async def on_message(self, msg: rtc.Received):
        if isinstance(msg, rtc.ReceivedAudio):
            text = msg.to_text()
            response_text = process_user_text(text)
            audio_bytes = murf_tts_generate(response_text)
            await self.room.local_participant.publish_audio(bytes=audio_bytes)


async def main():
    agent = OlaSDR()
    await agents.run_app(agent)

if __name__ == "__main__":
    agents.run(main())
