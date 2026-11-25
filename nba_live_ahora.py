from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard

TZ_LOCAL = ZoneInfo("America/Caracas")
SEASON = "2026-27"
PUNTOS_FILE = "nba_puntos.json"
LIVE_FILE = "nba_live.json"

TEAM_COLORS = {
    "ATL": ("#E03A3E", "#C1D32F", "Atlanta Hawks"),
    "BOS": ("#007A33", "#BA9653", "Boston Celtics"),
    "BKN": ("#111827", "#9CA3AF", "Brooklyn Nets"),
    "CHA": ("#1D1160", "#00788C", "Charlotte Hornets"),
    "CHI": ("#CE1141", "#1F2937", "Chicago Bulls"),
    "CLE": ("#860038", "#FDBB30", "Cleveland Cavaliers"),
    "DAL": ("#00538C", "#B8C4CA", "Dallas Mavericks"),
    "DEN": ("#0E2240", "#FEC524", "Denver Nuggets"),
    "DET": ("#C8102E", "#1D42BA", "Detroit Pistons"),
    "GSW": ("#1D428A", "#FFC72C", "Golden State Warriors"),
    "HOU": ("#CE1141", "#9CA3AF", "Houston Rockets"),
    "IND": ("#002D62", "#FDBB30", "Indiana Pacers"),
    "LAC": ("#C8102E", "#1D428A", "LA Clippers"),
    "LAL": ("#552583", "#FDB927", "Los Angeles Lakers"),
    "MEM": ("#5D76A9", "#12173F", "Memphis Grizzlies"),
    "MIA": ("#98002E", "#F9A01B", "Miami Heat"),
    "MIL": ("#00471B", "#EEE1C6", "Milwaukee Bucks"),
    "MIN": ("#0C2340", "#78BE20", "Minnesota Timberwolves"),
    "NOP": ("#0C2340", "#C8102E", "New Orleans Pelicans"),
    "NYK": ("#006BB6", "#F58426", "New York Knicks"),
    "OKC": ("#007AC1", "#EF3B24", "Oklahoma City Thunder"),
    "ORL": ("#0077C0", "#C4CED4", "Orlando Magic"),
    "PHI": ("#006BB6", "#ED174C", "Philadelphia 76ers"),
    "PHX": ("#1D1160", "#E56020", "Phoenix Suns"),
    "POR": ("#E03A3E", "#9CA3AF", "Portland Trail Blazers"),
    "SAC": ("#5A2D81", "#63727A", "Sacramento Kings"),
    "SAS": ("#1F2937", "#C4CED4", "San Antonio Spurs"),
    "TOR": ("#CE1141", "#A1A1A4", "Toronto Raptors"),
    "UTA": ("#002B5C", "#F9A01B", "Utah Jazz"),
    "WAS": ("#002B5C", "#E31837", "Washington Wizards"),
}


def cargar_base_puntos():
    if not os.path.exists(PUNTOS_FILE):
        return {
            "season": SEASON,
            "corte": "",
            "fecha_hoy": datetime.now(TZ_LOCAL).strftime("%d/%m/%Y"),
            "fecha_generacion": datetime.now(TZ_LOCAL).strftime("%Y-%m-%d"),
            "generado": datetime.now(TZ_LOCAL).strftime("%d/%m/%Y %I:%M %p"),
            "equipos_hoy": [],
            "partidos_hoy": [],
            "games_procesados": [],
            "team_games": {},
            "historial_jugadores": {},
            "jugadores": [],
        }
    with open(PUNTOS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("games_procesados", [])
    data.setdefault("team_games", {})
    data.setdefault("historial_jugadores", {})
    data.setdefault("jugadores", [])
    return data


def recalcular_jugadores_desde_historial(base, equipos_hoy):
    team_games = base.get("team_games", {})
    historial = base.get("historial_jugadores", {})
    elegibles = []

    for pid_str, info in historial.items():
        pid = int(pid_str)
        eq = info.get("equipo", "")
        juegos = info.get("juegos", [])
        if not eq or not juegos:
            continue

        tpj = int(team_games.get(eq, len(juegos)))
        pj = len(juegos)
        if tpj <= 0 or pj <= 0:
            continue

        pct_pj = round((pj / tpj) * 100.0, 1)
        if pct_pj < 80.0:
            continue

        pts_list = [int(x.get("pts", 0)) for x in juegos]
        fgm_total = sum(float(x.get("fgm", 0)) for x in juegos)
        fga_total = sum(float(x.get("fga", 0)) for x in juegos)
        fg_pct = round((fgm_total / fga_total) * 100.0, 1) if fga_total > 0 else 0.0
        if fg_pct <= 40.0:
            continue

        ppg = round(sum(pts_list) / pj, 1)
        if ppg < 14.0:
            continue

        c_bajo = sum(1 for p in pts_list if p <= 14)
        c_medio = sum(1 for p in pts_list if 15 <= p <= 24)
        c_alto = sum(1 for p in pts_list if p >= 25)

        cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))
        elegibles.append({
            "player_id": pid,
            "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png",
            "jugador": info.get("jugador", ""),
            "equipo": eq,
            "equipo_nombre": en,
            "color_prim": cp,
            "color_sec": cs,
            "juega_hoy": eq in set(equipos_hoy),
            "pj": pj,
            "team_pj": tpj,
            "pj_str": f"{pj}/{tpj}",
            "pct_pj": pct_pj,
            "fg_pct": fg_pct,
            "ppg": ppg,
            "max_pts": max(pts_list),
            "ultimo_partido": info.get("ultimo_partido", ""),
            "intervalos": {
                "0-14": {"juegos": c_bajo, "pct": round((c_bajo / pj) * 100.0, 1)},
                "15-24": {"juegos": c_medio, "pct": round((c_medio / pj) * 100.0, 1)},
                "25+": {"juegos": c_alto, "pct": round((c_alto / pj) * 100.0, 1)},
            },
        })

    elegibles.sort(key=lambda x: (-x["ppg"], x["jugador"]))
    return elegibles


