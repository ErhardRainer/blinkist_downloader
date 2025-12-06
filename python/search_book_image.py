import requests
import json
import os

# Konfiguration
# Du benötigst einen API Key von der Google Cloud Platform (Custom Search API aktiviert)
# und eine Search Engine ID (CX) von https://cse.google.com/cse/all
# Setze diese entweder hier direkt oder als Umgebungsvariablen.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "DEIN_API_KEY_HIER")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID", "DEINE_SEARCH_ENGINE_ID_HIER")

def search_book_image(query):
    if GOOGLE_API_KEY == "DEIN_API_KEY_HIER" or SEARCH_ENGINE_ID == "DEINE_SEARCH_ENGINE_ID_HIER":
        print("Fehler: Bitte konfiguriere GOOGLE_API_KEY und SEARCH_ENGINE_ID im Skript.")
        return

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "cx": SEARCH_ENGINE_ID,
        "key": GOOGLE_API_KEY,
        "searchType": "image",
        "num": 1,  # Anzahl der Ergebnisse
        "safe": "off"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()

        if "items" in results:
            first_result = results["items"][0]
            image_link = first_result["link"]
            print(f"Bild gefunden für '{query}':")
            print(image_link)
            
            # Optional: Weitere Details ausgeben
            # print(f"Titel: {first_result['title']}")
            # print(f"Kontext: {first_result['image']['contextLink']}")
            return image_link
        else:
            print(f"Keine Bilder gefunden für '{query}'.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Fehler bei der Anfrage: {e}")
        return None

if __name__ == "__main__":
    book_title = "Vera F. Birkenbihl - 115 Ideen für ein besseres Leben"
    search_book_image(book_title)
