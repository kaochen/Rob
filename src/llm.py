import sys
import os
import ollama

### Setup Localization
import gettext
gettext.install('messages', localedir='locales', names=['gettext'])

def init_llm(model_name="gemma3:1b"):
    print(_("  Checking Ollama..."))
    try:
        ollama.list()
    except Exception:
        print(_("❌ Ollama not running! Start it with: sudo systemctl enable --now ollama"))
        sys.exit(1)



def generate_response(user_input, conversation_history, llm_model="gemma3:1b"):
    print("💭 Thinking...")
    try:
        resp = ollama.chat(
            model=llm_model,
            messages=[*conversation_history,
                                    {"role": "system", "content": "Vous êtes un assistant vocal aidant. Garder les réponses concises (max 2 phrases) sans signes, ni émojis."},
                                    {'role': 'user', 'content': user_input}],
            options={"temperature": 0.7, "num_predict": 60, "top_p": 0.9}
        )
        conversation_history += [
            {'role': 'user', 'content': user_input},
            {'role': 'assistant', 'content': resp["message"]["content"] },
        ]
        # Keep conversation history short, five questions, five answers
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]

        return resp["message"]["content"]
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        response = "I'm sorry, I had trouble processing that."
