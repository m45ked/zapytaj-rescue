import io
import re
import gzip
import sqlite3
import os
import requests
from bs4 import BeautifulSoup
from typing import Set

ARCHIVEBOT_JOB_ID = '673i9jafj0idyemybm1p7up5h'
VIEWER_URL = f'https://archive.fart.website/archivebot/viewer/job/{ARCHIVEBOT_JOB_ID}'
DEFAULT_DB_PATH = './data/archivebot_ids.db'

class ArchiveBotSync:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS archivebot_ids (
                    qid INTEGER PRIMARY KEY
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_cdx (
                    filename TEXT PRIMARY KEY,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def get_known_ids(self) -> Set[int]:
        """Pobiera wszystkie znane ID z lokalnej bazy do szybkiego zbioru (set)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT qid FROM archivebot_ids')
            rows = cursor.fetchall()
            return {r[0] for r in rows}

    def sync(self, limit_files: int = 0) -> int:
        """
        Sprawdza serwer ArchiveBota, pobiera nowe indeksy CDX i dopisuje brakujące ID do bazy.
        Zwraca liczbę nowo dodanych ID pytań.
        """
        print(f"[Dedup] Sprawdzanie indeksów ArchiveBota pod adresem {VIEWER_URL}...")
        try:
            r = requests.get(VIEWER_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"[Dedup] Nie udało się połączyć z viewerem ArchiveBota: {e}")
            return 0

        soup = BeautifulSoup(r.text, 'html.parser')
        cdx_links = []
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if 'zapytaj.onet.pl-inf-20260901' in href and (href.endswith('.warc.gz') or href.endswith('.cdx.gz')):
                if href.endswith('.warc.gz'):
                    cdx_url = href.replace('.warc.gz', '.warc.os.cdx.gz')
                else:
                    cdx_url = href
                if cdx_url not in cdx_links:
                    cdx_links.append(cdx_url)

        if not cdx_links:
            print("[Dedup] Nie znaleziono plików CDX w podglądzie joba.")
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT filename FROM processed_cdx')
            already_processed = {r[0] for r in cursor.fetchall()}

        new_links = [u for u in cdx_links if os.path.basename(u) not in already_processed]
        if not new_links:
            print(f"[Dedup] Wszystkie pliki CDX ({len(cdx_links)}) zostały już wcześniej zindeksowane.")
            return 0

        print(f"[Dedup] Znaleziono {len(new_links)} nowych plików CDX do pobrania.")
        if limit_files > 0:
            new_links = new_links[:limit_files]

        total_new_ids = 0
        qid_regex = re.compile(r'/2,(\d+),')

        for url in new_links:
            fname = os.path.basename(url)
            print(f"[Dedup] Pobieranie indeksu {fname}...")
            try:
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
                if res.status_code != 200:
                    print(f"[Dedup] Błąd HTTP {res.status_code} dla {url}")
                    continue
                
                batch_ids = set()
                with gzip.GzipFile(fileobj=io.BytesIO(res.content)) as gz:
                    for line in gz:
                        line_str = line.decode('utf-8', errors='ignore')
                        if 'pl,onet,zapytaj)/category' in line_str:
                            m = qid_regex.search(line_str)
                            if m:
                                batch_ids.add(int(m.group(1)))

                print(f"[Dedup] Odnaleziono {len(batch_ids)} pytań w {fname}. Zapisywanie do bazy...")
                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany('INSERT OR IGNORE INTO archivebot_ids (qid) VALUES (?)', [(qid,) for qid in batch_ids])
                    conn.execute('INSERT OR REPLACE INTO processed_cdx (filename) VALUES (?)', (fname,))
                    conn.commit()

                total_new_ids += len(batch_ids)

            except Exception as ex:
                print(f"[Dedup] Błąd przetwarzania {url}: {ex}")

        print(f"[Dedup] Zakończono synchronizację ArchiveBota. Dodano {total_new_ids} nowych ID.")
        return total_new_ids

if __name__ == '__main__':
    sync = ArchiveBotSync()
    sync.sync()
    known = sync.get_known_ids()
    print(f"Liczba pytań zabezpieczonych przez ArchiveBot w bazie: {len(known)}")
