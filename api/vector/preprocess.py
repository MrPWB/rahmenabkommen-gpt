import os
import re
import fitz
from pathlib import Path
from bs4 import BeautifulSoup
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from sentence_transformers import SentenceTransformer
from langchain_community.embeddings import SentenceTransformerEmbeddings
from dotenv import load_dotenv

load_dotenv()  # .env laden

BASE_URL = os.getenv("BASE_URL", "https://rahmenabkommen-gpt.ch")  # Fallback-URL
PDF_DIR = "./app/data/pdfs"
HTML_DIR = "../ui/public/contracts"
FAISS_INDEX_PATH = "./app/data/vectorstore_index"

def pdf_to_html(html_title, pdf_path, html_path, out_dir):
    """
    Liest ein PDF mit PyMuPDF, erkennt anhand der font_size Überschriften vs. Fließtext
    und schreibt ein HTML-Dokument mit <h1>, <h2> und <p> Elementen.
    """
    doc = fitz.open(pdf_path)
    html = BeautifulSoup(
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'><title>{html_title}</title>"
        f"<link rel='stylesheet' href='{BASE_URL}/static.css'>"
        "</head><body></body></html>",
        "html.parser"
    )    

    body = html.body
    
    # ID-Counter für Referenzen
    counters = {"h1": 0, "h2": 0, "p": 0}

    for page_num, page in enumerate(doc, start=1):
        # Optional: Kapitel-Header pro Seite
        page_header = html.new_tag("h2")
        counters["h2"] += 1
        if not page_header.get('id'):
            page_header['id'] = f"h{counters['h2']}"
        body.append(page_header)

        # Textblöcke im „dict“-Format
        page_dict = page.get_text("dict")
        for block in page_dict["blocks"]:
            if block["type"] != 0: 
                continue  # nur Text-Blöcke

            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    size = span["size"]
                    # Schwellen für Überschriften (anpassen!)
                    if size >= 16:
                        tag_name = "h1"
                    elif size >= 12:
                        tag_name = "h2"
                    else:
                        tag_name = "p"
                    tag = html.new_tag(tag_name)
                    tag.string = text
                    # ID hinzufügen, wenn nicht vorhanden
                    if not tag.get('id'):
                        counters[tag_name] += 1
                        tag['id'] = f"p{counters[tag_name]}"

                    body.append(tag)

    # Schreibe die Datei
    out_path = os.path.join(out_dir, html_path)
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(str(html))
    print(f"[HTML] {pdf_path} → {out_path}")
    return html

def extract_text_with_mapping(soup):
    text = ""
    mapping = []
    current_pos = 0
    for element in soup.find_all(['span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        element_text = element.get_text()
        start = current_pos
        end = start + len(element_text)
        mapping.append((start, end, element['id']))
        text += element_text + "\n"
        current_pos = end + 1  # +1 für die neue Zeile
    return text, mapping

def get_chunk_positions(text, chunks, overlap=200):
    positions = []
    pos = 0
    for chunk in chunks:
        start = text.find(chunk, pos)
        if start == -1:
            start = text.find(chunk)  # Fallback, falls die Position nicht gefunden wird
        positions.append(start)
        pos = start + len(chunk) - overlap
        if pos < start:
            pos = start
    return positions

def make_html_path(filename):
    # Entferne Verzeichnispfade
    name = os.path.basename(filename)
    # Trenne Namen und Extension
    base, ext = os.path.splitext(name)
    # Grundsätzlich unerlaubte Zeichen entfernen
    base = re.sub(r'[\\/:"*?<>|]+', '', base)
    # Entferne alle Punkte und Kommas im Basisnamen
    base = base.replace('.', '').replace(',', '')
    # Spaces durch Unterstriche ersetzen
    base = re.sub(r'\s+', '_', base)
    # Optional: führende und folgende Unterstriche entfernen
    base = base.strip('_')
    return base + ".html"

def make_html_title(filename: str) -> str:
    name = os.path.basename(filename)
    base, ext = os.path.splitext(name)
    base = re.sub(r'[\\/:"*?<>|]+', '', base)
    base = base.strip('_')
    return base

def build_and_save_vectorstore(pdf_dir, html_dir, output_path):

    pdf_paths = [os.path.join(pdf_dir, f) for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    print(f"PDFs gefunden: {len(pdf_paths)}")
    
    all_chunk_texts = []
    all_metadatas = []
    
    os.makedirs(html_dir, exist_ok=True)
    
    for pdf_path in pdf_paths:
        print(f"\n{'='*50}")
        print(f"Verarbeite PDF: {os.path.basename(pdf_path)}")
        print(f"{'='*50}\n")
        
        # HTML Dateiname und Titel erzeugen
        html_title = make_html_title(pdf_path)
        html_path = make_html_path(pdf_path)

        # PDF in HTML umwandeln
        soup = pdf_to_html(html_title, pdf_path, html_path, html_dir)
        
        # Text extrahieren und Mapping erstellen
        text, mapping = extract_text_with_mapping(soup)
        print(f"Länge des extrahierten Textes: {len(text)} Zeichen")
        
        # Text in Chunks aufteilen
        splitter = CharacterTextSplitter(
            separator="\n",
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = splitter.split_text(text)
        print(f"Anzahl Chunks für dieses PDF: {len(chunks)}")
        
        # Startpositionen der Chunks ermitteln
        positions = get_chunk_positions(text, chunks)
        
        # Metadaten für jeden Chunk erstellen
        for chunk, start_pos in zip(chunks, positions):
            for map_start, map_end, element_id in mapping:
                if map_start <= start_pos < map_end:
                    metadata = {"source": f"{BASE_URL}/contracts/{html_path}#{element_id}"}
                    all_chunk_texts.append(chunk)
                    all_metadatas.append(metadata)
                    break
    
    print(f"\nAnzahl Chunks insgesamt: {len(all_chunk_texts)}")
    
    # Alle Chunks einbetten
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding_model = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    all_embeddings = model.encode(all_chunk_texts, show_progress_bar=True, convert_to_numpy=True)
    
    # Vektorspeicher mit Metadaten erstellen und speichern
    vectorstore = FAISS.from_embeddings(
        list(zip(all_chunk_texts, all_embeddings)),
        embedding_model,
        metadatas=all_metadatas
    )
    vectorstore.save_local(output_path)
    print(f"✅ Vectorstore gespeichert unter: {output_path}")

if __name__ == "__main__":
    build_and_save_vectorstore(PDF_DIR, HTML_DIR, FAISS_INDEX_PATH)