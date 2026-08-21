# Rob — The  (Raspberry Pi Voice Chatbot)

This is a fork of Bob the sentient : https://github.com/OminousIndustries/Bob


---fleu
Configuring the Rapsberry Pi

https://www.raspberrypi.com/software/
On a linux device install the rpi-imager with :
~~~bash
sudo apt install rpi-imager
~~~
For the OS Selection, choose into "Rapsberry Pi OS (other)" sub-category : "Rapsberry Pi OS Lite (64-bit)

If the preset configuration did not apply on the new system. Connect a Keyboard and a screen to the Rapsberry : 
~~~bash
sudo raspi-config
##check the ip address:
ifconfig
~~~

Many router from your provider come with a web interface, where you can find the address of the new device or assign one use the Mac adress.
Connection with ssh using the user your setup for the rapsberry and its ip address :
~~~bash
ssh user@192.168.x.x
~~~


---

## Step 1 — Audio, Bluetooth & Chatbot Base

### 1) System packages

~~~bash
# Update system packages
sudo apt update
sudo apt full-upgrade

# Core tools, audio stack, BT, and TTS
sudo apt install -y \
  git python3-venv python3-pip \
  python3-gpiozero python3-rpi.gpio \
  pipewire pipewire-pulse wireplumber \
  make build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
  libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev \
  liblzma-dev python3-openssl

# Add user to audio group for device permissions
sudo usermod -aG audio $USER



# Reboot for group membership to take effect
sudo reboot
~~~

> After reboot, log back in and continue.

### 2) Speaker Setup

~~~bash
# List PipeWire nodes; note your speaker's Sink ID
wpctl status

# Set default output (replace <sink-id> with the ID you noted)
wpctl set-default <sink-id>

# Test sound output
pw-play /usr/share/sounds/alsa/Front_Center.wav
~~~

---

### 4) USB microphone setup

~~~bash
# Plug in the USB mic, then list audio Sources
wpctl status

# Note the Source ID for your USB mic (e.g., 66) and set it as default:
wpctl set-default <source-id>

# Quick record test from the default source
pw-record --rate 44100 --channels 1 test.wav
# Speak ~3 seconds, then Ctrl+C

# Play back through default sink (BT speaker)
pw-play test.wav
~~~

---

### 5) Project & Python deps
#### 5.1 Install :
~~~bash
git clone https://github.com/kaochen/Rob
cd Rob
~~~
Create a virtual environnement for installing software with "pip"
~~~bash
python3 -m venv .venv
source .venv/bin/activate
~~~

# Upgrade pip and install packages
~~~bash
pip install --upgrade pip
pip install faster-whisper numpy 
# Optional: thread tuning for Faster-Whisper (shell startup)
echo 'export OMP_NUM_THREADS=4' >> ~/.bashrc
source ~/.bashrc
## source .venv/bin/activate ???
~~~
#### 5.2 Whisper test :
https://github.com/openai/whisper

Record 10 seconds of voice:
~~~bash
#record your voice from your microphone
arecord --format=cd file.wav -d 10

#Send record to whisper using an specific language:
whisper file.wav --model small --language fr --fp16 False
cat file.txt 
Je suis en train de tester, on va voir ce qui se passe.
~~~
---

### 6) Install Ollama & model
https://ollama.com/library/gemma3

~~~sh
# Install Ollama server

# If snap available:
sudo snap install ollama --edge
## else
curl -fsSL https://ollama.com/install.sh | sh

# Enable and start the Ollama daemon
sudo systemctl enable --now ollama

# Download a small, fast model (the gemma3:1b is more accurate but use more RAM...)
ollama pull gemma3:270m

# Check :
ollama run gemma3:270m "How old was Emperor Julius Ceasar when he died ?"
Julius Caesar died on **15 April 44 BC**.

#Better with a larger model:

ollama run gemma3:1b "How old was Emperor Julius Ceasar when he died ?"
Emperor Julius Caesar died at the age of 60. 
He was born in 100 BC and died in 44 BC.

##List the models installed :
ollama list
NAME           ID              SIZE      MODIFIED    
gemma3:1b      8648f39daa8f    815 MB    2 hours ago    
gemma3:270m    e7d36fb2c3b3    291 MB    5 hours ago

##List the running models
ollama ps

#Depending on the RAM left (check with using htop)
ollama stop gemma3:270m 
~~~
https://en.wikipedia.org/wiki/Julius_Caesar

### 7) Generate the audio voice using piper-tts
~~~bash
pip install pocket-tts sounddevice soundfile scipy
~~~
---

### 7) Create & run `chatbot.py`

~~~bash
# Create the chatbot script (paste in the chatbot.py script from the repo)
nano chatbot.py
~~~

Find your mic Source ID via `wpctl status`, then launch:

~~~bash
# Example: MIC_TARGET=66 (replace with your actual Source ID)
MIC_TARGET=66 python3 chatbot.py
~~~

---

## Step 2 — SPI Display (Waveshare) & “Rob” Chat

### 1) Enable SPI & groups, reboot

~~~bash
# Enable SPI in raspi-config:
sudo raspi-config   # Interface Options → SPI → Enable

# Add your user to GPIO/SPI groups
sudo usermod -a -G gpio,spi $USER

# Reboot to apply
sudo reboot
~~~

> After reboot, log back in and continue.

---


## Localization :

Init your language the first time (example for French ):
~~~bash
msginit -l fr -o ./locales/fr/LC_MESSAGES/messages.po -i ./locales/messages.pot
~~~
When a change occured in the code, or you updated the messages.po file
~~~bash
sh ./locales/updateTranslation.sh fr
~~~

If you want to test a specific language :

#### Pour le français :
~~~bash
export LANG=fr_FR.UTF-8
python3 chatbot.py
~~~
#### Para español :
~~~bash
export LANG=es_ES.UTF-8
python3 chatbot.py
~~~