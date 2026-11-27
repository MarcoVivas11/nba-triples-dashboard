from datetime import datetime, timedelta
import json
import os
import re
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard
import requests

TZ_LOCAL = ZoneInfo("America/Caracas")
SEASON = "2026-27"
SEASON_START_DATE = datetime(2026, 10, 20, tzinfo=TZ_LOCAL).date()
MAX_ESPN_GAMES_PER_RUN = 18

PUNTOS_FILE = "nba_puntos.json"
TRIPLES_FILE = "nba_triples.json"
LIVE_FILE = "nba_live.json"

HEADERS_ESPN = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

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
    "LAC": ("#C8102E", "#1D42BA", "LA Clippers"),
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


def fecha_mas_reciente(actual_str, candidata_str):
    if not candidata_str:
        return actual_str
    if not actual_str:
        return candidata_str
    try:
        d_act = datetime.strptime(actual_str, "%d/%m/%Y").date()
        d_cand = datetime.strptime(candidata_str, "%d/%m/%Y").date()
        return candidata_str if d_cand >= d_act else actual_str
    except Exception:
        return candidata_str


def parsear_hecho_o_intentado(val):
    s = str(val or "").strip()
    if "-" in s:
        partes = s.split("-", 1)
        try:
            return int(partes[0].strip()), int(partes[1].strip())
        except Exception:
            return 0, 0
    try:
        return int(float(s)), 0
    except Exception:
        return 0, 0


def minutos_jugados_espn(min_str):
    s = str(min_str or "").strip()
    if not s or s.upper() in ("0", "00", "DNP", "--"):
        return 0.0
    if ":" in s:
        partes = s.split(":")
        try:
            m = float(partes[0])
            sec = float(partes[1]) if len(partes) > 1 else 0.0
            return m + (sec / 60.0)
        except Exception:
            return 0.0
    m_match = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m_match.group(1)) if m_match else 0.0


def obtener_partidos_fecha_espn(fecha_yyyymmdd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fecha_yyyymmdd}"
    partidos = []
    equipos = set()
    partidos_estado = []
    finalizados = []
    try:
        resp = requests.get(url, headers=HEADERS_ESPN, timeout=15)
        if resp.status_code != 200:
            return partidos, equipos, partidos_estado, finalizados
        data = resp.json()
        for ev in data.get("events") or []:
            ev_id = str(ev.get("id") or "")
            comp = (ev.get("competitions") or [{}])[0]
            comps = comp.get("competitors") or []
            status_obj = ((comp.get("status") or {}).get("type")) or {}
            status_text = str(status_obj.get("shortDetail") or status_obj.get("description") or "").strip()
            state = str(status_obj.get("state") or "").lower()
            completed = bool(status_obj.get("completed"))
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
                if completed or state == "post":
                    finalizados.append({
                        "event_id": ev_id,
                        "away": away,
                        "home": home,
                    })
    except Exception as e:
        print(f"Aviso calendario ESPN ({fecha_yyyymmdd}): {e}")
    return partidos, equipos, partidos_estado, finalizados


