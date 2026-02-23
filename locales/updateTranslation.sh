#!/bin/bash

# Ask the user for the language code if no argument is provided
if [ $# -eq 0 ]; then
    read -p "Enter the language code (e.g., 'fr' for French, 'en' for English): " _language
else
    _language=$1
fi

# Check if the language code is provided
if [ -z "$_language" ]; then
    echo "Error: No language code provided."
    exit 1
fi

# Path to the locales directory
LOCALES_DIR="./locales/$_language/LC_MESSAGES"

# Check if the locales directory exists
if [ ! -d "$LOCALES_DIR" ]; then
    echo "Error: Directory $LOCALES_DIR does not exist."
    exit 1
fi

# Move to the locales directory
cd "$LOCALES_DIR" || { echo "Error: Failed to enter directory $LOCALES_DIR"; exit 1; }

echo "################### Update $_language.po ###################"

# Create a list of Python files to scan
touch update.po
find ../../../src -type f -iname "*.py" > list
echo "../../../chatbot.py" >> list

# Extract translatable strings
cat list | xgettext -j --from-code=UTF-8 -f --add-comments=translators: -f list -o update.po || { echo "Error: Failed to extract strings"; exit 1; }
sed -i 's/charset=CHARSET/charset=UTF-8/g' update.po

# Merge with the existing translation file
msgmerge -N "messages.po" update.po > tmp.po || { echo "Error: Failed to merge PO files"; exit 1; }

# Replace the old .po file with the new one
mv tmp.po messages.po || { echo "Error: Failed to update messages.po"; exit 1; }

# Clean up temporary files
rm update.po list

echo
echo "################### Update $_language.mo ###################"

# Generate the .mo file
msgfmt "messages.po" -o "messages.mo" || { echo "Error: Failed to generate messages.mo"; exit 1; }

echo "Translation files updated successfully for language: $_language"
