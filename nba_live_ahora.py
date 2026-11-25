from datetime import datetime
import json
import os
import time
from zoneinfo import ZoneInfo

from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import leaguegamelog

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


def obtener_vivo():
    vivo_jugadores = {}
    partidos_estado = []
    equipos_hoy = set()
    partidos_hoy = []

    try:
        sb = scoreboard.ScoreBoard()
        data = sb.get_dict()
        games = data.get("scoreboard", {}).get("games", [])
        for g in games:
            gid = g.get("gameId")
            status_text = str(g.get("gameStatusText", "")).strip()
            game_status = g.get("gameStatus")  # 1=previa, 2=en vivo, 3=finalizado
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
        "equipos_hoy": sorted(equipos_hoy),
        "partidos_hoy": partidos_hoy,
        "partidos": partidos_estado,
        "jugadores_live": vivo_jugadores,
    }


def necesita_actualizar_puntos():
    if not os.path.exists(PUNTOS_FILE):
        return True
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    try:
        with open(PUNTOS_FILE, "r", encoding="utf-8") as f:
            prev = json.load(f)
        fecha_prev = prev.get("fecha_generacion", "")
        hoy_str = datetime.now(TZ_LOCAL).strftime("%Y-%m-%d")
        return fecha_prev != hoy_str
    except Exception:
        return True


def generar_puntos_jugadores(equipos_hoy, partidos_hoy):
    team_df = leaguegamelog.LeagueGameLog(
        season=SEASON,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="T",
    ).get_data_frames()[0]

    time.sleep(0.6)

    player_df = leaguegamelog.LeagueGameLog(
        season=SEASON,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P",
    ).get_data_frames()[0]

    if team_df.empty or player_df.empty:
        raise RuntimeError("LeagueGameLog devolvió tablas vacías")

    team_games_count = team_df.groupby("TEAM_ABBREVIATION")["GAME_ID"].nunique().to_dict()
    corte_str = ""
    if "GAME_DATE" in player_df.columns and not player_df["GAME_DATE"].empty:
        fechas_dt = player_df["GAME_DATE"].astype(str).str[:10]
        max_f = fechas_dt.max()
        try:
            corte_str = datetime.strptime(max_f, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            corte_str = max_f

    jugadores_elegibles = []
    for (pid, pname, team_abbr), grp in player_df.groupby(
        ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"], dropna=False
    ):
        team_games = int(team_games_count.get(team_abbr, 0))
        pj = int(grp["GAME_ID"].nunique())
        if team_games <= 0 or pj <= 0:
            continue

        pct_pj = round((pj / team_games) * 100.0, 1)
        if pct_pj < 80.0:
            continue

        pts_series = grp["PTS"].fillna(0).astype(int)
        fgm_total = float(grp["FGM"].fillna(0).sum()) if "FGM" in grp.columns else 0.0
        fga_total = float(grp["FGA"].fillna(0).sum()) if "FGA" in grp.columns else 0.0
        fg_pct = round((fgm_total / fga_total) * 100.0, 1) if fga_total > 0 else 0.0
        if fg_pct <= 40.0:
            continue

        ppg = round(float(pts_series.mean()), 1)
        if ppg < 14.0:
            continue

        c_bajo = int((pts_series <= 14).sum())
        c_medio = int(((pts_series >= 15) & (pts_series <= 24)).sum())
        c_alto = int((pts_series >= 25).sum())

        p_bajo = round((c_bajo / pj) * 100.0, 1)
        p_medio = round((c_medio / pj) * 100.0, 1)
        p_alto = round((c_alto / pj) * 100.0, 1)

        ult_fecha = ""
        if "GAME_DATE" in grp.columns and not grp["GAME_DATE"].empty:
            ult_raw = str(grp.sort_values("GAME_DATE").iloc[-1]["GAME_DATE"])[:10]
            try:
                ult_fecha = datetime.strptime(ult_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                ult_fecha = ult_raw

        c_prim, c_sec, team_name = TEAM_COLORS.get(
            team_abbr, ("#38bdf8", "#94a3b8", team_abbr)
        )

        jugadores_elegibles.append({
            "player_id": int(pid),
            "foto": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{int(pid)}.png",
            "jugador": str(pname),
            "equipo": str(team_abbr),
            "equipo_nombre": team_name,
            "color_prim": c_prim,
            "color_sec": c_sec,
            "juega_hoy": str(team_abbr) in set(equipos_hoy),
            "pj": pj,
            "team_pj": team_games,
            "pj_str": f"{pj}/{team_games}",
            "pct_pj": pct_pj,
            "fg_pct": fg_pct,
            "ppg": ppg,
            "max_pts": int(pts_series.max()),
            "ultimo_partido": ult_fecha,
            "intervalos": {
                "0-14": {"juegos": c_bajo, "pct": p_bajo},
                "15-24": {"juegos": c_medio, "pct": p_medio},
                "25+": {"juegos": c_alto, "pct": p_alto},
            },
        })

    jugadores_elegibles.sort(key=lambda x: (-x["ppg"], x["jugador"]))
    ahora = datetime.now(TZ_LOCAL)

    return {
        "season": SEASON,
        "corte": corte_str,
        "fecha_hoy": ahora.strftime("%d/%m/%Y"),
        "fecha_generacion": ahora.strftime("%Y-%m-%d"),
        "generado": ahora.strftime("%d/%m/%Y %I:%M %p"),
        "criterios": {
            "min_pct_pj": 80.0,
            "min_fg_pct": 40.0,
            "min_ppg": 14.0,
            "rangos": ["0-14", "15-24", "25+"],
        },
        "equipos_hoy": equipos_hoy,
        "partidos_hoy": partidos_hoy,
        "jugadores": jugadores_elegibles,
    }


if __name__ == "__main__":
    live_payload = obtener_vivo()
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(live_payload, f, ensure_ascii=False)
    n_live = sum(1 for x in live_payload["partidos"] if x["es_live"])
    print(f"Live actualizado ({live_payload['actualizado_en']}) | Juegos en vivo: {n_live}")

    if necesita_actualizar_puntos():
        try:
            pts_payload = generar_puntos_jugadores(
                live_payload.get("equipos_hoy", []),
                live_payload.get("partidos_hoy", []),
            )
            with open(PUNTOS_FILE, "w", encoding="utf-8") as f:
                json.dump(pts_payload, f, ensure_ascii=False)
            print(f"Puntos por jugador actualizados: {len(pts_payload['jugadores'])} elegibles")
        except Exception as e:
            print(f"Aviso puntos por jugador: {e}")
