from datetime import datetime
import json
import os
import re
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard
import requests

TZ_LOCAL = ZoneInfo("America/Caracas")
SEASON = "2026-27"
PUNTOS_FILE = "nba_puntos.json"
TRIPLES_FILE = "nba_triples.json"
LIVE_FILE = "nba_live.json"

BREF_PER_GAME_URL = "https://www.basketball-reference.com/leagues/NBA_2027_per_game.html"
BREF_STANDINGS_URL = "https://www.basketball-reference.com/leagues/NBA_2027.html"

TEAM_COLORS = {
    "ATL": ("#E03A3E", "#C1D32F", "Atlanta Hawks"),
    "BOS": ("#007A33", "#BA9653", "Boston Celtics"),
    "BKN": ("#111827", "#9CA3AF", "Brooklyn Nets"),
    "BRK": ("#111827", "#9CA3AF", "Brooklyn Nets"),
    "CHA": ("#1D1160", "#00788C", "Charlotte Hornets"),
    "CHO": ("#1D1160", "#00788C", "Charlotte Hornets"),
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
    "PHO": ("#1D1160", "#E56020", "Phoenix Suns"),
    "POR": ("#E03A3E", "#9CA3AF", "Portland Trail Blazers"),
    "SAC": ("#5A2D81", "#63727A", "Sacramento Kings"),
    "SAS": ("#1F2937", "#C4CED4", "San Antonio Spurs"),
    "TOR": ("#CE1141", "#A1A1A4", "Toronto Raptors"),
    "UTA": ("#002B5C", "#F9A01B", "Utah Jazz"),
    "WAS": ("#002B5C", "#E31837", "Washington Wizards"),
}

BREF_TO_NBA = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}

NAME_TO_TEAM = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def normalizar_equipo(tri):
    t = str(tri or "").strip().upper()
    return BREF_TO_NBA.get(t, t)


def cargar_json_seguro(ruta, por_defecto):
    if not os.path.exists(ruta):
        return json.loads(json.dumps(por_defecto))
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return json.loads(json.dumps(por_defecto))
        for k, v in por_defecto.items():
            data.setdefault(k, json.loads(json.dumps(v)))
        return data
    except Exception:
        return json.loads(json.dumps(por_defecto))


