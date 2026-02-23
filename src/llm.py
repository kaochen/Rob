import sys
import os
import ollama
import subprocess

### Setup Localization
import gettext
gettext.install('messages', localedir='locales', names=['gettext'])


## Function to create a model from a modelfile using the ollama CLI
def create_model_from_modelfile(modelfile_path: str, model_name: str):
    try:
        # Exécuter la commande ollama create
        subprocess.run(
            ["ollama", "create", model_name, "-f", modelfile_path],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Modèle '{model_name}' créé avec succès !")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la création du modèle : {e.stderr}")
        raise

def model_exists(model_name: str) -> bool:
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True
    )
    return model_name in result.stdout



def init_llm():
    print(_("  Checking Ollama..."))
    try:
        ollama.list()
    except Exception:
        msg = _("Ollama not running! Start it with")
        print(f"❌ {msg}: sudo systemctl enable --now ollama")
        sys.exit(1)

    llm_name = "ROBOT_MODEL"
    if not model_exists(llm_name):
        create_model_from_modelfile("Modelfile", llm_name)
    else:
        print(f"The model '{llm_name}' already exists.")
        msg = _("Ollama is up and running!")
        print(f"✅ {msg}\n")
    return llm_name



def generate_response(user_text, conversation_history, llm_model="gemma3:1b"):
    print("💭 Thinking...")
    conversation_history.append({'role': 'user', 'content': user_text})
    try:
        resp = ollama.chat(
            model=llm_model,
            messages=conversation_history
        )
        conversation_history.append({'role': 'assistant', 'content': resp["message"]["content"]})
        return resp["message"]["content"], conversation_history
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        response = _("I'm sorry, I had trouble processing that.")

def print_conversation_history(conversation_history):
    print("\n📜 Conversation History:")
    for msg in conversation_history:
        role = "You" if msg['role'] == 'user' else "Assistant"
        print(f"{role}: {msg['content']}")