def obtener_vivo_y_acumular_puntos():
    vivo_jugadores = {}
    partidos_estado = []
    equipos_hoy = set()
    partidos_hoy = []
    base = cargar_base_puntos()
    games_vistos = set(base.get("games_procesados", []))
    historial = base.get("historial_jugadores", {})
    team_games = base.get("team_games", {})
    hubo_cambios_pts = False

    try:
        sb = scoreboard.ScoreBoard()
        data = sb.get_dict()
        games = data.get("scoreboard", {}).get("games", [])
        for g in games:
            gid = str(g.get("gameId") or "")
            status_text = str(g.get("gameStatusText", "")).strip()
            game_status = g.get("gameStatus")
            es_live = (game_status == 2) or (
                "LIVE" in status_text.upper()
                or ("Q" in status_text.upper() and "FINAL" not in status_text.upper())
            )

            away = g.get("awayTeam", {}).get("teamTricode", "")
            home = g.get("homeTeam", {}).get("teamTricode", "")
            if away:
                equipos_hoy.add(away)
            if home:
                equipos_hoy.add(home)
            if away and home:
                partidos_hoy.append(f"{away} @ {home}")

            partidos_estado.append({
                "game_id": gid,
                "matchup": f"{away} @ {home}",
                "status_text": status_text,
                "es_live": es_live,
            })

            if gid and game_status in (2, 3):
                try:
                    bs = boxscore.BoxScore(game_id=gid).get_dict().get("game", {})
                    for side, tri in (("homeTeam", home), ("awayTeam", away)):
                        for p in bs.get(side, {}).get("players", []):
                            nombre = p.get("name", "")
                            pid = p.get("personId")
                            st = p.get("statistics", {})
                            tpm = st.get("threePointersMade", 0)
                            tpa = st.get("threePointersAttempted", 0)
                            pts = int(st.get("points", 0) or 0)
                            fgm = int(st.get("fieldGoalsMade", 0) or 0)
                            fga = int(st.get("fieldGoalsAttempted", 0) or 0)
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

                            if game_status == 3 and gid not in games_vistos and pid and mins not in ("", "PT00M00.00S"):
                                p_key = str(pid)
                                entry = historial.setdefault(p_key, {
                                    "jugador": nombre,
                                    "equipo": tri,
                                    "ultimo_partido": datetime.now(TZ_LOCAL).strftime("%d/%m/%Y"),
                                    "juegos": [],
                                })
                                entry["jugador"] = nombre
                                entry["equipo"] = tri
                                entry["ultimo_partido"] = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")
                                if not any(j.get("game_id") == gid for j in entry["juegos"]):
                                    entry["juegos"].append({
                                        "game_id": gid,
                                        "pts": pts,
                                        "fgm": fgm,
                                        "fga": fga,
                                    })
                                    hubo_cambios_pts = True

                    if game_status == 3 and gid not in games_vistos:
                        for tri in (away, home):
                            if tri:
                                team_games[tri] = int(team_games.get(tri, 0)) + 1
                        games_vistos.add(gid)
                        hubo_cambios_pts = True

                    time.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        print(f"Aviso en vivo: {e}")

    ahora = datetime.now(TZ_LOCAL)
    live_payload = {
        "actualizado_en": ahora.strftime("%d/%m/%Y %I:%M:%S %p"),
        "equipos_hoy": sorted(equipos_hoy),
        "partidos_hoy": partidos_hoy,
        "partidos": partidos_estado,
        "jugadores_live": vivo_jugadores,
    }

    if hubo_cambios_pts or not os.path.exists(PUNTOS_FILE):
        base["games_procesados"] = sorted(games_vistos)
        base["team_games"] = team_games
        base["historial_jugadores"] = historial
        base["equipos_hoy"] = sorted(equipos_hoy)
        base["partidos_hoy"] = partidos_hoy
        base["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
        base["fecha_generacion"] = ahora.strftime("%Y-%m-%d")
        base["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
        base["jugadores"] = recalcular_jugadores_desde_historial(base, sorted(equipos_hoy))
        with open(PUNTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False)
        print(f"Puntos por jugador actualizados en nube: {len(base['jugadores'])} elegibles")

    return live_payload


if __name__ == "__main__":
    live_payload = obtener_vivo_y_acumular_puntos()
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(live_payload, f, ensure_ascii=False)
    n_live = sum(1 for x in live_payload["partidos"] if x["es_live"])
    print(f"Live actualizado ({live_payload['actualizado_en']}) | Juegos en vivo: {n_live} | Partidos en scoreboard: {len(live_payload['partidos'])}")
