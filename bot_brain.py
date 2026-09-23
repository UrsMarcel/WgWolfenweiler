import sqlite3
import re
import os
import json
import urllib.request
import urllib.error
import traceback

# Cheia ta API Groq
GROQ_API_KEY = "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"

MOOD_AVATARS = {
    'NORMAL': '🤖',
    'FRÖHLICH': '🥳🚀',
    'GESTRESST': '⚡💥',
    'SARKASTISCH': '😏☕',
    'SOMMELIER': '🍷🧐',
    'SCHOCKIERT': '😱🔥',
    'VERWIRRT': '😵‍💫❓',
    'LIEBEVOLL': '🥰🦾',
    'PANIK': '🚨🥶',
    'PARTY': '🍻🪩'
}

def normalize(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    return " ".join(text.split())

def ask_ai_bot(user_message, db_facts, mood, utilizator):
    system_prompt = f"""
    Du bist ein sarkastischer, humorvoller und intelligenter Chatbot in einem Weinlager.
    AKTUELLE STIMMUNG: {mood}
    Nutzer: {utilizator}
    Nutze NUR diese Fakten: {db_facts}
    Antworte kurz, lustig und auf Deutsch. Nutze HTML.
    """

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
    
    payload = {
        "model": "openai/gpt-oss-120b", # <-- Aici ai modificat modelul
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.8,
        "max_tokens": 250
    }
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers=headers, 
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=4.0) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data['choices'][0]['message']['content']
            
    except urllib.error.HTTPError as e:
        # Aici citim răspunsul exact de la server (ex: "Model not found")
        error_body = e.read().decode('utf-8')
        error_details = f"HTTP {e.code}:\n{error_body}\n\n{traceback.format_exc()}"
        db_facts_html = str(db_facts).replace('\n', '<br>')
        
        return f"""
        {MOOD_AVATARS.get(mood, '🤖')} <b>(Eroare API Groq)</b><br>
        <hr>
        <b style="color:#ff4444; font-size:14px;">🚨 DETALII EROARE EXACTE:</b><br>
        <pre style="background:#1e1e1e; color:#ff8888; padding:10px; border-radius:5px; font-size:11px; overflow-x:auto; text-align:left;">{error_details}</pre>
        <hr>
        <b>Date extrase din DB:</b><br>{db_facts_html}
        """
        
    except Exception as e:
        # Fallback pentru timeout-uri sau probleme de rețea
        error_details = traceback.format_exc()
        db_facts_html = str(db_facts).replace('\n', '<br>')
        
        return f"""
        {MOOD_AVATARS.get(mood, '🤖')} <b>(Offline Fallback - Conexiune blocată/timeout)</b><br>
        <hr>
        <b style="color:#ff4444; font-size:14px;">🚨 DETALII EROARE:</b><br>
        <pre style="background:#1e1e1e; color:#ff8888; padding:10px; border-radius:5px; font-size:11px; overflow-x:auto; text-align:left;">{error_details}</pre>
        <hr>
        <b>Date extrase din DB:</b><br>{db_facts_html}
        """

def process_message(mesaj_raw, utilizator_curent, session, conn):
    mesaj = mesaj_raw.lower().strip()
    mesaj_norm = normalize(mesaj_raw)
    cursor = conn.cursor()

    if 'bot_mood' not in session:
        session['bot_mood'] = 'NORMAL'

    last_employee = session.get('last_employee', None)

    cursor.execute("SELECT DISTINCT angajat FROM istoric_scanari")
    toti_angajatii = [row[0] for row in cursor.fetchall() if row[0]]
    
    angajat_cautat = None
    for ang in toti_angajatii:
        ang_clean = ang.lower()
        variante = [ang_clean, ang_clean.replace('.', ' '), ang_clean.replace('.', '')]
        if any(v in mesaj_norm for v in variante):
            angajat_cautat = ang
            break

    if not angajat_cautat and any(prefix in mesaj for prefix in ['herr', 'frau', 'aber', 'über', 'was ist mit', 'und']):
        cuvinte = mesaj_norm.split()
        for w in cuvinte:
            for ang in toti_angajatii:
                if len(w) > 2 and w in ang.lower():
                    angajat_cautat = ang
                    break

    db_facts = ""

    if angajat_cautat:
        session['last_employee'] = angajat_cautat
        session.modified = True
        cursor.execute("SELECT SUM(cantitate) FROM istoric_scanari WHERE LOWER(angajat) = LOWER(?)", (angajat_cautat,))
        total_flaschen = cursor.fetchone()[0] or 0
        db_facts = f"Mitarbeiter: {angajat_cautat} | Total: {total_flaschen} Flaschen."
        session['bot_mood'] = 'FRÖHLICH'

    elif 'top' in mesaj:
        cursor.execute("SELECT angajat, SUM(cantitate) as total FROM istoric_scanari GROUP BY angajat ORDER BY total DESC LIMIT 3")
        db_facts = f"Top 3: {cursor.fetchall()}"
        session['bot_mood'] = 'FRÖHLICH'

    elif 'stoc' in mesaj or 'lager' in mesaj:
        cursor.execute("SELECT denumire_produs, cantitate FROM stocuri_produse LIMIT 5")
        db_facts = f"Lagerbestand: {cursor.fetchall()}"
        session['bot_mood'] = 'NORMAL'
    else:
        db_facts = "Smalltalk."

    raspuns_ai = ask_ai_bot(
        user_message=mesaj_raw,
        db_facts=db_facts,
        mood=session['bot_mood'],
        utilizator=utilizator_curent
    )

    return f"<div class='p-3 bg-cyan-100 border border-cyan-200 text-slate-900 rounded-xl my-2 shadow-lg'>{raspuns_ai}</div>"
