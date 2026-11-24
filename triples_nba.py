from datetime import datetime
from zoneinfo import ZoneInfo

TZ_LOCAL = ZoneInfo("America/Caracas")
import json
from pathlib import Path
import time
import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog, scoreboardv2

SEASON = "2026-27"
TEAM_COLORS = {
    "ATL": ("#E03A3E", "#C1D32F", "Atlanta Hawks"), "BOS": ("#007A33", "#BA9653", "Boston Celtics"),
    "BKN": ("#111827", "#9CA3AF", "Brooklyn Nets"), "CHA": ("#1D1160", "#00788C", "Charlotte Hornets"),
    "CHI": ("#CE1141", "#1F2937", "Chicago Bulls"), "CLE": ("#860038", "#FDBB30", "Cleveland Cavaliers"),
    "DAL": ("#00538C", "#B8C4CA", "Dallas Mavericks"), "DEN": ("#0E2240", "#FEC524", "Denver Nuggets"),
    "DET": ("#C8102E", "#1D42BA", "Detroit Pistons"), "GSW": ("#1D428A", "#FFC72C", "Golden State Warriors"),
    "HOU": ("#CE1141", "#9CA3AF", "Houston Rockets"), "IND": ("#002D62", "#FDBB30", "Indiana Pacers"),
    "LAC": ("#C8102E", "#1D428A", "LA Clippers"), "LAL": ("#552583", "#FDB927", "Los Angeles Lakers"),
    "MEM": ("#5D76A9", "#12173F", "Memphis Grizzlies"), "MIA": ("#98002E", "#F9A01B", "Miami Heat"),
    "MIL": ("#00471B", "#EEE1C6", "Milwaukee Bucks"), "MIN": ("#0C2340", "#78BE20", "Minnesota Timberwolves"),
    "NOP": ("#0C2340", "#C8102E", "New Orleans Pelicans"), "NYK": ("#006BB6", "#F58426", "New York Knicks"),
    "OKC": ("#007AC1", "#EF3B24", "Oklahoma City Thunder"), "ORL": ("#0077C0", "#C4CED4", "Orlando Magic"),
    "PHI": ("#006BB6", "#ED174C", "Philadelphia 76ers"), "PHX": ("#1D1160", "#E56020", "Phoenix Suns"),
    "POR": ("#E03A3E", "#9CA3AF", "Portland Trail Blazers"), "SAC": ("#5A2D81", "#63727A", "Sacramento Kings"),
    "SAS": ("#1F2937", "#C4CED4", "San Antonio Spurs"), "TOR": ("#CE1141", "#A1A1A4", "Toronto Raptors"),
    "UTA": ("#002B5C", "#F9A01B", "Utah Jazz"), "WAS": ("#002B5C", "#E31837", "Washington Wizards"),
}


def obtener_equipos_jornada_hoy():
    hoy_str = datetime.now(TZ_LOCAL).strftime("%m/%d/%Y")
    equipos_hoy = set()
    partidos_hoy = []
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=hoy_str)
        frames = sb.get_data_frames()
        game_header = frames[0] if len(frames) > 0 else pd.DataFrame()
        line_score = frames[1] if len(frames) > 1 else pd.DataFrame()

        if not line_score.empty and "TEAM_ABBREVIATION" in line_score.columns:
            for ab in line_score["TEAM_ABBREVIATION"].dropna().unique():
                equipos_hoy.add(str(ab).strip())

        if not game_header.empty and not line_score.empty:
            for gid, grp in line_score.groupby("GAME_ID"):
                abs_list = [str(x).strip() for x in grp["TEAM_ABBREVIATION"].dropna().tolist()]
                if len(abs_list) >= 2:
                    partidos_hoy.append(f"{abs_list[0]} @ {abs_list[1]}")
    except Exception as e:
        print(f"Aviso jornada del dia: {e}")
    return sorted(equipos_hoy), partidos_hoy


print("Descargando estadisticas generales y jornada del dia...")
equipos_hoy, partidos_hoy = obtener_equipos_jornada_hoy()
set_hoy = set(equipos_hoy)

stats_df = leaguedashplayerstats.LeagueDashPlayerStats(
    season=SEASON,
    season_type_all_star="Regular Season"
).get_data_frames()[0]

