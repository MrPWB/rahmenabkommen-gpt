import os
import re
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.europa.eda.admin.ch/de/vernehmlassung-paket-schweiz-eu"
DOWNLOAD_DIR = "./app/data/pdfs"

def sanitize_filename(name: str) -> str:
    # Erlaubte Zeichen für Dateinamen, alles andere entfernen/ersetzen
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip()
    if len(name) == 0:
        name = "download"
    return name + ".pdf"

def get_download_links_and_titles(page, target_categories=["Abkommen", "Innerstaatliche Umsetzung", "Erläuternder Bericht", "Faktenblätter und FAQ", "Übersicht EU-Gesetzgebungsakte Paket Schweiz-EU"]):
    # Warte, bis die Download-Items geladen sind
    page.wait_for_selector("a.download-item")
    
    # Hole alle h2-Elemente und Download-Items
    elements = page.query_selector_all("h2, ul.accordion a.download-item, div.container__aside a.download-item")
    
    result = []
    current_category = None
    
    for idx, el in enumerate(elements):
        # Prüfe, ob das Element ein h2 ist (Kategorie)
        if el.evaluate("el => el.tagName.toLowerCase() === 'h2'"):
            current_category = el.inner_text().strip()
            continue
        
        # Nur Download-Items aus den Zielkategorien verarbeiten
        if current_category in target_categories:
            href = el.get_attribute("href")
            title_el = el.query_selector("h4.download-item__title")
            
            if title_el:
                title = title_el.inner_text().strip()
                if not title:
                    print(f"Warnung: Leerer Titel bei Link #{idx} in Kategorie '{current_category}' ({href})")
                    title = None
            else:
                print(f"Warnung: Kein Titel-Element bei Link #{idx} in Kategorie '{current_category}' ({href})")
                title = None
            
            # Fallback für Titel, falls keiner vorhanden
            if not title:
                download_attr = el.get_attribute("download")
                if download_attr:
                    title = os.path.splitext(download_attr)[0]
                    print(f"Fallback Titel aus 'download'-Attribut: {title}")
                else:
                    title = f"download_{len(result)}"

                    print(f"Fallback Titel generiert: {title}")
            
            result.append((title, href))
    
    return result
def download_file(url, filename):
    print(f"Downloading {url} as {filename}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    path = os.path.join(DOWNLOAD_DIR, filename)
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        print(f"Fehler beim Download von {url}: {e}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL)

        links_and_titles = get_download_links_and_titles(page)
        print(f"Gefundene Dokumente: {len(links_and_titles)}")

        for title, url in links_and_titles:
            filename = sanitize_filename(title)
            download_file(url, filename)

        browser.close()

if __name__ == "__main__":
    main()
