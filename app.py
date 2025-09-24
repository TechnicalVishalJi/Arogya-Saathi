import os
import json
import logging
import tempfile
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
from google.cloud import dialogflow_v2 as dialogflow
from google.oauth2 import service_account
import google.generativeai as genai
from datetime import datetime
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import ast
from google.cloud import speech_v1p1beta1 as speech, texttospeech
import uuid
from translate_utils import detect_language, translate_text

# def detect_language(text):
#     # Dummy implementation, replace with actual translation utility
#     return "en"  # Assume English for simplicity

# def translate_text(text, target="en"):
#     # Dummy implementation, replace with actual translation utility
#     return text  # No translation for simplicity

# ================== CONFIG ==================
load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
detected_lang = "en"  # default language
channel = "WhatsApp"  # default channel
chatFormat = "text"  # text or audio

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DIALOGFLOW_PROJECT_ID = os.getenv("DIALOGFLOW_PROJECT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
translate_credentials = service_account.Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS_TRANSLATE")
)

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "health_kb"
client = QdrantClient(url=QDRANT_URL)
embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

dialogflow_credentials = service_account.Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
)
dialogflow_client = dialogflow.SessionsClient(credentials=dialogflow_credentials)

META_API_URL = f"https://graph.facebook.com/v17.0/{META_PHONE_NUMBER_ID}/messages"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

reminders = {}  # phone -> list of reminders

# ================== ROUTES ==================
@app.route("/", methods=["GET"])
def index():
    return "Arogya Saathi is running"

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Verification token mismatch", 403
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        return "No body", 400

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                for msg in messages:
                    phone = msg.get("from")
                    msg_id = msg.get("id")
                    msg_type = msg.get("type")

                    global chatFormat

                    text = None
                    if msg_type == "text":
                        chatFormat = "text"
                        text = msg["text"].get("body")

                    elif msg_type == "image":
                        chatFormat = "text"
                        text = msg.get("caption") or "Image received"

                    elif msg_type == "audio":
                        chatFormat = "audio"
                        media_id = msg["audio"]["id"]
                        audio_bytes = download_whatsapp_media(media_id)
                        text = transcribe_audio(audio_bytes)

                    else:
                        text = f"Unsupported message type: {msg_type}"

                    # Forward to Dialogflow or Gemini
                    global channel
                    channel = "WhatsApp"
                    response = handle_incoming_message(phone, text)
                    if(response == "Reminders"):
                        send_whatsapp_text(phone, translate_text("Setting Reminder for you...", target=detected_lang), "text")
                    elif(response == "Thinking"):
                        send_whatsapp_text(phone, translate_text("Thinking...", target=detected_lang), "text")
                    else:
                        send_whatsapp_text(phone, response)

    except Exception as e:
        app.logger.exception("Webhook error: %s", e)
        return "Error", 500

    return "EVENT_RECEIVED", 200


# @app.route("/webhookSms", methods=["POST"])
# def webhook_sms():
#     try:
#         # (Optional) Validate Twilio request signature
#         validator = RequestValidator(TWILIO_AUTH_TOKEN)
#         twilio_signature = request.headers.get("X-Twilio-Signature", "")
#         url = request.url
#         params = request.form.to_dict()

#         if not validator.validate(url, params, twilio_signature):
#             app.logger.warning("Invalid Twilio signature")
#             return ("Forbidden", 403)

#         # Extract SMS details
#         from_number = request.form.get("From")
#         body_text = request.form.get("Body", "")
#         message_sid = request.form.get("MessageSid")
#         num_media = int(request.form.get("NumMedia", "0") or "0")

#         media = []
#         if num_media > 0:
#             for i in range(num_media):
#                 media_url = request.form.get(f"MediaUrl{i}")
#                 content_type = request.form.get(f"MediaContentType{i}")
#                 media.append({"url": media_url, "content_type": content_type})

#         # Forward to your bot logic
#         global channel
#         channel = "SMS"
#         response = handle_incoming_message(from_number, body_text)

#         # Reply immediately (blocking) via TwiML
#         resp = MessagingResponse()
#         resp.message(response)
#         return str(resp), 200, {"Content-Type": "application/xml"}

#     except Exception as e:
#         app.logger.exception("WebhookSms error: %s", e)
#         return ("Error", 500)