def procesar_evento_espn(
    ev_id,
    away,
    home,
    fecha_txt,
    games_pts,
    games_3p,
    hist_pts,
    hist_3p,
    tg_pts,
    tg_3p,
    solo_fotos=False,
):
    gid = f"ESPN_{ev_id}"
    if not solo_fotos and gid in games_pts and gid in games_3p:
        return False, False

    url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={ev_id}"
    resp = requests.get(url, headers=HEADERS_ESPN, timeout=15)
    if resp.status_code != 200:
        return False, False

    data = resp.json()
    box = data.get("boxscore") or {}
    players_groups = box.get("players") or []
    if not players_groups:
        return False, False

    cambio_pts = False
    cambio_3p = False

    for grp in players_groups:
        team_info = grp.get("team") or {}
        tri = normalizar_equipo(team_info.get("abbreviation") or "")
        if tri not in TEAM_COLORS:
            continue

        stat_blocks = grp.get("statistics") or []
        if not stat_blocks:
            continue

        block = stat_blocks[0]
        labels = [str(x).upper() for x in (block.get("labels") or [])]
        athletes = block.get("athletes") or []

        def idx_col(col_name, fallback):
            if col_name in labels:
                return labels.index(col_name)
            return fallback

        i_min = idx_col("MIN", 0)
        i_fg = idx_col("FG", 1)
        i_3pt = idx_col("3PT", 2)
        i_pts = -1
        for candidate in ("PTS",):
            if candidate in labels:
                i_pts = labels.index(candidate)

        for ath_entry in athletes:
            if ath_entry.get("didNotPlay"):
                continue
            ath = ath_entry.get("athlete") or {}
            pid_raw = ath.get("id")
            nombre = str(ath.get("displayName") or "").strip()
            headshot_url = str(((ath.get("headshot") or {}).get("href")) or "").strip()
            stats_arr = ath_entry.get("stats") or []
            if not pid_raw or not nombre or not stats_arr:
                continue

            try:
                pid = int(pid_raw)
            except Exception:
                continue
            p_key = str(pid)

            if headshot_url:
                if p_key in hist_pts and hist_pts[p_key].get("foto") != headshot_url:
                    hist_pts[p_key]["foto"] = headshot_url
                    cambio_pts = True
                if p_key in hist_3p and hist_3p[p_key].get("foto") != headshot_url:
                    hist_3p[p_key]["foto"] = headshot_url
                    cambio_3p = True

            if solo_fotos:
                continue

            min_val = stats_arr[i_min] if i_min < len(stats_arr) else ""
            if minutos_jugados_espn(min_val) <= 0.0:
                continue

            fg_str = stats_arr[i_fg] if i_fg < len(stats_arr) else "0-0"
            t3_str = stats_arr[i_3pt] if i_3pt < len(stats_arr) else "0-0"
            pts_str = stats_arr[i_pts] if (0 <= i_pts < len(stats_arr)) else "0"

            fgm, fga = parsear_hecho_o_intentado(fg_str)
            tpm, tpa = parsear_hecho_o_intentado(t3_str)
            pts, _ = parsear_hecho_o_intentado(pts_str)

            if gid not in games_pts:
                e_pts = hist_pts.setdefault(
                    p_key,
                    {"jugador": nombre, "equipo": tri, "foto": headshot_url, "ultimo_partido": fecha_txt, "juegos": []},
                )
                e_pts["jugador"] = nombre
                e_pts["equipo"] = tri
                if headshot_url:
                    e_pts["foto"] = headshot_url
                e_pts["ultimo_partido"] = fecha_mas_reciente(e_pts.get("ultimo_partido", ""), fecha_txt)
                if not any(j.get("game_id") == gid for j in e_pts["juegos"]):
                    e_pts["juegos"].append({
                        "game_id": gid,
                        "fecha": fecha_txt,
                        "pts": pts,
                        "fgm": fgm,
                        "fga": fga,
                    })
                    cambio_pts = True

            if gid not in games_3p:
                e_3p = hist_3p.setdefault(
                    p_key,
                    {"jugador": nombre, "equipo": tri, "foto": headshot_url, "ultimo_partido": fecha_txt, "juegos": []},
                )
                e_3p["jugador"] = nombre
                e_3p["equipo"] = tri
                if headshot_url:
                    e_3p["foto"] = headshot_url
                e_3p["ultimo_partido"] = fecha_mas_reciente(e_3p.get("ultimo_partido", ""), fecha_txt)
                if not any(j.get("game_id") == gid for j in e_3p["juegos"]):
                    e_3p["juegos"].append({
                        "game_id": gid,
                        "fecha": fecha_txt,
                        "tpm": tpm,
                        "tpa": tpa,
                    })
                    cambio_3p = True

    if not solo_fotos:
        if gid not in games_pts:
            for t in (away, home):
                if t:
                    tg_pts[t] = int(tg_pts.get(t, 0) or 0) + 1
            games_pts.add(gid)
            cambio_pts = True

        if gid not in games_3p:
            for t in (away, home):
                if t:
                    tg_3p[t] = int(tg_3p.get(t, 0) or 0) + 1
            games_3p.add(gid)
            cambio_3p = True

    return cambio_pts, cambio_3p


