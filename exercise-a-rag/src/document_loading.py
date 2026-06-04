import pypdf  
from pathlib import Path 

DATA_DIR = Path(__file__).parent.parent / "Data"


def read_pdf(path):
    text = ""
    for page in pypdf.PdfReader(path).pages:  #open pdf and loop through each page
        text += page.extract_text() or ""  
    return text


def load_all_documents():
    docs = []
    for path in DATA_DIR.iterdir():  #loop through every file in the Data/ folder
        if path.suffix.lower() != ".pdf":  #skip anything if not pdf
            continue
        try:
            text = read_pdf(path)  #extract all text from pdf
            if text.strip():  #only add it if theres actual content, not just whitespace
                docs.append({"source": path.name, "text": text})  # store filename & text as a dict
                print(f"  loaded: {path.name}") 
        except Exception as e:
            print(f"  skipping {path.name}: {e}")  #if some error occirs, skip it and move on
    return docs  