# ================== DIALOGFLOW ==================
def detect_intent_text(project_id, session_id, text, language_code="en"):
    session_client = dialogflow_client
    session = session_client.session_path(project_id, session_id)
    text_input = dialogflow.types.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.types.QueryInput(text=text_input)
    response = session_client.detect_intent(request={"session": session, "query_input": query_input})
    return response.query_result

def handle_incoming_message(phone, text):
    try:
        # 1) detect language (returns language code like 'hi' or 'en')
        global detected_lang
        detected_lang = detect_language(text)
        app.logger.info("Detected language: %s", detected_lang)

        # 2) translate to English if needed
        if detected_lang != "en":
            text_en = translate_text(text, target="en")
            app.logger.info("Translated to English: %s", text_en)
        else:
            text_en = text

        # 3) Call Dialogflow
        session_id = phone
        result = detect_intent_text(DIALOGFLOW_PROJECT_ID, session_id, text_en, language_code="en")
        intent = result.intent.display_name if result.intent else "Default Fallback Intent"

        # If intent has fulfillment, Dialogflow will call /continue
        if not result.intent.is_fallback and result.fulfillment_text:
            return result.fulfillment_text
        elif intent == "Reminders":
            if chatFormat == "audio":
                return "Reminders"
            return translate_text("Setting Reminder for you...", target=detected_lang)
        else:
            if chatFormat == "audio":
                return "Thinking"
            return translate_text("Thinking...", target=detected_lang)
    except Exception as e:
        app.logger.exception("handle_incoming_message error: %s", e)
        return translate_text("Something went wrong, please try again later.", target=detected_lang)

# ================== CONTINUE (FULFILLMENT) ==================
@app.route("/continue", methods=["POST"])
def continue_webhook():
    req = request.get_json(force=True)
    app.logger.info("Continue webhook payload: %s", json.dumps(req))

    intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "Default Fallback Intent")
    session = req.get("session", "unknown")
    phone = session.split("/")[-1]  # we use phone as session id earlier
    user_text = req.get("queryResult", {}).get("queryText", "")

    reply_text = "Sorry, I could not process that."

    if intent == "Query":
        reply_text = answer_with_gemini(generate_prompt(user_text))
        print("Gemini reply:", reply_text)
    elif intent == "Reminders":
        reply_text = handle_reminder(phone, user_text)
    elif intent == "ShowReminders":
        user_reminders = reminders.get(phone, [])
        if user_reminders:
            lines = [f"{i+1}. {r['task']} at {r['time']}" for i, r in enumerate(user_reminders)]
            reply_text = "Your reminders:\n" + "\n".join(lines)
        else:
            reply_text = "You have no reminders set."
        return jsonify({"fulfillmentText": reply_text})
    else:  # Default Fallback Intent
        reply_text = answer_with_gemini(generate_prompt(user_text))
        print("AI reply:", reply_text)

    send_whatsapp_text(phone, reply_text) if channel=="WhatsApp" else send_sms(phone, reply_text)

    return jsonify({"fulfillmentText": reply_text})

# ================== HELPERS ==================
def generate_prompt(question, top_k=4):
    q_vec = embedder.encode(question).tolist()
    hits = client.search(collection_name=COLLECTION_NAME, query_vector=q_vec, limit=top_k)
    contexts = []
    for h in hits:
        txt = h.payload.get("text")
        src = h.payload.get("source")
        score = h.score
        contexts.append({"text": txt, "source": src, "score": score})
    # Build prompt for Gemini
    prompt = "You are a professional health assistant. Use only the following documents to answer the user's question. If the answer is not in the documents, then search through official and reliable sources and reply for the answer by yourself.\n\n"
    for i, c in enumerate(contexts):
        prompt += f"Document {i+1} (source={c['source']}, score={c['score']}):\n{c['text']}\n\n"
    prompt += f"Question: {question}\nAnswer concisely and clearly."
    return prompt

def answer_with_gemini(prompt: str) -> str:
    instructions = (
        "Instructions: Answer the question clearly and accurately. "
        "Format the reply for WhatsApp chat: use *bold* for key terms, "
        "simple line breaks for lists, and avoid markdown that WhatsApp does not support. "
        "Do NOT include disclaimers, warnings, or 'important notes'. "
        "Say that you cannot tell for medicine prescription or dosage and advise to consult a doctor if user asks about this for some illness. "
        f"Keep the reply focused and conversational. Answer in the language whose code is '{detected_lang}'."
    )
    prompt = instructions + "\n\n" + prompt
    print("Final prompt sent to Gemini:", prompt)
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        app.logger.error("Gemini error: %s", e)
        return translate_text("I had trouble answering that. Please try again.", target=detected_lang)

