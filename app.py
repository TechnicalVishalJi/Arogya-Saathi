import os
import json
import logging
from flask import Flask, request, jsonify, abort
import requests
from dotenv import load_dotenv
from google.cloud import dialogflow_v2 as dialogflow
# from translate_utils import detect_language, translate_text

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DIALOGFLOW_PROJECT_ID = os.getenv("DIALOGFLOW_PROJECT_ID")

if not (META_ACCESS_TOKEN and META_PHONE_NUMBER_ID and VERIFY_TOKEN and DIALOGFLOW_PROJECT_ID):
    app.logger.warning("One or more environment variables are missing. Check .env file.")

META_API_URL = f"https://graph.facebook.com/v17.0/{META_PHONE_NUMBER_ID}/messages"

@app.route("/", methods=["GET"])
def index():
    return "HealthBot is running"

# Meta webhook verification (GET)
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            app.logger.info("Webhook verified")
            return challenge, 200
        else:
            return "Verification token mismatch", 403
    return "OK", 200

# Meta will POST incoming messages here
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    app.logger.info("Webhook received: %s", json.dumps(body))
    # Basic validation
    if body is None:
        return "No body", 400

    # Parse message(s)
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                for msg in messages:
                    phone = msg.get("from")  # phone id like "919XXXXXXXXX"
                    msg_id = msg.get("id")
                    msg_type = msg.get("type")
                    text = None
                    if msg_type == "text":
                        text = msg["text"].get("body")
                    elif msg_type == "image":
                        # handle images if needed later
                        text = msg.get("caption") or "Image received"
                    else:
                        text = f"Unsupported message type: {msg_type}"

                    # Basic flow: detect language -> translate -> dialogflow -> translate back -> reply
                    # print(f"Message from {phone}: {text} (id: {msg_id})")
                    handle_incoming_message(phone, text, msg_id, contacts)
    except Exception as e:
        app.logger.exception("Error processing webhook: %s", e)
        return "Error", 500

    return "EVENT_RECEIVED", 200

def detect_intent_text(project_id, session_id, text, language_code="en"):
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, session_id)
    text_input = dialogflow.types.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.types.QueryInput(text=text_input)
    response = session_client.detect_intent(request={"session": session, "query_input": query_input})
    return response.query_result.fulfillment_text


def handle_incoming_message(phone, text, msg_id, contacts):
    try:
        # # 1) detect language (returns language code like 'hi' or 'en')
        # detected_lang = detect_language(text)
        # app.logger.info("Detected language: %s", detected_lang)

        # # 2) translate to English if needed
        # if detected_lang != "en":
        #     text_en = translate_text(text, target="en")
        #     app.logger.info("Translated to English: %s", text_en)
        # else:
        #     text_en = text

        # 3) Call Dialogflow
        session_id = phone  # use phone as session id to keep session per user
        # df_response = detect_intent_text(DIALOGFLOW_PROJECT_ID, session_id, text_en, language_code="en")
        df_response = detect_intent_text(DIALOGFLOW_PROJECT_ID, session_id, text, language_code="en")
        reply_text_en = df_response or "Sorry, I couldn't understand that. Please rephrase."

        # 4) Translate reply back to user's language (if not English)
        # if detected_lang != "en":
        #     reply_local = translate_text(reply_text_en, target=detected_lang)
        # else:
        #     reply_local = reply_text_en

        # 5) Send reply via Meta
        send_whatsapp_text(phone, reply_text_en)
    except Exception as e:
        app.logger.exception("handle_incoming_message error: %s", e)
        send_whatsapp_text(phone, "Sorry, something went wrong on our side. Please try again later.")

def send_whatsapp_text(to_phone, message_text):
    headers = {"Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }
    params = {"access_token": META_ACCESS_TOKEN}
    resp = requests.post(META_API_URL, params=params, headers=headers, json=payload)
    app.logger.info("Sent message to %s, status: %s, resp: %s", to_phone, resp.status_code, resp.text)
    return resp

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
