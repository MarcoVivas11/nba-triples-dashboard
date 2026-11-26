from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog
import pandas as pd
import requests

TZ_LOCAL = ZoneInfo("America/Caracas")
SEASON = "2026-27"
PUNTOS_FILE = "nba_puntos.json"
TRIPLES_FILE = "nba_triples.json"
LIVE_FILE = "nba_live.json"

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


def poblar_desde_stats_oficiales(base_pts, base_3p, equipos_hoy):
    """Carga datos oficiales reales de temporada desde nba_api.stats sin inventar ni estimar."""
    try:
        stats_df = leaguedashplayerstats.LeagueDashPlayerStats(
            season=SEASON,
            season_type_all_star="Regular Season",
            timeout=30,
        ).get_data_frames()[0]
        if stats_df.empty:
            return False, False

        stats_df["EQ_NORM"] = stats_df["TEAM_ABBREVIATION"].apply(normalizar_equipo)
        stats_df = stats_df[stats_df["EQ_NORM"].isin(TEAM_COLORS.keys())].copy()
        if stats_df.empty:
            return False, False

        team_gp_map = (
            stats_df.groupby("EQ_NORM")["GP"]
            .max()
            .astype(int)
            .to_dict()
        )
        base_pts["team_games"] = dict(team_gp_map)
        base_3p["team_games"] = dict(team_gp_map)

        # Candidatos para puntos (>= 80% PJ, FG% > 40%, >= 14.0 PPG)
        cand_pts = stats_df[
            (stats_df["GP"] > 0)
            & ((stats_df["GP"] / stats_df["EQ_NORM"].map(team_gp_map)) >= 0.80)
            & ((stats_df["FG_PCT"] * 100.0) > 40.0)
            & ((stats_df["PTS"] / stats_df["GP"]) >= 14.0)
        ].copy()

        # Candidatos para triples (>= 80% PJ, >= 5.0 3PA/J)
        cand_3p = stats_df[
            (stats_df["GP"] > 0)
            & ((stats_df["GP"] / stats_df["EQ_NORM"].map(team_gp_map)) >= 0.80)
            & ((stats_df["FG3A"] / stats_df["GP"]) >= 5.0)
        ].copy()

        pids_objetivo = sorted(
            set(cand_pts["PLAYER_ID"].astype(int).tolist())
            | set(cand_3p["PLAYER_ID"].astype(int).tolist())
        )

        hist_pts = base_pts.setdefault("historial_jugadores", {})
        hist_3p = base_3p.setdefault("historial_triples", {})
        fechas_max = []

        for pid in pids_objetivo:
            fila_row = stats_df[stats_df["PLAYER_ID"] == pid].iloc[0]
            nombre = str(fila_row["PLAYER_NAME"]).strip()
            eq = str(fila_row["EQ_NORM"]).strip()

            try:
                gl = playergamelog.PlayerGameLog(
                    player_id=pid,
                    season=SEASON,
                    season_type_all_star="Regular Season",
                    timeout=30,
                ).get_data_frames()[0]
            except Exception as e:
                print(f"Aviso game log {nombre} ({pid}): {e}")
                continue

            time.sleep(0.5)
            if gl.empty:
                continue

            gl = gl.copy()
            gl["DT_REAL"] = pd.to_datetime(gl["GAME_DATE"], errors="coerce")
            gl = gl.dropna(subset=["DT_REAL"]).sort_values("DT_REAL")
            if gl.empty:
                continue

            ult_fecha = gl["DT_REAL"].max().strftime("%d/%m/%Y")
            fechas_max.append(gl["DT_REAL"].max())

            juegos_pts = []
            juegos_3p = []
            for _, g_row in gl.iterrows():
                gid = str(g_row.get("Game_ID") or g_row.get("GAME_ID") or "")
                f_txt = g_row["DT_REAL"].strftime("%d/%m/%Y")
                pts_v = int(g_row.get("PTS", 0) or 0)
                fgm_v = int(g_row.get("FGM", 0) or 0)
                fga_v = int(g_row.get("FGA", 0) or 0)
                tpm_v = int(g_row.get("FG3M", 0) or 0)
                tpa_v = int(g_row.get("FG3A", 0) or 0)

                juegos_pts.append({
                    "game_id": gid,
                    "fecha": f_txt,
                    "pts": pts_v,
                    "fgm": fgm_v,
                    "fga": fga_v,
                })
                juegos_3p.append({
                    "game_id": gid,
                    "fecha": f_txt,
                    "tpm": tpm_v,
                    "tpa": tpa_v,
                })

            p_key = str(pid)
            hist_pts[p_key] = {
                "jugador": nombre,
                "equipo": eq,
                "ultimo_partido": ult_fecha,
                "juegos": juegos_pts,
            }
            hist_3p[p_key] = {
                "jugador": nombre,
                "equipo": eq,
                "ultimo_partido": ult_fecha,
                "juegos": juegos_3p,
            }

        if fechas_max:
            corte_real = max(fechas_max).strftime("%d/%m/%Y")
            base_pts["corte"] = corte_real
            base_3p["corte"] = corte_real

        base_pts["jugadores"] = recalcular_jugadores_puntos(base_pts, equipos_hoy)
        base_3p["jugadores"] = recalcular_jugadores_triples(base_3p, equipos_hoy)
        print(
            f"Historial oficial cargado: {len(base_pts['jugadores'])} en puntos, "
            f"{len(base_3p['jugadores'])} en triples"
        )
        return True, True
    except Exception as e:
        print(f"Aviso cargando estadisticas oficiales: {e}")
        return False, False


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

        elegibles.append({
            "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png",
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

    cambio_pts = False
    cambio_3p = False

    if not base_pts.get("historial_jugadores") or not base_3p.get("historial_triples"):
        c_p, c_3 = poblar_desde_stats_oficiales(base_pts, base_3p, [])
        cambio_pts = cambio_pts or c_p
        cambio_3p = cambio_3p or c_3
        games_pts = set(base_pts.get("games_procesados", []))
        games_3p = set(base_3p.get("games_procesados", []))
        hist_pts = base_pts.get("historial_jugadores", {})
        hist_3p = base_3p.get("historial_triples", {})
        tg_pts = base_pts.get("team_games", {})
        tg_3p = base_3p.get("team_games", {})

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
                                        {"jugador": nombre, "equipo": tri, "ultimo_partido": fecha_txt, "juegos": []},
                                    )
                                    e_pts["jugador"] = nombre
                                    e_pts["equipo"] = tri
                                    e_pts["ultimo_partido"] = fecha_mas_reciente(
                                        e_pts.get("ultimo_partido", ""), fecha_txt
                                    )
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
                                        {"jugador": nombre, "equipo": tri, "ultimo_partido": fecha_txt, "juegos": []},
                                    )
                                    e_3p["jugador"] = nombre
                                    e_3p["equipo"] = tri
                                    e_3p["ultimo_partido"] = fecha_mas_reciente(
                                        e_3p.get("ultimo_partido", ""), fecha_txt
                                    )
                                    if not any(j.get("game_id") == gid for j in e_3p["juegos"]):
                                        e_3p["juegos"].append({
                                            "game_id": gid,
                                            "fecha": fecha_txt,
                                            "tpm": tpm,
                                            "tpa": tpa,
                                        })
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

    base_3p["games_procesados"] = sorted(games_3p)
    base_3p["team_games"] = tg_3p
    base_3p["historial_triples"] = hist_3p
    base_3p["equipos_hoy"] = eq_sorted
    base_3p["partidos_hoy"] = partidos_hoy
    base_3p["fecha_hoy"] = ahora.strftime("%d/%m/%Y")
    base_3p["generado"] = ahora.strftime("%d/%m/%Y %I:%M %p")
    base_3p["corte"] = base_3p.get("corte") or ahora.strftime("%d/%m/%Y")
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