def sincronizar_historial_espn(
    hoy_local,
    games_pts,
    games_3p,
    hist_pts,
    hist_3p,
    tg_pts,
    tg_3p,
):
    cambio_pts_total = False
    cambio_3p_total = False
    procesados = 0
    faltan_fotos = any(not v.get("foto") for v in hist_3p.values()) or any(not v.get("foto") for v in hist_pts.values())

    cursor = hoy_local
    while cursor >= SEASON_START_DATE and procesados < MAX_ESPN_GAMES_PER_RUN:
        fecha_yyyymmdd = cursor.strftime("%Y%m%d")
        fecha_txt = cursor.strftime("%d/%m/%Y")
        _, _, _, finalizados = obtener_partidos_fecha_espn(fecha_yyyymmdd)

        for ev in finalizados:
            if procesados >= MAX_ESPN_GAMES_PER_RUN:
                break
            ev_id = ev.get("event_id")
            if not ev_id:
                continue
            gid = f"ESPN_{ev_id}"
            ya_procesado = gid in games_pts and gid in games_3p
            if ya_procesado and not faltan_fotos:
                continue
            try:
                c_p, c_3 = procesar_evento_espn(
                    ev_id=ev_id,
                    away=ev["away"],
                    home=ev["home"],
                    fecha_txt=fecha_txt,
                    games_pts=games_pts,
                    games_3p=games_3p,
                    hist_pts=hist_pts,
                    hist_3p=hist_3p,
                    tg_pts=tg_pts,
                    tg_3p=tg_3p,
                    solo_fotos=ya_procesado and faltan_fotos,
                )
                if c_p:
                    cambio_pts_total = True
                if c_3:
                    cambio_3p_total = True
                procesados += 1
                time.sleep(0.2)
            except Exception as e:
                print(f"Aviso evento ESPN {ev_id}: {e}")

        cursor -= timedelta(days=1)

    return cambio_pts_total, cambio_3p_total


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

        pj = len(juegos)
        tpj = int(team_games.get(eq, pj))
        if tpj <= 0 or pj <= 0:
            continue

        pct_pj = round((pj / tpj) * 100.0, 1)
        if pct_pj < 80.0:
            continue

        pts_list = [int(x.get("pts", 0)) for x in juegos]
        fgm_tot = sum(float(x.get("fgm", 0)) for x in juegos)
        fga_tot = sum(float(x.get("fga", 0)) for x in juegos)
        if fga_tot <= 0:
            continue

        fg_pct = round((fgm_tot / fga_tot) * 100.0, 1)
        if fg_pct <= 40.0:
            continue

        ppg = round(sum(pts_list) / pj, 1)
        if ppg < 14.0:
            continue

        fechas_j = [x.get("fecha", "") for x in juegos if x.get("fecha")]
        ult_pj = info.get("ultimo_partido", "")
        for f_c in fechas_j:
            ult_pj = fecha_mas_reciente(ult_pj, f_c)

        c_bajo = sum(1 for p in pts_list if p <= 14)
        c_medio = sum(1 for p in pts_list if 15 <= p <= 24)
        c_alto = sum(1 for p in pts_list if p >= 25)
        cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))
        foto_url = info.get("foto") or f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"

        elegibles.append({
            "player_id": pid,
            "foto": foto_url,
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
            "ultimo_partido": ult_pj,
            "intervalos": {
                "0-14": {"juegos": c_bajo, "pct": round((c_bajo / pj) * 100.0, 1)},
                "15-24": {"juegos": c_medio, "pct": round((c_medio / pj) * 100.0, 1)},
                "25+": {"juegos": c_alto, "pct": round((c_alto / pj) * 100.0, 1)},
            },
        })

    elegibles.sort(key=lambda x: (-x["ppg"], x["jugador"]))
    return elegibles


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

        pj = len(juegos)
        tpj = int(team_games.get(eq, pj))
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

        fechas_j = [x.get("fecha", "") for x in juegos if x.get("fecha")]
        ult_pj = info.get("ultimo_partido", "")
        for f_c in fechas_j:
            ult_pj = fecha_mas_reciente(ult_pj, f_c)

        max_t = max(tpm_list)
        freq = {str(k): sum(1 for x in tpm_list if x == k) for k in range(max_t + 1)}
        cp, cs, en = TEAM_COLORS.get(eq, ("#38bdf8", "#94a3b8", eq))
        foto_url = info.get("foto") or f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"

        elegibles.append({
            "foto": foto_url,
            "equipo": eq,
            "equipo_nombre": en,
            "juega_hoy": eq in set(equipos_hoy),
            "color_prim": cp,
            "color_sec": cs,
            "jugador": info.get("jugador", ""),
            "ultimo_partido": ult_pj,
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

    elegibles.sort(key=lambda x: (-x["prob_2"], -x["prob_1"], x["jugador"]))
    return elegibles


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

    ahora = datetime.now(TZ_LOCAL)

    sincronizar_historial_espn(
        hoy_local=ahora.date(),
        games_pts=games_pts,
        games_3p=games_3p,
        hist_pts=hist_pts,
        hist_3p=hist_3p,
        tg_pts=tg_pts,
        tg_3p=tg_3p,
    )

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
                    for side, tri in (("homeTeam", home), ("awayTeam", away)):
                        for p in bs.get(side, {}).get("players", []):
                            nombre = p.get("name", "")
                            st = p.get("statistics", {})
                            tpm = int(st.get("threePointersMade", 0) or 0)
                            tpa = int(st.get("threePointersAttempted", 0) or 0)
                            pts = int(st.get("points", 0) or 0)
                            mins = str(st.get("minutesCalculated") or "")

                            if nombre:
                                vivo_jugadores[nombre.lower()] = {
                                    "es_live": es_live,
                                    "estado_juego": status_text,
                                    "3pm_live": tpm,
                                    "3pa_live": tpa,
                                    "pts_live": pts,
                                    "min_live": mins,
                                }
                    time.sleep(0.2)
                except Exception:
                    pass
    except Exception as e:
        print(f"Aviso en vivo: {e}")

    todos_finalizados = bool(partidos_estado) and all(
        not p["es_live"] and "FINAL" in str(p["status_text"]).upper()
        for p in partidos_estado
    )
    if (not partidos_hoy) or (todos_finalizados and ahora.hour < 17):
        partidos_espn, equipos_espn, estado_espn, _ = obtener_partidos_fecha_espn(ahora.strftime("%Y%m%d"))
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

    fechas_reales = []
    for info in hist_pts.values():
        if info.get("ultimo_partido"):
            fechas_reales.append(info["ultimo_partido"])
    for info in hist_3p.values():
        if info.get("ultimo_partido"):
            fechas_reales.append(info["ultimo_partido"])
    corte_real = ""
    for f_txt in fechas_reales:
        corte_real = fecha_mas_reciente(corte_real, f_txt)

    base_pts["games_procesados"] = sorted(games_pts)
    base_pts["team_games"] = tg_pts
    base_pts["historial_jugadores"] = hist_pts
    base_pts["equipos_hoy"] = eq_sorted
    base_pts["partidos_hoy"] = partidos_hoy
    base_pts["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
    base_pts["fecha_generacion"] = ahora.strftime("%Y-%m-%d")
    base_pts["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
    if corte_real:
        base_pts["corte"] = corte_real
    base_pts["jugadores"] = recalcular_jugadores_puntos(base_pts, eq_sorted)
    with open(PUNTOS_FILE, "w", encoding="utf-8") as f:
        json.dump(base_pts, f, ensure_ascii=False)

    base_3p["games_procesados"] = sorted(games_3p)
    base_3p["team_games"] = tg_3p
    base_3p["historial_triples"] = hist_3p
    base_3p["equipos_hoy"] = eq_sorted
    base_3p["partidos_hoy"] = partidos_hoy
    base_3p["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
    base_3p["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
    if corte_real:
        base_3p["corte"] = corte_real
    base_3p["jugadores"] = recalcular_jugadores_triples(base_3p, eq_sorted)
    with open(TRIPLES_FILE, "w", encoding="utf-8") as f:
        json.dump(base_3p, f, ensure_ascii=False)

    n_live = sum(1 for x in partidos_estado if x["es_live"])
    print(
        f"Live actualizado ({live_payload['actualizado_en']}) | Juegos en vivo: {n_live} | "
        f"Partidos hoy: {len(partidos_hoy)} | Puntos elegibles: {len(base_pts.get('jugadores', []))} | "
        f"Triples elegibles: {len(base_3p.get('jugadores', []))}"
    )


if __name__ == "__main__":
    sincronizar_todo()
