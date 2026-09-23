from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3
import os
import bot_brain  # Importă noul modul
import re  # <--- DIESE ZEILE MUSS HINZUGEFÜGT WERDEN
from citeste_tabel import extrage_comenzi
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from fpdf import FPDF
    has_fpdf = True
except ImportError:
    has_fpdf = False

app = Flask(__name__)
app.secret_key = 'cheie_secreta_super_sigura'

def init_db():
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS stocuri_produse (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cod_bare TEXT UNIQUE,
                        denumire_produs TEXT,
                        soi TEXT,
                        cantitate INTEGER,
                        locatie TEXT,
                        ultima_imbuteliere TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS istoric_scanari (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        angajat TEXT,
                        auftrag TEXT,
                        cod_bare TEXT,
                        denumire_produs TEXT,
                        cantitate INTEGER,
                        data_ora TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS facturi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client TEXT,
                        produs TEXT DEFAULT 'Fără descriere',
                        suma REAL,
                        data TEXT,
                        status TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS plati (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        furnizor TEXT,
                        detalii TEXT DEFAULT 'Fără detalii',
                        suma REAL,
                        data TEXT,
                        status TEXT,
                        cantitate_initiala INTEGER DEFAULT 1,
                        cantitate_ramasa INTEGER DEFAULT 1)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS utilizatori (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        password TEXT,
                        rol TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS acces_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        ip_adresa TEXT,
                        data_ora TEXT)''')

    try: cursor.execute("ALTER TABLE facturi ADD COLUMN produs TEXT DEFAULT 'Fără descriere'")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE plati ADD COLUMN detalii TEXT DEFAULT 'Fără detalii'")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE plati ADD COLUMN cantitate_initiala INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE plati ADD COLUMN cantitate_ramasa INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE stocuri_produse ADD COLUMN cod_bare_carton TEXT")
    except sqlite3.OperationalError: pass

    conn.commit()
    conn.close()

init_db()

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    username = request.form['username']
    password = request.form['password']

    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM utilizatori WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if username == 'admin' and password == 'admin':
        session['user'] = 'admin'
        session['rol'] = 'admin'
        return redirect(url_for('index'))
    elif user and user[2] == password:
        session['user'] = user[1]
        session['rol'] = user[3]
        return redirect(url_for('index'))
    else:
        return "Date de autentificare incorecte! <a href='/'>Înapoi</a>"

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        username = session.get('user')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        timp = datetime.now(ZoneInfo('Europe/Berlin')).strftime("%d.%m.%Y %H:%M:%S")

        conn_log = sqlite3.connect('facturi.db')
        cur_log = conn_log.cursor()
        cur_log.execute("INSERT INTO acces_log (username, ip_adresa, data_ora) VALUES (?, ?, ?)", (username, ip, timp))
        conn_log.commit()
        conn_log.close()
    except Exception as e:
        print("Eroare la salvarea log-ului:", e)

    comenzi_active = []
    toate_achizitiile = []
    total_incasat = 0.0
    total_de_plata = 0.0

    if session.get('rol') == 'admin':
        try:
            conn = sqlite3.connect('facturi.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, client, produs, suma, data, status FROM facturi ORDER BY id DESC")
            facturi = cursor.fetchall()
            cursor.execute("SELECT id, furnizor, detalii, suma, data, status, cantitate_initiala, cantitate_ramasa FROM plati ORDER BY id DESC")
            plati = cursor.fetchall()

            for f in facturi:
                if f[5] == 'vandut':
                    total_incasat += f[3]
                elif f[5] == 'neplatit':
                    comenzi_active.append(f)

            for p in plati:
                if p[5] == 'platit':
                    total_de_plata += p[3]
                toate_achizitiile.append(p)

            conn.close()
        except Exception as e:
            print("Eroare date financiare:", e)

    profit = total_incasat - total_de_plata

    return render_template('index.html', user=session['user'], rol=session.get('rol', 'angajat'),
                           comenzi_active=comenzi_active, toate_achizitiile=toate_achizitiile,
                           total_incasat=round(total_incasat, 2), total_de_plata=round(total_de_plata, 2),
                           profit=round(profit, 2))

@app.route('/genereaza', methods=['GET', 'POST'])
def genereaza():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    if request.method == 'POST':
        client = request.form.get('client')
        produs = request.form.get('produs', 'Fără descriere')
        suma = float(request.form.get('pret', 0))
        data = request.form.get('data_ora', datetime.now(ZoneInfo('Europe/Berlin')).strftime("%Y-%m-%d"))
        status = 'neplatit'

        try:
            conn = sqlite3.connect('facturi.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO facturi (client, produs, suma, data, status) VALUES (?, ?, ?, ?, ?)", (client, produs, suma, data, status))
            factura_id = cursor.lastrowid
            conn.commit()
            conn.close()

            if has_fpdf:
                os.makedirs('facturi', exist_ok=True)
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, txt=f"Rechnung ID: #{factura_id}", ln=True, align='C')
                pdf.cell(200, 10, txt=f"Kunde: {client}", ln=True)
                pdf.cell(200, 10, txt=f"Produkt: {produs}", ln=True)
                pdf.cell(200, 10, txt=f"Betrag: {suma} EUR", ln=True)
                pdf.cell(200, 10, txt=f"Datum: {data}", ln=True)
                pdf.output(f"facturi/rechnung_{factura_id}.pdf")
        except Exception as e:
            return f"Eroare la salvarea în baza de date: {str(e)}"
        return redirect(url_for('index'))
    return render_template('genereaza.html', user=session.get('user', 'admin'))

@app.route('/adauga_plata', methods=['POST'])
def adauga_plata():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    furnizor = request.form.get('furnizor')
    descriere = request.form.get('descriere')
    cantitate = int(request.form.get('cantitate', 1))
    suma = float(request.form.get('suma', 0))
    data_ora = request.form.get('data_ora', datetime.now(ZoneInfo('Europe/Berlin')).strftime("%Y-%m-%d %H:%M"))

    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO plati (furnizor, detalii, suma, data, status, cantitate_initiala, cantitate_ramasa) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                   (furnizor, descriere, suma, data_ora, 'neplatit', cantitate, cantitate))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/marcheaza_vandut/<int:id>')
def marcheaza_vandut(id):
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE facturi SET status = 'vandut' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/marcheaza_platit/<int:id>')
def marcheaza_platit(id):
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE plati SET status = 'platit' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/scade_stoc', methods=['POST'])
def scade_stoc():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    id_plata = request.form.get('id_plata')
    cantitate_consumata = int(request.form.get('cantitate_consumata', 0))

    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE plati SET cantitate_ramasa = MAX(0, cantitate_ramasa - ?) WHERE id = ?", (cantitate_consumata, id_plata))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
def chat():
    if 'user' not in session:
        return jsonify({'raspuns': 'Systemfehler: Sie sind nicht angemeldet.'})

    data = request.json
    mesaj = data.get('mesaj', '')
    utilizator_curent = session['user']

    try:
        conn = sqlite3.connect('facturi.db')
        # Procesează mesajul prin creierul robotului
        raspuns_bot = bot_brain.process_message(mesaj, utilizator_curent, session, conn)
        conn.close()

        return jsonify({'raspuns': raspuns_bot})
    except Exception as e:
        return jsonify({'raspuns': f"System-Absturz! 🤖 Fehler: {str(e)}"})

@app.route('/scanare')
def scanare():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('scanare.html')

@app.route('/api/get_comanda_pdf', methods=['POST'])
def api_get_comanda_pdf():
    if 'user' not in session: return jsonify({'status': 'eroare', 'mesaj': 'Neautentificat'})
    data = request.json or {}
    auftrag = data.get('auftrag', '')

    try:
        try:
            rezultat = extrage_comenzi(auftrag)
        except TypeError:
            rezultat = extrage_comenzi()

        if isinstance(rezultat, dict):
            comanda_gasita = rezultat.get(auftrag, rezultat)
            return jsonify({'status': 'gasit', 'comanda': comanda_gasita})
        else:
            return jsonify({'status': 'nu_exista', 'comanda': {}})
    except Exception as e:
        return jsonify({'status': 'eroare', 'mesaj': str(e)})

@app.route('/gestioneaza_stoc', methods=['GET', 'POST'])
def gestioneaza_stoc():
    if 'user' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()

    if request.method == 'POST' and session.get('rol') == 'admin':
        cod_bare = request.form['cod_bare']
        cod_bare_carton = request.form.get('cod_bare_carton', '')
        denumire = request.form['denumire_produs']
        soi = request.form['soi']
        cantitate = int(request.form['cantitate'])
        locatie = request.form['locatie']
        ultima_imb = request.form['ultima_imbuteliere']

        cursor.execute("SELECT id FROM stocuri_produse WHERE cod_bare = ?", (cod_bare,))
        if cursor.fetchone():
            cursor.execute("UPDATE stocuri_produse SET cod_bare_carton=?, denumire_produs=?, soi=?, cantitate=?, locatie=?, ultima_imbuteliere=? WHERE cod_bare=?",
                           (cod_bare_carton, denumire, soi, cantitate, locatie, ultima_imb, cod_bare))
        else:
            cursor.execute("INSERT INTO stocuri_produse (cod_bare, cod_bare_carton, denumire_produs, soi, cantitate, locatie, ultima_imbuteliere) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (cod_bare, cod_bare_carton, denumire, soi, cantitate, locatie, ultima_imb))
        conn.commit()

    cursor.execute("SELECT id, cod_bare, denumire_produs, cantitate, locatie, ultima_imbuteliere, cod_bare_carton FROM stocuri_produse ORDER BY id DESC")
    produse = cursor.fetchall()
    cursor.execute("SELECT cod_bare, angajat, SUM(cantitate) FROM istoric_scanari GROUP BY cod_bare, angajat")
    istoric = cursor.fetchall()
    vanzari_pe_produs = {}
    for row in istoric:
        cod = row[0]
        angajat = row[1]
        total_vandut = row[2]
        if cod not in vanzari_pe_produs: vanzari_pe_produs[cod] = []
        vanzari_pe_produs[cod].append({'angajat': angajat, 'total': total_vandut})
    conn.close()
    return render_template('gestioneaza_stoc.html', produse=produse, vanzari_pe_produs=vanzari_pe_produs, user=session['user'], rol=session.get('rol'))

@app.route('/api/info_stoc', methods=['POST'])
def api_info_stoc():
    if 'user' not in session: return jsonify({'status': 'eroare'})
    cod_bare = request.json.get('cod_bare')
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT cod_bare, cod_bare_carton, denumire_produs, cantitate, locatie FROM stocuri_produse WHERE cod_bare = ? OR cod_bare_carton = ? ORDER BY id DESC", (cod_bare, cod_bare))
    p = cursor.fetchone()
    conn.close()
    if p: return jsonify({'status': 'gasit', 'cod_bare': p[0], 'cod_bare_carton': p[1], 'denumire': p[2], 'cantitate': p[3], 'locatie': p[4]})
    return jsonify({'status': 'negasit'})

@app.route('/api/update_stoc_rapid', methods=['POST'])
def api_update_stoc_rapid():
    if session.get('rol') != 'admin': return jsonify({'status': 'eroare', 'mesaj': 'Doar adminii pot modifica stocul'})
    data = request.json
    cod_bare = data.get('cod_bare')
    noua_cantitate = int(data.get('cantitate', 0))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE stocuri_produse SET cantitate = ? WHERE cod_bare = ?", (noua_cantitate, cod_bare))
    conn.commit()
    conn.close()
    return jsonify({'status': 'succes'})

@app.route('/api/scaneaza_cod', methods=['POST'])
def api_scaneaza_cod():
    if 'user' not in session: return jsonify({'status': 'eroare', 'mesaj': 'Neautentificat'})
    data = request.json
    cod_bare = data.get('cod_bare')
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT denumire_produs, cantitate, locatie, cod_bare FROM stocuri_produse WHERE cod_bare = ? OR cod_bare_carton = ? ORDER BY id DESC", (cod_bare, cod_bare))
    produs = cursor.fetchone()
    conn.close()
    if produs:
        return jsonify({'status': 'gasit', 'denumire': produs[0], 'cantitate': produs[1], 'locatie': produs[2], 'cod_bare_primar': produs[3]})
    else:
        return jsonify({'status': 'eroare', 'mesaj': 'Produkt mit diesem Barcode nicht im System gefunden.'})

@app.route('/api/vinde_scaneaza', methods=['POST'])
def vinde_scaneaza():
    if 'user' not in session: return jsonify({'status': 'eroare', 'mesaj': 'Nu ești logat'})
    data = request.json
    cod_bare = data.get('cod_bare')
    cantitate = int(data.get('cantitate', 1))
    auftrag = data.get('auftrag', 'Fără comandă')
    angajat = session['user']

    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, cantitate, denumire_produs, cod_bare FROM stocuri_produse WHERE cod_bare = ? OR cod_bare_carton = ? ORDER BY id DESC", (cod_bare, cod_bare))
    produs = cursor.fetchone()

    if produs:
        stoc_curent = produs[1]
        denumire = produs[2]
        cod_bare_primar = produs[3]
        if stoc_curent >= cantitate:
            cursor.execute("UPDATE stocuri_produse SET cantitate = cantitate - ? WHERE cod_bare = ?", (cantitate, cod_bare_primar))
            acum = datetime.now(ZoneInfo('Europe/Berlin')).strftime("%d.%m.%Y %H:%M:%S")
            cursor.execute("INSERT INTO istoric_scanari (angajat, auftrag, cod_bare, denumire_produs, cantitate, data_ora) VALUES (?, ?, ?, ?, ?, ?)", (angajat, auftrag, cod_bare_primar, denumire, cantitate, acum))
            conn.commit()
            conn.close()
            return jsonify({'status': 'succes'})
        else:
            conn.close()
            return jsonify({'status': 'eroare', 'mesaj': 'Nu ai suficient stoc disponibil!'})
    else:
        conn.close()
        return jsonify({'status': 'eroare', 'mesaj': 'Produs negăsit'})

@app.route('/api/anuleaza_scanare', methods=['POST'])
def anuleaza_scanare():
    if 'user' not in session: return jsonify({'status': 'eroare', 'mesaj': 'Nu ești logat'})
    data = request.json
    cod_bare = data.get('cod_bare')
    cantitate = int(data.get('cantitate', 1))
    auftrag = data.get('auftrag')
    angajat = session['user']

    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT cod_bare FROM stocuri_produse WHERE cod_bare = ? OR cod_bare_carton = ? ORDER BY id DESC", (cod_bare, cod_bare))
    p = cursor.fetchone()
    if p:
        cod_bare_primar = p[0]
        cursor.execute("UPDATE stocuri_produse SET cantitate = cantitate + ? WHERE cod_bare = ?", (cantitate, cod_bare_primar))
        cursor.execute("""DELETE FROM istoric_scanari WHERE id = (SELECT id FROM istoric_scanari WHERE angajat = ? AND auftrag = ? AND cod_bare = ? ORDER BY id DESC LIMIT 1)""", (angajat, auftrag, cod_bare_primar))
        conn.commit()
    conn.close()
    return jsonify({'status': 'succes'})

@app.route('/istoric')
def istoric():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT angajat, auftrag, denumire_produs, cantitate, data_ora FROM istoric_scanari ORDER BY id DESC")
    inregistrari = cursor.fetchall()
    conn.close()
    return render_template('istoric.html', inregistrari=inregistrari, user=session.get('user', 'admin'))

@app.route('/verificare')
def verificare():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, ip_adresa, data_ora FROM acces_log ORDER BY id DESC")
    logs = cursor.fetchall()
    conn.close()
    return render_template('verificare.html', logs=logs, user=session.get('user', 'admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/angajati', methods=['GET', 'POST'])
def angajati():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    conn = sqlite3.connect('facturi.db')
    cursor = conn.cursor()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rol = request.form['rol']
        cursor.execute("INSERT INTO utilizatori (username, password, rol) VALUES (?, ?, ?)", (username, password, rol))
        conn.commit()
    cursor.execute("SELECT id, username, rol FROM utilizatori")
    lista_utilizatori = cursor.fetchall()
    cursor.execute("SELECT angajat, auftrag, denumire_produs, SUM(cantitate), MAX(data_ora) FROM istoric_scanari GROUP BY angajat, auftrag, denumire_produs ORDER BY id DESC")
    scanari_raw = cursor.fetchall()
    conn.close()
    activitate_angajati = {}
    for row in scanari_raw:
        angajat = row[0]
        if angajat not in activitate_angajati: activitate_angajati[angajat] = []
        activitate_angajati[angajat].append({'auftrag': row[1], 'produs': row[2], 'cantitate': row[3], 'data': row[4]})
    return render_template('angajati.html', utilizatori=lista_utilizatori, activitate_angajati=activitate_angajati, user=session['user'])

if __name__ == '__main__':
    app.run(debug=True)
