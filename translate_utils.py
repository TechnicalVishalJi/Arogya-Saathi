from google.cloud import translate
from google.cloud import translate_v2 as translate_v2
from google.cloud import translate as translate_v3
import os
from dotenv import load_dotenv
from google.oauth2 import service_account

# We'll use translate_v2 client for simplicity
from google.cloud import translate_v2 as translate_client

load_dotenv()

translate_credentials = service_account.Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS_TRANSLATE")
)
client = translate_client.Client(credentials=translate_credentials)

def detect_language(text):
    try:
        res = client.detect_language(text)
        lang = res.get("language")
        return lang
    except Exception as e:
        # fallback to english
        return "en"

def translate_text(text, target="en"):
    if text is None:
        return ""
    # if target is already 'en' and text language is en, this will still return the same text
    result = client.translate(text, target_language=target)
    return result.get("translatedText")
