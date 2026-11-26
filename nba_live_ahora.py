from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard
import requests

TZ_LOCAL = ZoneInfo("America/Caracas")
SEASON = "2026-27"
PUNTOS_FILE = "nba_puntos.json"
TRIPLES_FILE = "nba_triples.json"
LIVE_FILE = "nba_live.json"

ESPN_NBA_STATS_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete"
    "?region=us&lang=en&contentorigin=espn&limit=500&page=1&season=2027&seasontype=2"
)

BASE_INICIAL_PUNTOS = [
    (1628369, "Jayson Tatum", "BOS", 15, 17, 46.8, 26.4, 38),
    (1629029, "Luka Dončić", "LAL", 16, 18, 47.2, 29.8, 42),
    (1628983, "Shai Gilgeous-Alexander", "OKC", 17, 18, 51.4, 31.2, 44),
    (1630595, "Cade Cunningham", "DET", 15, 16, 45.6, 24.1, 35),
    (1628973, "Jalen Brunson", "NYK", 17, 17, 48.1, 25.3, 37),
    (1630178, "Tyrese Maxey", "PHI", 17, 18, 44.8, 24.7, 36),
    (1641705, "Victor Wembanyama", "SAS", 17, 18, 48.5, 23.6, 35),
    (1627750, "Jamal Murray", "DEN", 15, 15, 46.2, 21.4, 32),
    (1626164, "Devin Booker", "PHX", 16, 16, 45.9, 25.1, 36),
    (203081, "Damian Lillard", "POR", 17, 17, 43.7, 22.8, 34),
    (1630217, "Desmond Bane", "ORL", 15, 16, 46.5, 20.9, 31),
    (1629639, "Tyler Herro", "MIL", 17, 18, 45.3, 22.1, 33),
]

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

BREF_TO_NBA = {
    "BRK": "BKN",
    "CHO": "CHA",
    "PHO": "PHX",
    "WSH": "WAS",
    "NO": "NOP",
    "GS": "GSW",
    "NY": "NYK",
    "SA": "SAS",
    "UTAH": "UTA",
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


def construir_fila_elegible(pid, nombre, eq, pj, tpj, fg_pct, ppg, max_pts, fecha_txt, equipos_hoy):
    pct_pj = round((pj / tpj) * 100.0, 1) if tpj > 0 else 0.0
    if pct_pj < 80.0 or fg_pct <= 40.0 or ppg < 14.0:
        return None

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

    cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))
    return {
        "player_id": int(pid),
        "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{int(pid)}.png",
        "jugador": nombre,
        "equipo": eq,
        "equipo_nombre": en,
        "color_prim": cp,
        "color_sec": cs,
        "juega_hoy": eq in set(equipos_hoy),
        "pj": pj,
        "team_pj": tpj,
        "pj_str": f"{pj}/{tpj}",
        "pct_pj": pct_pj,
        "fg_pct": round(fg_pct, 1),
        "ppg": round(ppg, 1),
        "max_pts": int(max_pts),
        "ultimo_partido": fecha_txt,
        "intervalos": {
            "0-14": {"juegos": c_bajo, "pct": p_bajo},
            "15-24": {"juegos": c_medio, "pct": p_medio},
            "25+": {"juegos": c_alto, "pct": p_alto},
        },
    }


def sembrar_historial_jugador(historial, fila, fecha_txt):
    pid = fila["player_id"]
    pj = fila["pj"]
    fg_pct = fila["fg_pct"]
    ppg = fila["ppg"]
    max_pts = fila["max_pts"]
    ints = fila["intervalos"]

    fga_est = pj * 16
    fgm_est = round(fga_est * (fg_pct / 100.0))

    historial[str(pid)] = {
        "jugador": fila["jugador"],
        "equipo": fila["equipo"],
        "ultimo_partido": fecha_txt,
        "base_pj": pj,
        "base_pts": round(ppg * pj),
        "base_fgm": fgm_est,
        "base_fga": fga_est,
        "base_max_pts": max_pts,
        "base_intervalos": {
            "0-14": ints["0-14"]["juegos"],
            "15-24": ints["15-24"]["juegos"],
            "25+": ints["25+"]["juegos"],
        },
        "juegos": [],
    }


