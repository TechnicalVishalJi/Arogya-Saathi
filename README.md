# 🩺 Arogya Saathi

A conversational AI system that brings **accessible healthcare education** to users over WhatsApp with **voice support** for low-literacy populations.  
The system integrates advanced AI models, natural language understanding, and vector search to deliver **preventive care guidance, symptom checks, vaccination reminders, and outbreak alerts**.

---

## 🌟 Key Features
- **Multilingual Conversational AI** → Supports multiple Indian and global languages.
- **WhatsApp Accessibility** → Reach users where they already are.
- **Preventive Healthcare Education** → Provides easy-to-understand health tips.
- **Symptom & First-Aid Guidance** → Quick responses for common health issues.
- **Vaccination Tracker & Reminders** → Keeps users and families on schedule.
- **Real-Time Outbreak Alerts** → Pushes updates during epidemics/pandemics.
- **Voice Support for Low Literacy Users** → Speech-to-Text (STT) and Text-to-Speech (TTS).
- **Vector Database + API Hybrid** → Efficient retrieval with embeddings and contextual AI.

---

## 🛠️ Technology Stack
- **Dialogflow ES** → Intent detection and parameter extraction.
- **Gemini API (Google Generative AI)** → Content generation, reasoning, and summarization.
- **Qdrant Vector Database** → Stores embeddings for semantic search and contextual answers.
- **Sentence Transformer** → Generates embeddings for healthcare knowledge base.
- **Google Cloud STT** → Converts WhatsApp voice notes to text (multilingual).
- **Google Cloud TTS** → Converts AI responses to speech for playback on WhatsApp.
- **WhatsApp Business API** → Communication channel for text, voice, and media.

---

## ⚙️ System Architecture
1. **User Interaction (WhatsApp)**  
   Users send text or voice queries via WhatsApp.
   
2. **Webhook Processing**  
   Incoming messages (text/audio) are received at `/webhook`:
   - Text → Sent directly to **Dialogflow/Gemini**.
   - Audio → Transcribed using **Google STT** before forwarding.

3. **NLP + AI Layer**  
   - **Dialogflow ES** extracts intents and parameters.  
   - **Gemini API** generates context-rich responses.  
   - **Sentence Transformer + Qdrant** provides semantic search for healthcare knowledge.

4. **Response Delivery**  
   - Text responses are sent back via WhatsApp.  
   - Voice responses are synthesized using **Google TTS** for accessibility.

## 📊 Example Use Cases

- User: "Mujhe typhoid ke baare mein batao."

- System: Provides simplified preventive care guidelines in Hindi (text/voice).

- User: "Remind me for polio vaccination on 20th Sept at 5 PM."

- System: Stores reminder and sends notification at the scheduled time.

- User: Sends voice note: "Bukhar ho raha hai, kya karun?"

- System: Transcribes → Detects symptom intent → Suggests first-aid and when to see a doctor.

## 📌 Future Enhancements

- 📈 Advanced medical intent detection using Dialogflow CX.
- 🧠 Personal health profile for personalized recommendations.
- 🌍 Support for more regional languages.
- 🔒 Stronger privacy and compliance with healthcare data standards.
