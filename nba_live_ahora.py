from datetime import datetime
from zoneinfo import ZoneInfo

TZ_LOCAL = ZoneInfo("America/Caracas")
import json
import time
import pandas as pd
from nba_api.live.nba.endpoints import boxscore, scoreboard

def obtener_vivo():
    vivo_jugadores = {}
    partidos_estado = []
    try:
        sb = scoreboard.ScoreBoard()
        data = sb.get_dict()
        games = data.get("scoreboard", {}).get("games", [])
        for g in games:
            gid = g.get("gameId")
            status_text = str(g.get("gameStatusText", "")).strip()
            game_status = g.get("gameStatus")  # 1=previa, 2=en vivo, 3=finalizado
            es_live = (game_status == 2) or ("LIVE" in status_text.upper()) or ("Q" in status_text.upper() and "FINAL" not in status_text.upper())

            away = g.get("awayTeam", {}).get("teamTricode", "")
            home = g.get("homeTeam", {}).get("teamTricode", "")
            partidos_estado.append({
                "game_id": gid,
                "matchup": f"{away} @ {home}",
                "status_text": status_text,
                "es_live": es_live,
            })

            if gid and game_status in (2, 3):
                try:
                    bs = boxscore.BoxScore(game_id=gid).get_dict().get("game", {})
                    for side in ("homeTeam", "awayTeam"):
                        for p in bs.get(side, {}).get("players", []):
                            nombre = p.get("name", "")
                            st = p.get("statistics", {})
                            tpm = st.get("threePointersMade", 0)
                            tpa = st.get("threePointersAttempted", 0)
                            pts = st.get("points", 0)
                            mins = st.get("minutesCalculated", "")
                            if nombre:
                                vivo_jugadores[nombre.lower()] = {
                                    "es_live": es_live,
                                    "estado_juego": status_text,
                                    "3pm_live": tpm,
                                    "3pa_live": tpa,
                                    "pts_live": pts,
                                    "min_live": mins,
                                }
                    time.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        print(f"Aviso en vivo: {e}")

    return {
        "actualizado_en": datetime.now(TZ_LOCAL).strftime("%d/%m/%Y %I:%M:%S %p"),
        "partidos": partidos_estado,
        "jugadores_live": vivo_jugadores,
    }

if __name__ == "__main__":
    payload = obtener_vivo()
    with open("nba_live.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    n_live = sum(1 for x in payload["partidos"] if x["es_live"])
    print(f"Live actualizado ({payload['actualizado_en']}) | Juegos en vivo: {n_live}")