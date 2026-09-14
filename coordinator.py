import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
from config import settings
from coordinator_db import CoordinatorDB

db = CoordinatorDB(db_path=os.path.join(settings.DATA_DIR, "coordinator.db"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_chunks(max_qid=settings.MAX_QID, min_qid=settings.MIN_QID, chunk_size=settings.CHUNK_SIZE)
    yield

app = FastAPI(title="Zapytaj Onet Rescue Coordinator", version="1.0.0", lifespan=lifespan)

class ClaimRequest(BaseModel):
    volunteer: str

class HeartbeatRequest(BaseModel):
    chunk_id: int
    volunteer: str

class CompleteRequest(BaseModel):
    chunk_id: int
    volunteer: str
    items_saved: int
    items_404: int
    warc_filename: Optional[str] = ""
    warc_size: Optional[int] = 0
    checksum: Optional[str] = ""

@app.post("/api/chunk/claim")
def claim_chunk(req: ClaimRequest):
    volunteer = req.volunteer.strip() or "anonymous"
    chunk = db.claim_chunk(volunteer=volunteer, lease_timeout_seconds=settings.LEASE_TIMEOUT_MINUTES * 60)
    if not chunk:
        return JSONResponse(content={"status": "ALL_DONE", "message": "Wszystkie paczki zostały już rozdane lub ukończone!"})
    return {"status": "OK", "chunk": chunk}

@app.post("/api/chunk/heartbeat")
def heartbeat(req: HeartbeatRequest):
    ok = db.heartbeat(chunk_id=req.chunk_id, volunteer=req.volunteer)
    if not ok:
        raise HTTPException(status_code=404, detail="Chunk nie istnieje lub dzierżawa wygasła.")
    return {"status": "OK"}

@app.post("/api/chunk/complete")
def complete_chunk(req: CompleteRequest):
    ok = db.complete_chunk(
        chunk_id=req.chunk_id,
        volunteer=req.volunteer,
        items_saved=req.items_saved,
        items_404=req.items_404,
        warc_filename=req.warc_filename or "",
        warc_size=req.warc_size or 0,
        checksum=req.checksum or ""
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Nie udało się zapisać ukończenia chunka.")
    return {"status": "OK", "message": f"Paczka {req.chunk_id} pomyślnie oznaczona jako ukończona!"}

@app.get("/api/stats")
def get_stats():
    return db.get_stats()

@app.get("/", response_class=HTMLResponse)
def dashboard():
    stats = db.get_stats()
    pct = stats["percent_complete"]
    gb_saved = round(stats["total_warc_bytes"] / (1024 ** 3), 2)
    
    active_rows = ""
    for w in stats["active_workers"]:
        active_rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #334155;"><strong>{w['volunteer']}</strong></td>
            <td style="padding: 10px; border-bottom: 1px solid #334155;">Paczka #{w['chunk_id']} ({w['range']})</td>
            <td style="padding: 10px; border-bottom: 1px solid #334155; color: #4ade80;">{w['seconds_since_heartbeat']}s temu</td>
        </tr>
        """
    if not active_rows:
        active_rows = "<tr><td colspan='3' style='padding: 15px; text-align: center; color: #94a3b8;'>Brak aktywnych workerów w tej chwili.</td></tr>"

    leaderboard_rows = ""
    for idx, l in enumerate(stats["leaderboard"], 1):
        leaderboard_rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #334155;">#{idx}</td>
            <td style="padding: 10px; border-bottom: 1px solid #334155;"><strong>{l['volunteer']}</strong></td>
            <td style="padding: 10px; border-bottom: 1px solid #334155;">{l['chunks_done']} paczek</td>
            <td style="padding: 10px; border-bottom: 1px solid #334155; color: #38bdf8;">{l['items_saved']:,} pytań</td>
        </tr>
        """
    if not leaderboard_rows:
        leaderboard_rows = "<tr><td colspan='4' style='padding: 15px; text-align: center; color: #94a3b8;'>Czekamy na pierwsze ukończone paczki!</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Zapytaj Onet Rescue - Koordynator</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 25px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
            h1, h2 {{ margin-top: 0; }}
            .progress-bar-bg {{ background: #334155; border-radius: 8px; height: 26px; overflow: hidden; margin-top: 10px; }}
            .progress-bar-fill {{ background: linear-gradient(90deg, #3b82f6, #10b981); height: 100%; text-align: center; font-weight: bold; line-height: 26px; font-size: 14px; width: {max(pct, 1.0)}%; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }}
            .stat-box {{ background: #0f172a; padding: 15px; border-radius: 8px; border: 1px solid #334155; text-align: center; }}
            .stat-val {{ font-size: 24px; font-weight: bold; color: #38bdf8; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ background: #0f172a; padding: 10px; border-bottom: 2px solid #475569; color: #94a3b8; font-size: 13px; text-transform: uppercase; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1>Zapytaj Onet Rescue Dashboard</h1>
                <p style="color: #94a3b8;">Ratujemy zawartość serwisu Zapytaj.onet.pl przed wyłączeniem 30 września 2026 r.</p>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill">{pct}%</div>
                </div>
                <div class="stats-grid">
                    <div class="stat-box"><div>Ukończone paczki</div><div class="stat-val">{stats['done_chunks']} / {stats['total_chunks']}</div></div>
                    <div class="stat-box"><div>Zapisane pytania</div><div class="stat-val">{stats['total_items_saved']:,}</div></div>
                    <div class="stat-box"><div>Brakujące (404)</div><div class="stat-val">{stats['total_items_404']:,}</div></div>
                    <div class="stat-box"><div>Pobrane WARC</div><div class="stat-val">{gb_saved} GB</div></div>
                </div>
            </div>

            <div class="card">
                <h2>Aktywni Wolontariusze ({stats['active_chunks']})</h2>
                <table>
                    <thead>
                        <tr><th>Wolontariusz</th><th>Przydział (Zakres ID)</th><th>Ostatni Heartbeat</th></tr>
                    </thead>
                    <tbody>
                        {active_rows}
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h2>Ranking Wolontariuszy</h2>
                <table>
                    <thead>
                        <tr><th>Pozycja</th><th>Wolontariusz</th><th>Ukończone Paczki</th><th>Zabezpieczone Pytania</th></tr>
                    </thead>
                    <tbody>
                        {leaderboard_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