def handle_reminder(phone: str, text: str) -> str:
    now = datetime.now().isoformat()
    task, date, time = ast.literal_eval(gemini_model.generate_content(f"Today's date and time is: {now} (ISO 8601 format). Below is the task that user wants to set reminder for and provide me reponse as a tuple in the format as ('<task>', '<date>', '<time>'). The date and time should follow ISO 8601 standard: \n\n {text}").text.strip())
    print("Parsed reminder:", task, date, time)
    try:
        reminder_dt = datetime.fromisoformat(f"{date}T{time+'+05:30'}")
    except Exception:
        reminder_dt = datetime.now()  # fallback

    reminders.setdefault(phone, []).append({
        "task": task,
        "time": reminder_dt.strftime("%Y-%m-%d %H:%M")
    })

    print("Current reminders:", reminders)

    return translate_text(
        f"✅ Reminder set for {reminder_dt.strftime('%d %b %Y, %I:%M %p')}: '{task}'.",
        target=detected_lang
    )

def download_whatsapp_media(media_id: str) -> bytes:
    """Download media from WhatsApp using media_id."""
    # Step 1: Get media URL
    url = f"https://graph.facebook.com/v20.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    media_url = resp.json().get("url")

    # Step 2: Download actual file
    resp = requests.get(media_url, headers=headers)
    resp.raise_for_status()
    return resp.content

def transcribe_audio(audio_bytes: bytes) -> str:
    """Convert audio bytes to text using Google Speech-to-Text."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)   # audio_bytes = from WhatsApp
        tmp_path = tmp.name
    # Load audio file (must be wav/mp3/m4a/webm)
    audio_file = genai.upload_file(tmp_path)

    prompt = """
    You are a transcription helper. I have provided you an audio file.
    1. Detect speaker language from these codes ['en', 'hi', 'bn'].
    2. Respond with only the code of the detected language.
    """

    code = gemini_model.generate_content([prompt, audio_file]).text.strip()
    print("Detected language code from audio:", code)

    client = speech.SpeechClient(credentials=translate_credentials)

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,  # WhatsApp voice notes are usually OGG/Opus
        sample_rate_hertz=16000,
        language_code=code+"-IN",  # 👈 change based on user’s language
        alternative_language_codes=["hi-IN", "en-IN", "bn-IN", "ta-IN"]  # add languages you expect
    )

    response = client.recognize(config=config, audio=audio)
    transcript = " ".join([r.alternatives[0].transcript for r in response.results])
    print("Transcription result:", transcript)
    return transcript or "Could not transcribe audio."

def synthesize_speech(text):
    client = texttospeech.TextToSpeechClient(credentials=translate_credentials)
    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code=detected_lang+"-IN",  # change based on detected language
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    filename = f"static/{uuid.uuid4().hex}.mp3"
    with open(filename, "wb") as f:
        f.write(response.audio_content)

    # return a public URL (assuming you serve /static via Flask)
    return f"{os.getenv('SERVER_DOMAIN')}/{filename}"


def send_whatsapp_text(to_phone, message_text, format=None):
    finalFormat = chatFormat if format is None else format
    if finalFormat == "audio":
        audio_url = synthesize_speech(message_text)
        headers = {"Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "audio",
            "audio": {"link": audio_url}
        }
        params = {"access_token": META_ACCESS_TOKEN}
        requests.post(META_API_URL, params=params, headers=headers, json=payload)
    else:
        headers = {"Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": message_text}
        }
        params = {"access_token": META_ACCESS_TOKEN}
        resp = requests.post(META_API_URL, params=params, headers=headers, json=payload)
        return resp
        

def send_sms(to_phone, message_text):
    try:
        return
        # resp = twilio_client.messages.create(
        #     body=message_text,
        #     from_=TWILIO_PHONE_NUMBER,
        #     to=to_phone
        # )
        # app.logger.info("Sent SMS to %s sid=%s", to_phone, resp.sid)
        # return resp
    except Exception as e:
        app.logger.exception("Error sending SMS: %s", e)
        return None

# ================== MAIN ==================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