def poblar_desde_espn(base):
    try:
        resp = requests.get(
            ESPN_NBA_STATS_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"Aviso ESPN status: {resp.status_code}")
            return False
        payload = resp.json()
        athletes = payload.get("athletes") or []
        if not athletes:
            return False

        team_pj_map = dict(base.get("team_games", {}))
        historial = base.setdefault("historial_jugadores", {})
        jugadores = []
        fecha_txt = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")
        eq_hoy = base.get("equipos_hoy", [])

        for item in athletes:
            ath = item.get("athlete") or {}
            pid_raw = ath.get("id")
            nombre = str(ath.get("displayName") or "").strip()
            team_obj = ath.get("team") or item.get("team") or {}
            eq = normalizar_equipo(team_obj.get("abbreviation") or "")
            if not pid_raw or not nombre or not eq or eq not in TEAM_COLORS:
                continue

            flat_map = {}
            names = item.get("names") or payload.get("names") or []
            vals = item.get("values") or []
            for idx_n, n_val in enumerate(names):
                if idx_n < len(vals):
                    flat_map[str(n_val).lower()] = vals[idx_n]

            for cat in (item.get("categories") or []):
                c_names = cat.get("names") or []
                c_vals = cat.get("values") or []
                for idx_c, c_name in enumerate(c_names):
                    if idx_c < len(c_vals):
                        flat_map[str(c_name).lower()] = c_vals[idx_c]

            pj = int(float(flat_map.get("gp", flat_map.get("gamesplayed", 0)) or 0))
            ppg = float(flat_map.get("avgpoints", flat_map.get("pts", 0)) or 0.0)
            fg_raw = float(flat_map.get("fieldgoalpct", flat_map.get("fg%", 0)) or 0.0)
            fg_pct = round(fg_raw * 100.0 if 0 < fg_raw <= 1.0 else fg_raw, 1)

            if pj <= 0:
                continue

            tpj = max(int(team_pj_map.get(eq, pj)), pj)
            team_pj_map[eq] = tpj

            fila = construir_fila_elegible(
                pid=pid_raw,
                nombre=nombre,
                eq=eq,
                pj=pj,
                tpj=tpj,
                fg_pct=fg_pct,
                ppg=ppg,
                max_pts=round(ppg * 1.45),
                fecha_txt=fecha_txt,
                equipos_hoy=eq_hoy,
            )
            if fila:
                jugadores.append(fila)
                sembrar_historial_jugador(historial, fila, fecha_txt)

        if jugadores:
            jugadores.sort(key=lambda x: (-x["ppg"], x["jugador"]))
            base["team_games"] = team_pj_map
            base["jugadores"] = jugadores
            base["corte"] = fecha_txt
            print(f"Base de puntos poblada desde ESPN: {len(jugadores)} jugadores")
            return True
    except Exception as e:
        print(f"Aviso cargando base desde ESPN: {e}")
    return False


def poblar_base_puntos_si_vacia(base):
    if base.get("historial_jugadores") or base.get("jugadores"):
        return False

    if poblar_desde_espn(base):
        return True

    fecha_txt = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")
    eq_hoy = base.get("equipos_hoy", [])
    team_pj_map = dict(base.get("team_games", {}))
    historial = base.setdefault("historial_jugadores", {})
    jugadores = []

    for pid, nombre, eq, pj, tpj, fg_pct, ppg, max_pts in BASE_INICIAL_PUNTOS:
        tpj_real = max(int(team_pj_map.get(eq, tpj)), pj)
        team_pj_map[eq] = tpj_real
        fila = construir_fila_elegible(
            pid=pid,
            nombre=nombre,
            eq=eq,
            pj=pj,
            tpj=tpj_real,
            fg_pct=fg_pct,
            ppg=ppg,
            max_pts=max_pts,
            fecha_txt=fecha_txt,
            equipos_hoy=eq_hoy,
        )
        if fila:
            jugadores.append(fila)
            sembrar_historial_jugador(historial, fila, fecha_txt)

    if jugadores:
        jugadores.sort(key=lambda x: (-x["ppg"], x["jugador"]))
        base["team_games"] = team_pj_map
        base["jugadores"] = jugadores
        base["corte"] = fecha_txt
        print(f"Base de puntos cargada con respaldo inicial continuo: {len(jugadores)} jugadores")
        return True

    return False


def obtener_partidos_fecha_espn(fecha_yyyymmdd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fecha_yyyymmdd}"
    partidos = []
    equipos = set()
    partidos_estado = []
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code != 200:
            return partidos, equipos, partidos_estado
        data = resp.json()
        for ev in data.get("events") or []:
            ev_id = str(ev.get("id") or "")
            comp = (ev.get("competitions") or [{}])[0]
            comps = comp.get("competitors") or []
            status_obj = ((comp.get("status") or {}).get("type")) or {}
            status_text = str(status_obj.get("shortDetail") or status_obj.get("description") or "").strip()
            state = str(status_obj.get("state") or "").lower()
            es_live = state == "in"

            home = ""
            away = ""
            for c in comps:
                tri = normalizar_equipo(((c.get("team") or {}).get("abbreviation")) or "")
                if c.get("homeAway") == "home":
                    home = tri
                elif c.get("homeAway") == "away":
                    away = tri
            if away and home:
                matchup = f"{away} @ {home}"
                partidos.append(matchup)
                equipos.add(away)
                equipos.add(home)
                partidos_estado.append({
                    "game_id": ev_id,
                    "matchup": matchup,
                    "status_text": status_text,
                    "es_live": es_live,
                })
    except Exception as e:
        print(f"Aviso calendario ESPN: {e}")
    return partidos, equipos, partidos_estado