team_gp = stats_df.groupby("TEAM_ID")["GP"].max().rename("TEAM_GP")
df = stats_df.merge(team_gp, on="TEAM_ID")
df["GP_PCT"] = df["GP"] / df["TEAM_GP"]
df["3PA_PG"] = df["FG3A"] / df["GP"]

elegibles = df[(df["GP_PCT"] >= 0.80) & (df["3PA_PG"] >= 5.0)].copy()
top3 = (
    elegibles.sort_values(["TEAM_ABBREVIATION", "3PA_PG"], ascending=[True, False])
    .groupby("TEAM_ABBREVIATION")
    .head(3)
)

filas_csv, registros_json, fechas_partidos = [], [], []
print(f"Procesando game logs de {len(top3)} jugadores...")

for _, row in top3.iterrows():
    pid = int(row["PLAYER_ID"])
    try:
        gl = playergamelog.PlayerGameLog(
            player_id=pid,
            season=SEASON,
            season_type_all_star="Regular Season"
        ).get_data_frames()[0]
    except Exception as e:
        print(f"Error con {row['PLAYER_NAME']}: {e}")
        continue

    time.sleep(0.7)
    if gl.empty:
        continue

    f_dt = pd.to_datetime(gl["GAME_DATE"], errors="coerce").dropna()
    ult = "N/D"
    if not f_dt.empty:
        mx_dt = f_dt.max()
        fechas_partidos.append(mx_dt)
        ult = mx_dt.strftime("%d/%m/%Y")

    eq = str(row["TEAM_ABBREVIATION"]).strip()
    juega_hoy = eq in set_hoy
    cp, cs, neq = TEAM_COLORS.get(eq, ("#38bdf8", "#22c55e", eq))
    foto = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"

    fg3m_serie = gl["FG3M"].astype(int)
    total_gl = max(1, len(fg3m_serie))
    max3 = int(fg3m_serie.max())
    freq = {str(k): int((fg3m_serie == k).sum()) for k in range(0, max3 + 1)}

    prob_1 = round(float((fg3m_serie >= 1).sum()) / total_gl * 100, 1)
    prob_2 = round(float((fg3m_serie >= 2).sum()) / total_gl * 100, 1)
    prob_3 = round(float((fg3m_serie >= 3).sum()) / total_gl * 100, 1)

    pj, pjeq = int(row["GP"]), int(row["TEAM_GP"])
    pct_pj = round(float(row["GP_PCT"]) * 100, 1)
    tpa = round(float(row["3PA_PG"]), 1)
    tpm = round(float(row["FG3M"] / row["GP"]), 1)
    pct3 = (
        round(float(row["FG3_PCT"]) * 100, 1)
        if "FG3_PCT" in row and pd.notna(row["FG3_PCT"])
        else round((tpm / tpa) * 100, 1)
    )

    f_row = {
        "Juega_Hoy": "SI" if juega_hoy else "NO",
        "Equipo": eq,
        "Jugador": row["PLAYER_NAME"],
        "Ultimo_Partido": ult,
        "PJ": f"{pj}/{pjeq}",
        "3PA_PJ": tpa,
        "3PM_PJ": tpm,
        "3P_Pct": pct3,
        "Prob_1T_Pct": prob_1,
        "Prob_2T_Pct": prob_2,
        "Prob_3T_Pct": prob_3,
        "Max_3PM": max3,
        "Frecuencia_Aciertos": " | ".join([f"{k}T: {freq[str(k)]}PJ" for k in range(0, max3 + 1)]),
    }
    for k in range(0, 12):
        f_row[f"{k}_aciertos"] = freq.get(str(k), 0)
    filas_csv.append(f_row)

    registros_json.append({
        "foto": foto,
        "equipo": eq,
        "equipo_nombre": neq,
        "juega_hoy": juega_hoy,
        "color_prim": cp,
        "color_sec": cs,
        "jugador": row["PLAYER_NAME"],
        "ultimo_partido": ult,
        "pj_str": f"{pj}/{pjeq}",
        "pct_pj": pct_pj,
        "tpa_pj": tpa,
        "tpm_pj": tpm,
        "pct_3p": pct3,
        "prob_1": prob_1,
        "prob_2": prob_2,
        "prob_3": prob_3,
        "max_3pm": max3,
        "freq": freq,
    })

