import imaplib
import email
import os

try:
    import pypdf
except ImportError:
    print("Biblioteca pypdf nu este instalată. Rulează în consolă: pip3 install pypdf --user")
    exit()

# --- SETĂRI EMAIL ---
EMAIL_ACCOUNT = "xprototype112@gmail.com"
PASSWORD = "Jxuyezyfdcnjphcs"
IMAP_SERVER = "imap.gmail.com"

def descarca_si_citeste_pdf():
    try:
        print(f"Se conectează la serverul {IMAP_SERVER}...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, PASSWORD)

        mail.select("inbox")
        status, mesaje = mail.search(None, 'ALL')
        id_uri = mesaje[0].split()

        if not id_uri:
            print("Nu s-au găsit emailuri în Inbox.")
            return

        pdf_gasite = 0

        # Iterăm prin TOATE emailurile, nu doar prin ultimul
        for id_mesaj in id_uri:
            status, date_mesaj = mail.fetch(id_mesaj, '(RFC822)')

            for response_part in date_mesaj:
                if isinstance(response_part, tuple):
                    mesaj = email.message_from_bytes(response_part[1])
                    
                    # Trecem peste emailurile care nu au atașamente
                    if not mesaj.is_multipart():
                        continue

                    for part in mesaj.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue

                        nume_fisier = part.get_filename()
                        if bool(nume_fisier) and nume_fisier.lower().endswith('.pdf'):
                            calea_salvare = os.path.join(os.getcwd(), nume_fisier)

                            # 1. Salvarea fișierului PDF
                            with open(calea_salvare, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            print(f"\nSucces! Am descărcat PDF-ul: {nume_fisier}")
                            pdf_gasite += 1

                            # 2. Citirea textului din PDF
                            try:
                                with open(calea_salvare, 'rb') as f_pdf:
                                    cititor = pypdf.PdfReader(f_pdf)
                                    text_extras = ""
                                    for pagina in cititor.pages:
                                        text_extras += pagina.extract_text() + "\n"

                                    if text_extras.strip():
                                        print(f"AM REUȘIT extragerea pentru {nume_fisier}. Primele rânduri:")
                                        print("-" * 40)
                                        # Afișăm mai puține caractere (250) ca să nu umplem prea tare consola la multe fișiere
                                        print(text_extras[:250]) 
                                        print("-" * 40)
                                    else:
                                        print(f"Fișierul {nume_fisier} pare să fie scanat (poză).")
                            except Exception as ex:
                                print(f"Eroare la citirea PDF-ului {nume_fisier}: {ex}")

                            # AICI ERA PROBLEMA: am șters comanda 'return' care oprea bucla prematur.

        if pdf_gasite == 0:
            print("Nu s-a găsit niciun atașament PDF în emailurile verificate.")
        else:
            print(f"\nProces finalizat. Am descărcat și citit {pdf_gasite} PDF-uri.")

    except Exception as e:
        print(f"A apărut o eroare generală: {e}")
    finally:
        try:
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    descarca_si_citeste_pdf()