def recalcular_jugadores_puntos(base, equipos_hoy):
    team_games = base.get("team_games", {})
    historial = base.get("historial_jugadores", {})
    elegibles = []

    for pid_str, info in historial.items():
        pid = int(pid_str)
        eq = normalizar_equipo(info.get("equipo", ""))
        juegos = info.get("juegos", [])
        base_pj = int(info.get("base_pj", 0) or 0)
        if not eq or (not juegos and base_pj <= 0):
            continue

        pj = base_pj + len(juegos)
        tpj = max(int(team_games.get(eq, pj)), pj)
        if tpj <= 0 or pj <= 0:
            continue

        pct_pj = round((pj / tpj) * 100.0, 1)
        if pct_pj < 80.0:
            continue

        pts_nuevos = [int(x.get("pts", 0)) for x in juegos]
        pts_total = int(info.get("base_pts", 0) or 0) + sum(pts_nuevos)
        fgm_tot = float(info.get("base_fgm", 0) or 0) + sum(float(x.get("fgm", 0)) for x in juegos)
        fga_tot = float(info.get("base_fga", 0) or 0) + sum(float(x.get("fga", 0)) for x in juegos)

        fg_pct = round((fgm_tot / fga_tot) * 100.0, 1) if fga_tot > 0 else 0.0
        if fg_pct <= 40.0:
            continue

        ppg = round(pts_total / pj, 1)
        if ppg < 14.0:
            continue

        b_ints = info.get("base_intervalos", {})
        c_bajo = int(b_ints.get("0-14", 0) or 0) + sum(1 for p in pts_nuevos if p <= 14)
        c_medio = int(b_ints.get("15-24", 0) or 0) + sum(1 for p in pts_nuevos if 15 <= p <= 24)
        c_alto = int(b_ints.get("25+", 0) or 0) + sum(1 for p in pts_nuevos if p >= 25)

        max_pts = max([int(info.get("base_max_pts", 0) or 0)] + pts_nuevos)
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
            "max_pts": max_pts,
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
        "season": SEASON,
        "corte": "",
        "fecha_hoy": "",
        "fecha_generacion": "",
        "generado": "",
        "equipos_hoy": [],
        "partidos_hoy": [],
        "games_procesados": [],
        "team_games": {},
        "historial_jugadores": {},
        "jugadores": [],
    })
    base_3p = cargar_json_seguro(TRIPLES_FILE, {
        "season": SEASON,
        "corte": "",
        "fecha_hoy": "",
        "generado": "",
        "equipos_hoy": [],
        "partidos_hoy": [],
        "games_procesados": [],
        "team_games": {},
        "historial_triples": {},
        "jugadores": [],
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
                                    e_pts = hist_pts.setdefault(
                                        p_key,
                                        {
                                            "jugador": nombre,
                                            "equipo": tri,
                                            "ultimo_partido": fecha_txt,
                                            "base_pj": 0,
                                            "base_pts": 0,
                                            "base_fgm": 0,
                                            "base_fga": 0,
                                            "base_max_pts": 0,
                                            "base_intervalos": {"0-14": 0, "15-24": 0, "25+": 0},
                                            "juegos": [],
                                        },
                                    )
                                    e_pts["jugador"], e_pts["equipo"], e_pts["ultimo_partido"] = nombre, tri, fecha_txt
                                    if not any(j.get("game_id") == gid for j in e_pts["juegos"]):
                                        e_pts["juegos"].append({"game_id": gid, "pts": pts, "fgm": fgm, "fga": fga})
                                        cambio_pts = True

                                if gid not in games_3p:
                                    e_3p = hist_3p.setdefault(
                                        p_key,
                                        {"jugador": nombre, "equipo": tri, "ultimo_partido": fecha_txt, "juegos": []},
                                    )
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
    todos_finalizados = bool(partidos_estado) and all(
        not p["es_live"] and "FINAL" in str(p["status_text"]).upper()
        for p in partidos_estado
    )
    if (not partidos_hoy) or (todos_finalizados and ahora.hour < 17):
        partidos_espn, equipos_espn, estado_espn = obtener_partidos_fecha_espn(ahora.strftime("%Y%m%d"))
        if partidos_espn:
            partidos_hoy = partidos_espn
            equipos_hoy = equipos_espn
            partidos_estado = estado_espn

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
    print(
        f"Live actualizado ({live_payload['actualizado_en']}) | Juegos en vivo: {n_live} | "
        f"Partidos hoy: {len(partidos_hoy)} | Puntos elegibles: {len(base_pts.get('jugadores', []))}"
    )


if __name__ == "__main__":
    sincronizar_todo()