def obtener_team_games_publico(actual):
    team_pj_map = dict(actual or {})
    try:
        st_resp = requests.get(BREF_STANDINGS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if st_resp.status_code == 200:
            for m_name, tri in NAME_TO_TEAM.items():
                pat = rf'href="/teams/{re.escape(tri)}/2027\.html"[^>]*>{re.escape(m_name)}</a>.*?</td\s*>\s*<td[^>]*>(\d+)</td>\s*<td[^>]*>(\d+)</td>'
                mt = re.search(pat, st_resp.text, flags=re.S)
                if mt:
                    team_pj_map[tri] = max(int(team_pj_map.get(tri, 0)), int(mt.group(1)) + int(mt.group(2)))
    except Exception:
        pass
    return team_pj_map


def poblar_base_puntos_si_vacia(base):
    if base.get("jugadores"):
        return False
    try:
        resp = requests.get(BREF_PER_GAME_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if resp.status_code != 200:
            return False
        team_pj_map = obtener_team_games_publico(base.get("team_games", {}))
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', resp.text, flags=re.S)
        jugadores = []
        idx_fb = 900000

        for r in rows:
            if 'data-stat="player"' not in r or 'data-stat="pts_per_g"' not in r:
                continue
            m_player = re.search(r'data-stat="player"[^>]*>(.*?)</td>', r, flags=re.S)
            m_team = re.search(r'data-stat="team_name_abbr"[^>]*>(.*?)</td>', r, flags=re.S) or re.search(r'data-stat="team_id"[^>]*>(.*?)</td>', r, flags=re.S)
            m_g = re.search(r'data-stat="g"[^>]*>(\d+)</td>', r)
            m_fg = re.search(r'data-stat="fg_pct"[^>]*>([.0-9]*)</td>', r)
            m_pts = re.search(r'data-stat="pts_per_g"[^>]*>([.0-9]*)</td>', r)
            if not (m_player and m_team and m_g and m_pts):
                continue

            nombre = re.sub(r"<[^>]+>", "", m_player.group(1)).strip()
            eq = normalizar_equipo(re.sub(r"<[^>]+>", "", m_team.group(1)).strip())
            if not nombre or not eq or eq in ("2TM", "3TM", "TOT"):
                continue

            pj = int(m_g.group(1))
            ppg = float(m_pts.group(1) or 0.0)
            fg_raw = m_fg.group(1) if m_fg else ""
            fg_pct = round(float(fg_raw) * 100.0 if fg_raw and float(fg_raw) <= 1.0 else (float(fg_raw) if fg_raw else 0.0), 1)
            tpj = max(int(team_pj_map.get(eq, pj)), pj)
            team_pj_map[eq] = tpj
            pct_pj = round((pj / tpj) * 100.0, 1) if tpj > 0 else 0.0

            if pct_pj < 80.0 or fg_pct <= 40.0 or ppg < 14.0:
                continue

            if ppg >= 25.0:
                p_alto, p_medio = 62.0, 28.0
            elif ppg >= 20.0:
                p_alto, p_medio = 34.0, 48.0
            else:
                p_alto, p_medio = 18.0, 54.0
            p_bajo = round(max(0.0, 100.0 - p_alto - p_medio), 1)
            p_medio, p_alto = round(p_medio, 1), round(p_alto, 1)
            c_bajo = int(round((p_bajo / 100.0) * pj))
            c_medio = int(round((p_medio / 100.0) * pj))
            c_alto = max(0, pj - c_bajo - c_medio)

            idx_fb += 1
            cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))
            jugadores.append({
                "player_id": idx_fb,
                "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{idx_fb}.png",
                "jugador": nombre,
                "equipo": eq,
                "equipo_nombre": en,
                "color_prim": cp,
                "color_sec": cs,
                "juega_hoy": False,
                "pj": pj,
                "team_pj": tpj,
                "pj_str": f"{pj}/{tpj}",
                "pct_pj": pct_pj,
                "fg_pct": fg_pct,
                "ppg": round(ppg, 1),
                "max_pts": int(round(ppg * 1.45)),
                "ultimo_partido": datetime.now(TZ_LOCAL).strftime("%d/%m/%Y"),
                "intervalos": {
                    "0-14": {"juegos": c_bajo, "pct": p_bajo},
                    "15-24": {"juegos": c_medio, "pct": p_medio},
                    "25+": {"juegos": c_alto, "pct": p_alto},
                },
            })

        if jugadores:
            jugadores.sort(key=lambda x: (-x["ppg"], x["jugador"]))
            base["team_games"] = team_pj_map
            base["jugadores"] = jugadores
            base["corte"] = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")
            return True
    except Exception as e:
        print(f"Aviso cargando base de puntos: {e}")
    return False


def recalcular_jugadores_puntos(base, equipos_hoy):
    team_games = base.get("team_games", {})
    historial = base.get("historial_jugadores", {})
    elegibles = []

    for pid_str, info in historial.items():
        pid = int(pid_str)
        eq = normalizar_equipo(info.get("equipo", ""))
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
        fgm_tot = sum(float(x.get("fgm", 0)) for x in juegos)
        fga_tot = sum(float(x.get("fga", 0)) for x in juegos)
        fg_pct = round((fgm_tot / fga_tot) * 100.0, 1) if fga_tot > 0 else 0.0
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

    if elegibles:
        elegibles.sort(key=lambda x: (-x["ppg"], x["jugador"]))
        return elegibles

    actuales = base.get("jugadores", [])
    for item in actuales:
        item["juega_hoy"] = item.get("equipo") in set(equipos_hoy)
    return actuales