corte = max(fechas_partidos).strftime("%d/%m/%Y") if fechas_partidos else "Sin datos"
gen = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y %I:%M %p")
fecha_hoy_ui = datetime.now(TZ_LOCAL).strftime("%d/%m/%Y")

pd.DataFrame(filas_csv).to_csv("nba_2026_27_triples.csv", index=False, encoding="utf-8-sig")

meta_payload = {
    "season": SEASON,
    "corte": corte,
    "generado": gen,
    "fecha_hoy": fecha_hoy_ui,
    "equipos_hoy": equipos_hoy,
    "partidos_hoy": partidos_hoy,
    "jugadores": registros_json,
}
with open("nba_2026_27_datos.json", "w", encoding="utf-8") as fj:
    json.dump(meta_payload, fj, ensure_ascii=False)

html_code = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><title>NBA __S__ - Jornada y Probabilidades Triples</title>
<style>
body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#f8fafc;padding:22px}
.wrap{max-width:1420px;margin:0 auto}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;padding-bottom:14px;border-bottom:1px solid #334155;margin-bottom:16px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.bc{background:rgba(34,197,94,.16);border:1px solid #22c55e;color:#4ade80;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
.bg{background:rgba(56,189,248,.14);border:1px solid #38bdf8;color:#7dd3fc;padding:4px 10px;border-radius:999px;font-size:12px}
.bh{background:rgba(250,204,21,.15);border:1px solid #eab308;color:#fde047;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600}
.blive-info{background:rgba(220,38,38,.18);border:1px solid #ef4444;color:#fca5a5;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
.live-badge{display:inline-block;background:#dc2626;color:#ffffff;font-size:10px;font-weight:800;letter-spacing:.5px;padding:2px 7px;border-radius:5px;margin-left:6px;vertical-align:middle;box-shadow:0 0 8px rgba(220,38,38,.65)}
.live-stat{display:inline-block;background:rgba(220,38,38,.2);border:1px solid #f87171;color:#fecaca;font-size:11px;font-weight:700;padding:2px 7px;border-radius:6px;margin-left:6px}
button{background:#38bdf8;color:#061322;border:none;padding:8px 13px;border-radius:8px;font-weight:600;cursor:pointer}
button.sec{background:#1e293b;color:#f8fafc;border:1px solid #334155}
.slate-box{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:12px 14px;margin-bottom:16px}
.slate-title{font-size:12px;font-weight:700;color:#fde047;text-transform:uppercase;margin-bottom:8px}
.match-list{display:flex;flex-wrap:wrap;gap:7px}
.match-pill{background:#0b1120;border:1px solid #334155;padding:4px 9px;border-radius:7px;font-size:12px;color:#e2e8f0}
.match-live{border-color:#ef4444;background:rgba(220,38,38,.12);color:#fecaca;font-weight:700}
.recs{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px;margin-bottom:16px}
.rec-card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:14px}
.rec-head{font-size:13px;font-weight:700;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}
.rec-item{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 9px;background:#0b1120;border-radius:8px;margin-bottom:6px;font-size:12px;cursor:pointer;border:1px solid transparent}
.rec-item:hover{border-color:#38bdf8}
.prob-tag{font-weight:700;padding:2px 7px;border-radius:999px;background:rgba(34,197,94,.18);color:#4ade80;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:13px}
.kv{font-size:24px;font-weight:700;color:#38bdf8;margin-top:4px}
.ctrl{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:10px;background:#1e293b;padding:12px;border-radius:12px;border:1px solid #334155;margin-bottom:16px}
input,select{width:100%;padding:8px 10px;border-radius:8px;border:1px solid #334155;background:#0b1120;color:#f8fafc}
.tbl{background:#1e293b;border:1px solid #334155;border-radius:12px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0b1120;color:#94a3b8;text-align:left;padding:10px 10px;border-bottom:1px solid #334155;white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid rgba(51,65,85,.55);vertical-align:middle}
tr:hover td{background:rgba(56,189,248,.07);cursor:pointer}
.pcell{display:flex;align-items:center;gap:10px}
.ava{width:44px;height:34px;object-fit:cover;object-position:top;border-radius:8px;background:#0b1120}
.tpill{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:7px;font-weight:700;font-size:12px;color:#fff}
.dot{width:8px;height:8px;border-radius:50%}
.mpill{display:inline-block;padding:3px 8px;border-radius:999px;font-weight:700;font-size:12px;color:#fff}
.today-dot{display:inline-block;padding:2px 6px;border-radius:6px;font-size:10px;font-weight:700;background:rgba(250,204,21,.2);color:#fde047;margin-left:6px}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{font-size:11px;padding:2px 6px;border-radius:5px;background:#0b1120;border:1px solid #334155}
.bgm{display:none;position:fixed;inset:0;background:rgba(2,6,23,.8);align-items:center;justify-content:center;padding:20px;z-index:50}
.mod{background:#1e293b;border:1px solid #334155;border-radius:14px;max-width:680px;width:100%;overflow:hidden}
.mban{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;color:#fff}
.mfoto{width:78px;height:58px;object-fit:cover;object-position:top;border-radius:10px;border:2px solid rgba(255,255,255,.35)}
.mbody{padding:16px 20px}
.live-box-modal{background:#0b1120;border:1px solid #ef4444;border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:12px;color:#fecaca}
.brow{display:grid;grid-template-columns:76px 1fr 56px;align-items:center;gap:10px;margin:7px 0;font-size:12px}
.btrk{height:14px;background:#0b1120;border-radius:6px;overflow:hidden}
.bfil{height:100%;border-radius:6px}
@media (max-width:900px){.ctrl{grid-template-columns:1fr}}
@media print{body{background:#fff;color:#000;padding:0}.ctrl,.np,.slate-box,.recs{display:none}.kpi,.tbl{background:#fff;border:1px solid #ccc}td,th,.chip,.kv,.bc,.bg,.bh,.blive-info{color:#000;background:#f8fafc}}
</style></head><body><div class="wrap">
<header><div><h1 style="margin:0;font-size:21px">NBA __S__ - Jornada del Dia y Probabilidad de Triples (1T / 2T / 3T)</h1>
<div style="color:#94a3b8;font-size:13px;margin-top:4px">Base: >= 80% PJ del equipo y >= 5.0 3PA/J · Presiona F5 para leer lo ultimo en nba_live.json</div>
<div class="badges">
  <span class="bc">Fecha de corte oficial NBA: __C__</span>
  <span class="bh">Jornada del dia: __HOY__</span>
  <span class="bg">Generado: __G__</span>
  <span class="blive-info" id="liveBadgeHeader">Live: esperando nba_live.json</span>
</div></div>
<div class="np" style="display:flex;gap:8px"><button class="sec" onclick="resetF()">Limpiar filtros</button><button onclick="window.print()">Imprimir / PDF</button></div></header>

<section class="slate-box" id="slateBox"></section>
<section class="recs" id="recsBox"></section>
<section class="kpis" id="kpis"></section>

<section class="ctrl">
  <input id="q" placeholder="Buscar jugador o equipo..." oninput="render()">
  <select id="soloHoy" onchange="render()">
    <option value="hoy">Jornada de hoy (recomendado)</option>
    <option value="todos">Todos los jugadores elegibles</option>
  </select>
  <select id="eq" onchange="render()"><option value="">Todos los equipos</option></select>
  <select id="ord" onchange="render()">
    <option value="p2">Mayor Prob. 2+ triples</option>
    <option value="p1">Mayor Prob. 1+ triple</option>
    <option value="p3">Mayor Prob. 3+ triples</option>
    <option value="tpa">Mayor volumen (3PA/J)</option>
    <option value="abc">Equipo A-Z</option>
  </select>
</section>

<section class="tbl"><table><thead><tr>
  <th>Equipo</th><th>Jugador</th><th>PJ</th><th>3PA/J</th><th>3PM/J</th>
  <th>Prob. 1T+</th><th>Prob. 2T+</th><th>Prob. 3T+</th><th>Max</th><th>Frecuencia</th>
</tr></thead><tbody id="tb"></tbody></table></section></div>

<div class="bgm" id="bgM" onclick="if(event.target.id==='bgM')this.style.display='none'"><div class="mod" id="modBox"><div class="mban" id="mBan"><div style="display:flex;align-items:center;gap:12px"><img id="mFoto" class="mfoto" onerror="this.style.visibility='hidden'"><div><h2 id="mTit" style="margin:0;font-size:18px"></h2><div id="mSub" style="font-size:12px;margin-top:3px"></div></div></div><button class="sec" onclick="document.getElementById('bgM').style.display='none'">Cerrar</button></div><div class="mbody" id="mBar"></div></div></div>

<script>
const META = __META__;
const DATA = META.jugadores || [];
const HAY_HOY = DATA.some(d => d.juega_hoy);
let LIVE_MAP = {};
let LIVE_PARTIDOS = [];
let LIVE_ACTUALIZADO = '';

if (!HAY_HOY) {
  document.getElementById('soloHoy').value = 'todos';
}

function getLiveJugador(nombre) {
  return LIVE_MAP[(nombre || '').toLowerCase()] || null;
}

function badgeLiveHtml(info) {
  if (!info) return '';
  const tagLive = info.es_live ? '<span class="live-badge">LIVE</span>' : '';
  const stat3p = `<span class="live-stat">${info['3pm_live']}/${info['3pa_live']} 3P</span>`;
  return tagLive + stat3p;
}

function renderSlate() {
  const box = document.getElementById('slateBox');
  const listaPartidos = LIVE_PARTIDOS.length ? LIVE_PARTIDOS : (META.partidos_hoy || []).map(m => ({ matchup: m, status_text: '', es_live: false }));
  if (listaPartidos.length) {
    box.innerHTML = `<div class="slate-title">Partidos del dia (${META.fecha_hoy}) — ${listaPartidos.length} encuentros</div>
      <div class="match-list">${listaPartidos.map(m => {
        const cls = m.es_live ? 'match-pill match-live' : 'match-pill';
        const liveTxt = m.es_live ? ' <span class="live-badge">LIVE</span>' : '';
        const est = m.status_text ? ` · ${m.status_text}` : '';
        return `<span class="${cls}">${m.matchup}${est}${liveTxt}</span>`;
      }).join('')}</div>`;
  } else {
    box.innerHTML = `<div class="slate-title">Jornada (${META.fecha_hoy})</div>
      <div style="font-size:12px;color:#94a3b8;">No se detectaron encuentros en el calendario del dia o el servidor aun no publica la cartelera; se muestra el universo completo de jugadores elegibles.</div>`;
  }
}

function scoreCandidato(d, metaTriples) {
  const prob = metaTriples === 1 ? d.prob_1 : (metaTriples === 2 ? d.prob_2 : d.prob_3);
  return prob + (d.tpa_pj * 1.5);
}

function abrirModalJugador(d) {
  const lv = getLiveJugador(d.jugador);
  document.getElementById('mBan').style.background = `linear-gradient(135deg,${d.color_prim},#0f172a 125%)`;
  document.getElementById('modBox').style.borderColor = d.color_prim;
  const f = document.getElementById('mFoto');
  f.style.visibility = 'visible';
  f.src = d.foto;
  document.getElementById('mTit').innerHTML = `${d.jugador}${lv && lv.es_live ? '<span class="live-badge">LIVE</span>' : ''}`;
  document.getElementById('mSub').textContent = `${d.equipo_nombre} (${d.equipo}) · Prob 1T+: ${d.prob_1}% · 2T+: ${d.prob_2}% · 3T+: ${d.prob_3}% · Ult. PJ: ${d.ultimo_partido}`;
  const ent = Object.entries(d.freq);
  const mx = Math.max(1, ...ent.map(([, v]) => v));
  const liveBox = lv
    ? `<div class="live-box-modal"><strong>${lv.es_live ? 'EN VIVO' : 'JUEGO DE HOY'} (${lv.estado_juego || 'Activo'}):</strong> Triples encestados/lanzados: <strong>${lv['3pm_live']} / ${lv['3pa_live']}</strong> · Puntos: <strong>${lv.pts_live}</strong></div>`
    : '';
  document.getElementById('mBar').innerHTML = liveBox + ent.map(([k, v]) => `<div class="brow"><div><strong>${k}</strong> triple${k==='1'?'':'s'}</div><div class="btrk"><div class="bfil" style="width:${Math.round(v/mx*100)}%;background:linear-gradient(90deg,${d.color_prim},${d.color_sec})"></div></div><div style="text-align:right"><strong>${v}</strong> PJ</div></div>`).join('');
  document.getElementById('bgM').style.display = 'flex';
}

function renderRecomendaciones(poolBase) {
  const base = poolBase.length ? poolBase : DATA;
  const config = [
    { meta: 1, titulo: 'Top 5 Confiables — 1+ Triple', campo: 'prob_1' },
    { meta: 2, titulo: 'Top 5 Confiables — 2+ Triples', campo: 'prob_2' },
    { meta: 3, titulo: 'Top 5 Confiables — Max 3+ Triples', campo: 'prob_3' }
  ];
  document.getElementById('recsBox').innerHTML = config.map(c => {
    const top = [...base]
      .sort((a, b) => scoreCandidato(b, c.meta) - scoreCandidato(a, c.meta))
      .slice(0, 5);
    const items = top.map((d, i) => {
      const lv = getLiveJugador(d.jugador);
      return `<div class="rec-item" data-idx="${i}" data-meta="${c.meta}">
        <div>
          <strong>#${i+1} ${d.jugador}</strong>
          <span style="color:#94a3b8">(${d.equipo} · ${d.tpa_pj} 3PA/J)</span>
          ${badgeLiveHtml(lv)}
        </div>
        <span class="prob-tag">${d[c.campo]}%</span>
      </div>`;
    }).join('');
    return `<div class="rec-card"><div class="rec-head"><span>${c.titulo}</span><span style="font-size:11px;color:#94a3b8">Prob. historica</span></div>${items}</div>`;
  }).join('');

  document.querySelectorAll('.rec-item').forEach(el => {
    const meta = Number(el.getAttribute('data-meta'));
    const idx = Number(el.getAttribute('data-idx'));
    const listaOrdenada = [...base].sort((a, b) => scoreCandidato(b, meta) - scoreCandidato(a, meta));
    el.onclick = () => abrirModalJugador(listaOrdenada[idx]);
  });
}

[...new Set(DATA.map(d => d.equipo))].sort().forEach(e => {
  const info = DATA.find(x => x.equipo === e);
  const o = document.createElement('option');
  o.value = e;
  o.textContent = e + ' - ' + (info ? info.equipo_nombre : e);
  document.getElementById('eq').appendChild(o);
});

function resetF() {
  document.getElementById('q').value = '';
  document.getElementById('eq').value = '';
  document.getElementById('soloHoy').value = HAY_HOY ? 'hoy' : 'todos';
  document.getElementById('ord').value = 'p2';
  render();
}

function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const soloHoy = document.getElementById('soloHoy').value;
  const eq = document.getElementById('eq').value;
  const ord = document.getElementById('ord').value;

  const poolHoy = HAY_HOY ? DATA.filter(d => d.juega_hoy) : DATA;
  renderSlate();
  renderRecomendaciones(poolHoy);

  let L = DATA.filter(d =>
    (soloHoy !== 'hoy' || !HAY_HOY || d.juega_hoy) &&
    (!eq || d.equipo === eq) &&
    (!q || d.jugador.toLowerCase().includes(q) || d.equipo.toLowerCase().includes(q) || d.equipo_nombre.toLowerCase().includes(q))
  );

  const cmp = {
    p2: (a, b) => b.prob_2 - a.prob_2 || b.prob_1 - a.prob_1,
    p1: (a, b) => b.prob_1 - a.prob_1 || b.prob_2 - a.prob_2,
    p3: (a, b) => b.prob_3 - a.prob_3 || b.prob_2 - a.prob_2,
    tpa: (a, b) => b.tpa_pj - a.tpa_pj,
    abc: (a, b) => a.equipo.localeCompare(b.equipo) || b.prob_2 - a.prob_2
  };
  L.sort(cmp[ord] || cmp.p2);

  const n = L.length;
  const avgP2 = n ? (L.reduce((s, d) => s + d.prob_2, 0) / n).toFixed(1) : '0.0';
  const avgP3 = n ? (L.reduce((s, d) => s + d.prob_3, 0) / n).toFixed(1) : '0.0';
  const maxT = n ? Math.max(...L.map(d => d.max_3pm)) : 0;

  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div style="font-size:11px;color:#94a3b8">JUGADORES EN VISTA</div><div class="kv">${n}</div></div>
    <div class="kpi"><div style="font-size:11px;color:#94a3b8">PROB. PROMEDIO 2+ TRIPLES</div><div class="kv">${avgP2}%</div></div>
    <div class="kpi"><div style="font-size:11px;color:#94a3b8">PROB. PROMEDIO 3+ TRIPLES</div><div class="kv">${avgP3}%</div></div>
    <div class="kpi"><div style="font-size:11px;color:#94a3b8">MAXIMO EN UN JUEGO</div><div class="kv">${maxT}</div></div>`;

  const tb = document.getElementById('tb');
  tb.innerHTML = '';
  L.forEach(d => {
    const lv = getLiveJugador(d.jugador);
    const chips = Object.entries(d.freq).map(([k, v]) => `<span class="chip" style="border-color:${d.color_prim}66"><strong style="color:${d.color_sec}">${k}T:</strong> ${v}</span>`).join('');
    const tr = document.createElement('tr');
    tr.onclick = () => abrirModalJugador(d);
    tr.innerHTML = `
      <td><span class="tpill" style="background:linear-gradient(135deg,${d.color_prim},#0f172a 140%)"><span class="dot" style="background:${d.color_sec}"></span>${d.equipo}</span></td>
      <td><div class="pcell"><img class="ava" src="${d.foto}" style="border:2px solid ${d.color_prim}" onerror="this.style.display='none'"><div>
        <strong>${d.jugador}</strong>
        ${d.juega_hoy ? '<span class="today-dot">HOY</span>' : ''}
        ${badgeLiveHtml(lv)}
        <div style="font-size:11px;color:#94a3b8">${d.equipo_nombre} · Ult. PJ: ${d.ultimo_partido}</div>
      </div></div></td>
      <td>${d.pj_str} <span style="color:#94a3b8">(${d.pct_pj}%)</span></td>
      <td>${d.tpa_pj.toFixed(1)}</td>
      <td>${d.tpm_pj.toFixed(1)}</td>
      <td><strong>${d.prob_1}%</strong></td>
      <td><strong>${d.prob_2}%</strong></td>
      <td><strong>${d.prob_3}%</strong></td>
      <td><span class="mpill" style="background:${d.color_prim};border:1px solid ${d.color_sec}">${d.max_3pm}</span></td>
      <td><div class="chips">${chips}</div></td>`;
    tb.appendChild(tr);
  });
}

async function cargarLiveAlRefrescar() {
  try {
    const resp = await fetch('nba_live.json?v=' + Date.now(), { cache: 'no-store' });
    if (!resp.ok) return;
    const j = await resp.json();
    LIVE_MAP = j.jugadores_live || {};
    LIVE_PARTIDOS = j.partidos || [];
    LIVE_ACTUALIZADO = j.actualizado_en || '';
    const activos = LIVE_PARTIDOS.filter(p => p.es_live).length;
    const hdr = document.getElementById('liveBadgeHeader');
    if (hdr) {
      hdr.innerHTML = activos > 0
        ? `<span class="live-badge" style="margin-left:0;margin-right:5px">LIVE</span>${activos} en juego · Sync: ${LIVE_ACTUALIZADO}`
        : `Live sync: ${LIVE_ACTUALIZADO || 'sin juegos activos'}`;
    }
    render();
  } catch (e) {
    // Si se abre por file:// sin servidor local, permanece en modo estatico
  }
}

renderSlate();
render();
cargarLiveAlRefrescar();
</script></body></html>"""

final_html = (
    html_code
    .replace("__S__", SEASON)
    .replace("__C__", corte)
    .replace("__HOY__", fecha_hoy_ui)
    .replace("__G__", gen)
    .replace("__META__", json.dumps(meta_payload, ensure_ascii=False))
)
Path("nba_2026_27_dashboard_junta.html").write_text(final_html, encoding="utf-8")
print(f"Listo! Corte NBA: {corte} | Equipos hoy: {len(equipos_hoy)} | Generado: {gen}")
Path("index.html").write_text(final_html, encoding="utf-8")