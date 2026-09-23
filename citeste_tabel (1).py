import os
import glob

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

def extrage_comenzi(auftrag=None):
    director_principal = "/home/ursmarcel/"
    director_mysite = "/home/ursmarcel/mysite/"

    # Caută toate PDF-urile din contul tău
    fisiere_pdf = (glob.glob(director_principal + "*.pdf") + glob.glob(director_principal + "*.PDF") + 
                   glob.glob(director_mysite + "*.pdf") + glob.glob(director_mysite + "*.PDF"))

    if not fisiere_pdf:
        return {"LIPSA_PDF": {'nume': 'Eroare: Niciun PDF găsit în sistem!', 'cantitate': 0, 'ean': '0'}}

    if pdfplumber is None:
        return {"LIPSA_LIBRARIE": {'nume': 'Eroare: pdfplumber nu este instalat!', 'cantitate': 0, 'ean': '0'}}

    pdf_de_procesat = None

    # Aici este magia: Căutăm DOAR PDF-ul care are numărul comenzii în nume
    if auftrag:
        numar_comanda = ''.join(filter(str.isdigit, str(auftrag)))
        if numar_comanda:
            for fisier in fisiere_pdf:
                # Verifică dacă numărul există în numele fișierului (ex: 22974 în A22974.pdf)
                if numar_comanda in os.path.basename(fisier):
                    pdf_de_procesat = fisier
                    break
        
        # Dacă a căutat și nu a găsit niciun fișier care să conțină numărul, se oprește!
        if not pdf_de_procesat:
            return {"LIPSA_PDF_COMANDA": {'nume': f'Achtung: Kein PDF für Auftrag {auftrag} gefunden!', 'cantitate': 0, 'ean': '0'}}
    else:
        # Fallback dacă nu se trimite niciun număr
        pdf_de_procesat = max(fisiere_pdf, key=os.path.getctime)

    lista_cantitati = []
    lista_eans = []

    try:
        with pdfplumber.open(pdf_de_procesat) as pdf:
            for pagina in pdf.pages:
                words = pagina.extract_words()
                if not words:
                    continue
                
                words.sort(key=lambda w: (round(w['top'] / 4) * 4, w['x0']))
                
                linii = []
                linie_curenta = []
                top_curent = None
                
                for w in words:
                    if top_curent is None or abs(w['top'] - top_curent) < 4.5:
                        linie_curenta.append(w['text'])
                        if top_curent is None: 
                            top_curent = w['top']
                    else:
                        linii.append(" ".join(linie_curenta))
                        linie_curenta = [w['text']]
                        top_curent = w['top']
                if linie_curenta:
                    linii.append(" ".join(linie_curenta))

                linie_anterioara = ""
                for linie in linii:
                    if "ltr." in linie:
                        elemente = linie.split()
                        if elemente[-1].isdigit():
                            volum_extras = ""
                            try:
                                idx = elemente.index("ltr.")
                                if idx > 0:
                                    volum_extras = elemente[idx-1] + " ltr."
                            except ValueError:
                                pass
                            
                            cartoane_extras = ""
                            for i, el in enumerate(elemente):
                                if "LT6" in el or "BO6" in el:
                                    if i > 0 and elemente[i-1].isdigit():
                                        cartoane_extras = f"{elemente[i-1]} {el}"
                                    else:
                                        cartoane_extras = el
                                    break
                            
                            lista_cantitati.append({
                                'cant': int(elemente[-1]),
                                'rabatt': "Naturalrabatt" in linie,
                                'volum': volum_extras,
                                'cartoane': cartoane_extras
                            })
                    
                    if "EAN" in linie and ("Flasche" in linie or "Verpackung" in linie):
                        ean = ''.join(filter(str.isdigit, linie.split(":")[-1])) if ":" in linie else ''.join(filter(str.isdigit, linie.split()[-1]))
                        nume = linie.split("EAN")[0].replace("WG Wolfenweiler - Der mit dem Wolf", "").replace("(bitte senkrecht setzen!!!)", "").strip()
                        if len(nume) < 5:
                            nume = linie_anterioara.replace("WG Wolfenweiler - Der mit dem Wolf", "").replace("(bitte senkrecht setzen!!!)", "").strip()
                        if not nume: 
                            nume = "Vin Necunoscut"

                        if len(ean) >= 12:
                            lista_eans.append({'ean': ean, 'nume': nume})
                            
                    linie_anterioara = linie

    except Exception as e:
        return {"EROARE_CITIRE": {'nume': f'Eroare la procesare: {str(e)}', 'cantitate': 0, 'ean': '0'}}

    produse_comandate = {}
    
    for i in range(min(len(lista_eans), len(lista_cantitati))):
        ean = lista_eans[i]['ean']
        cant = lista_cantitati[i]['cant']
        nume = lista_eans[i]['nume']
        is_rabatt = lista_cantitati[i]['rabatt']
        volum = lista_cantitati[i]['volum']
        cartoane_pdf = lista_cantitati[i]['cartoane']
        
        if is_rabatt:
            nume = "🎁 " + nume + " (Naturalrabatt)"
            
        detalii_extra = []
        if volum:
            detalii_extra.append(f"📦 {volum}")
        if cartoane_pdf:
            detalii_extra.append(f"🛒 {cartoane_pdf}")
            
        if detalii_extra:
            nume = f"{nume}  |  {'  |  '.join(detalii_extra)}"
            
        cheie = f"{ean}_{i}"
        produse_comandate[cheie] = {
            'ean': ean,
            'nume': nume,
            'cantitate': cant
        }

    return produse_comandate