def recalcular_jugadores_triples(triples_base, equipos_hoy):
    team_games = triples_base.get("team_games", {})
    historial = triples_base.get("historial_triples", {})
    elegibles = []

    for pid_str, info in historial.items():
        pid = int(pid_str)
        eq = normalizar_equipo(info.get("equipo", ""))
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

        tpm_list = [int(x.get("tpm", 0)) for x in juegos]
        tpa_list = [int(x.get("tpa", 0)) for x in juegos]
        tpa_pj = round(sum(tpa_list) / pj, 1)
        if tpa_pj < 5.0:
            continue

        tpm_pj = round(sum(tpm_list) / pj, 1)
        tpa_tot = sum(tpa_list)
        pct_3p = round((sum(tpm_list) / tpa_tot) * 100.0, 1) if tpa_tot > 0 else 0.0
        p1 = round((sum(1 for x in tpm_list if x >= 1) / pj) * 100.0, 1)
        p2 = round((sum(1 for x in tpm_list if x >= 2) / pj) * 100.0, 1)
        p3 = round((sum(1 for x in tpm_list if x >= 3) / pj) * 100.0, 1)

        max_t = max(tpm_list)
        freq = {str(k): sum(1 for x in tpm_list if x == k) for k in range(max_t + 1)}
        cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))

        elegibles.append({
            "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png",
            "equipo": eq,
            "equipo_nombre": en,
            "juega_hoy": eq in set(equipos_hoy),
            "color_prim": cp,
            "color_sec": cs,
            "jugador": info.get("jugador", ""),
            "ultimo_partido": info.get("ultimo_partido", ""),
            "pj_str": f"{pj}/{tpj}",
            "pct_pj": pct_pj,
            "tpa_pj": tpa_pj,
            "tpm_pj": tpm_pj,
            "pct_3p": pct_3p,
            "prob_1": p1,
            "prob_2": p2,
            "prob_3": p3,
            "max_3pm": max_t,
            "freq": freq,
        })

    if elegibles:
        elegibles.sort(key=lambda x: (-x["prob_2"], -x["prob_1"], x["jugador"]))
        return elegibles

    actuales = triples_base.get("jugadores", [])
    for item in actuales:
        item["juega_hoy"] = item.get("equipo") in set(equipos_hoy)
    return actuales


def sincronizar_todo():
    vivo_jugadores = {}
    partidos_estado = []
    equipos_hoy = set()
    partidos_hoy = []

    base_pts = cargar_json_seguro(PUNTOS_FILE, {
        "season": SEASON, "corte": "", "fecha_hoy": "", "fecha_generacion": "",
        "generado": "", "equipos_hoy": [], "partidos_hoy": [],
        "games_procesados": [], "team_games": {}, "historial_jugadores": {}, "jugadores": [],
    })
    base_3p = cargar_json_seguro(TRIPLES_FILE, {
        "season": SEASON, "corte": "", "fecha_hoy": "", "generado": "",
        "equipos_hoy": [], "partidos_hoy": [],
        "games_procesados": [], "team_games": {}, "historial_triples": {}, "jugadores": [],
    })

    games_pts = set(base_pts.get("games_procesados", []))
    games_3p = set(base_3p.get("games_procesados", []))
    hist_pts = base_pts.get("historial_jugadores", {})
    hist_3p = base_3p.get("historial_triples", {})
    tg_pts = base_pts.get("team_games", {})
    tg_3p = base_3p.get("team_games", {})

    cambio_pts = poblar_base_puntos_si_vacia(base_pts)
    cambio_3p = False

    try:
        sb = scoreboard.ScoreBoard()
        games = sb.get_dict().get("scoreboard", {}).get("games", [])
        for g in games:
            gid = str(g.get("gameId") or "")
            status_text = str(g.get("gameStatusText", "")).strip()
            game_status = g.get("gameStatus")
            es_live = (game_status == 2) or (
                "LIVE" in status_text.upper()
                or ("Q" in status_text.upper() and "FINAL" not in status_text.upper())
            )
            away = normalizar_equipo(g.get("awayTeam", {}).get("teamTricode", ""))
            home = normalizar_equipo(g.get("homeTeam", {}).get("teamTricode", ""))
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
                    fecha_txt = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")
                    for side, tri in (("homeTeam", home), ("awayTeam", away)):
                        for p in bs.get(side, {}).get("players", []):
                            nombre = p.get("name", "")
                            pid = p.get("personId")
                            st = p.get("statistics", {})
                            tpm = int(st.get("threePointersMade", 0) or 0)
                            tpa = int(st.get("threePointersAttempted", 0) or 0)
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

                            if game_status == 3 and pid and mins not in ("", "PT00M00.00S"):
                                p_key = str(pid)
                                if gid not in games_pts:
                                    e_pts = hist_pts.setdefault(p_key, {"jugador": nombre, "equipo": tri, "ultimo_partido": fecha_txt, "juegos": []})
                                    e_pts["jugador"], e_pts["equipo"], e_pts["ultimo_partido"] = nombre, tri, fecha_txt
                                    if not any(j.get("game_id") == gid for j in e_pts["juegos"]):
                                        e_pts["juegos"].append({"game_id": gid, "pts": pts, "fgm": fgm, "fga": fga})
                                        cambio_pts = True

                                if gid not in games_3p:
                                    e_3p = hist_3p.setdefault(p_key, {"jugador": nombre, "equipo": tri, "ultimo_partido": fecha_txt, "juegos": []})
                                    e_3p["jugador"], e_3p["equipo"], e_3p["ultimo_partido"] = nombre, tri, fecha_txt
                                    if not any(j.get("game_id") == gid for j in e_3p["juegos"]):
                                        e_3p["juegos"].append({"game_id": gid, "tpm": tpm, "tpa": tpa})
                                        cambio_3p = True

                    if game_status == 3:
                        if gid not in games_pts:
                            for tri in (away, home):
                                if tri:
                                    tg_pts[tri] = int(tg_pts.get(tri, 0)) + 1
                            games_pts.add(gid)
                            cambio_pts = True
                        if gid not in games_3p:
                            for tri in (away, home):
                                if tri:
                                    tg_3p[tri] = int(tg_3p.get(tri, 0)) + 1
                            games_3p.add(gid)
                            cambio_3p = True

                    time.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        print(f"Aviso en vivo: {e}")

    ahora = datetime.now(TZ_LOCAL)
    eq_sorted = sorted(equipos_hoy)
    live_payload = {
        "actualizado_en": ahora.strftime("%d/%m/%Y %I:%M:%S %p"),
        "equipos_hoy": eq_sorted,
        "partidos_hoy": partidos_hoy,
        "partidos": partidos_estado,
        "jugadores_live": vivo_jugadores,
    }
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(live_payload, f, ensure_ascii=False)

    if cambio_pts or not os.path.exists(PUNTOS_FILE):
        base_pts["games_procesados"] = sorted(games_pts)
        base_pts["team_games"] = tg_pts
        base_pts["historial_jugadores"] = hist_pts
        base_pts["equipos_hoy"] = eq_sorted
        base_pts["partidos_hoy"] = partidos_hoy
        base_pts["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
        base_pts["fecha_generacion"] = ahora.strftime("%Y-%m-%d")
        base_pts["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
        base_pts["jugadores"] = recalcular_jugadores_puntos(base_pts, eq_sorted)
        with open(PUNTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(base_pts, f, ensure_ascii=False)

    if cambio_3p or os.path.exists(TRIPLES_FILE):
        base_3p["games_procesados"] = sorted(games_3p)
        base_3p["team_games"] = tg_3p
        base_3p["historial_triples"] = hist_3p
        base_3p["equipos_hoy"] = eq_sorted
        base_3p["partidos_hoy"] = partidos_hoy
        base_3p["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
        base_3p["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
        base_3p["corte"] = ahora.strftime("%d/%m/%Y")
        base_3p["jugadores"] = recalcular_jugadores_triples(base_3p, eq_sorted)
        with open(TRIPLES_FILE, "w", encoding="utf-8") as f:
            json.dump(base_3p, f, ensure_ascii=False)

    n_live = sum(1 for x in partidos_estado if x["es_live"])
    print(f"Live actualizado ({live_payload['actualizado_en']}) | Juegos en vivo: {n_live} | Partidos en scoreboard: {len(partidos_estado)} | Puntos elegibles: {len(base_pts.get('jugadores', []))}")


if __name__ == "__main__":
    sincronizar_todo()
