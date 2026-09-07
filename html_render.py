"""Renders board.html: a single self-contained file with Pool / My Roster /
Budget tabs. All data is embedded as a JSON blob and rendered/sorted/
filtered client-side with vanilla JS - no server, no CDN dependency, so it
still works offline once generated.

Called by both build_board.py (Phase 1, no live state) and live_tracker.py
(Phase 2, regenerates the same file each poll with live state attached).
"""

import json
from datetime import datetime, timezone

from board_data import BoardData
from config import LeagueConfig


def _value_display(p: dict) -> str:
    if p.get("dynasty_value") is not None:
        return f"${round(p['dynasty_value']):,}"
    if p.get("fp_idp_rank") is not None:
        tier = p.get("fp_idp_tier")
        return f"IDP ECR #{p['fp_idp_rank']}" + (f" (Tier {tier})" if tier else "")
    return "—"  # em dash


def _player_row(p: dict) -> dict:
    return {
        "id": p["player_id"],
        "name": p["name"],
        "position": p.get("position") or "-",
        "fpos": "/".join(p.get("fantasy_positions") or []) or (p.get("position") or "-"),
        "team": p.get("team") or "-",
        "status": p.get("status") or "-",
        "former_team": p.get("former_team", ""),
        "value_display": _value_display(p),
        "value_source": p.get("value_source", "tiering"),
        "rank_score": p.get("rank_score", 1_000_000),
        "unresolved": p.get("unresolved", False),
    }


def to_json_payload(data: BoardData, cfg: LeagueConfig, live_state: dict | None = None) -> dict:
    my_team = data.current_teams.get(data.my_roster_id) if data.my_roster_id is not None else None

    return {
        "league_name": data.league.get("name") or cfg.name,
        "league_key": cfg.key,
        "format": cfg.format,
        "budget": cfg.budget,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dynasty_values_are_real": data.dynasty_values_are_real,
        "idp_rankings_are_real": data.idp_rankings_are_real,
        "position_limits_source": data.position_limits_source,
        "position_limits": data.position_limits,
        "position_counts": data.position_counts,
        "my_team_name": my_team.team_name if my_team else "(no roster found for MY_USER_ID)",
        "departed_team_count": len(data.departed_owner_ids) + len(data.departed_orphan_roster_ids),
        "pool": [_player_row(p) for p in data.pool],
        "my_active": [_player_row(p) for p in data.my_active_players],
        "my_taxi": [_player_row(p) for p in data.my_taxi_players],
        "my_ir": [_player_row(p) for p in data.my_ir_players],
        "cut_candidates": [_player_row(p) for p in data.cut_candidates],
        "live": live_state,
    }


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LEAGUE_NAME__ Dispersal Auction Board</title>
<style>
  :root {
    --bg: #0f1216; --panel: #171b21; --panel-2: #1e232b; --border: #2a3038;
    --text: #e7ecf2; --text-dim: #9aa5b1; --accent: #4f9dff; --good: #35c37b;
    --warn: #e0a83b; --bad: #e0553b;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; font-size:14px; }
  header { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; }
  header h1 { font-size:18px; margin:0; }
  header .meta { color:var(--text-dim); font-size:12px; }
  nav { display:flex; gap:4px; padding:10px 20px 0; border-bottom:1px solid var(--border); }
  nav button { background:none; border:none; color:var(--text-dim); padding:10px 16px; cursor:pointer; font-size:14px; border-bottom:2px solid transparent; }
  nav button.active { color:var(--text); border-bottom-color:var(--accent); }
  main { padding:16px 20px 40px; }
  .tabpane { display:none; }
  .tabpane.active { display:block; }
  .toolbar { display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; align-items:center; }
  input[type=text], select { background:var(--panel-2); border:1px solid var(--border); color:var(--text); padding:6px 10px; border-radius:6px; font-size:13px; }
  input[type=text] { min-width:220px; }
  table { border-collapse:collapse; width:100%; background:var(--panel); border-radius:8px; overflow:hidden; }
  th, td { padding:8px 10px; text-align:left; border-bottom:1px solid var(--border); }
  th { color:var(--text-dim); font-weight:600; cursor:pointer; user-select:none; font-size:12px; text-transform:uppercase; letter-spacing:.03em; white-space:nowrap; }
  th:hover { color:var(--text); }
  tr:hover td { background:var(--panel-2); }
  .badge { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px; font-weight:600; }
  .badge.fits { background:rgba(53,195,123,.15); color:var(--good); }
  .pill { padding:2px 8px; border-radius:5px; background:var(--panel-2); font-size:12px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:18px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px; }
  .card .pos { font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:.04em; }
  .card .count { font-size:22px; font-weight:700; margin-top:4px; }
  .card.over .count { color:var(--bad); }
  .card.room .count { color:var(--good); }
  .flag { background:rgba(224,168,59,.12); border:1px solid rgba(224,168,59,.4); color:var(--warn); padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:14px; }
  .flag.bad { background:rgba(224,85,59,.12); border-color:rgba(224,85,59,.4); color:var(--bad); }
  h2 { font-size:15px; margin:22px 0 10px; color:var(--text-dim); text-transform:uppercase; letter-spacing:.04em; }
  .subtle { color:var(--text-dim); }
  .unresolved { color:var(--warn); }
  #liveLog { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:10px 14px; max-height:320px; overflow-y:auto; font-family:ui-monospace,Consolas,monospace; font-size:12.5px; line-height:1.6; }
</style>
</head>
<body>
<header>
  <div>
    <h1>__LEAGUE_NAME__ &mdash; Dispersal Auction Board</h1>
    <div class="meta">My team: <strong id="myTeamName"></strong> &middot; Departed teams: <span id="departedCount"></span> &middot; Generated <span id="generatedAt"></span></div>
  </div>
</header>
<nav>
  <button data-tab="pool" class="active">Pool</button>
  <button data-tab="roster">My Roster</button>
  <button data-tab="budget">Budget</button>
</nav>
<main>

  <section id="tab-pool" class="tabpane active">
    <div id="valueFlag"></div>
    <div class="toolbar">
      <input type="text" id="poolSearch" placeholder="Search player name...">
      <select id="poolPosFilter"><option value="">All positions</option></select>
      <select id="poolFitFilter">
        <option value="">All players</option>
        <option value="fits">Fills a position I have room for</option>
      </select>
      <span class="subtle" id="poolCount"></span>
    </div>
    <table id="poolTable">
      <thead><tr>
        <th data-key="name">Player</th>
        <th data-key="position">Pos</th>
        <th data-key="fpos">Eligibility</th>
        <th data-key="former_team">Former Team</th>
        <th data-key="team">NFL Team</th>
        <th data-key="status">Status</th>
        <th data-key="value_display" data-sort="rank_score">Value</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </section>

  <section id="tab-roster" class="tabpane">
    <h2>Position Counts vs. Limits</h2>
    <div id="limitsFlag" class="flag"></div>
    <div class="cards" id="posCards"></div>

    <h2>Active Roster</h2>
    <table id="activeTable">
      <thead><tr><th data-key="name">Player</th><th data-key="position">Pos</th><th data-key="fpos">Eligibility</th><th data-key="team">NFL Team</th><th data-key="status">Status</th><th data-key="value_display" data-sort="rank_score">Value</th></tr></thead>
      <tbody></tbody>
    </table>

    <h2>Taxi Squad</h2>
    <table id="taxiTable">
      <thead><tr><th data-key="name">Player</th><th data-key="position">Pos</th><th data-key="fpos">Eligibility</th><th data-key="team">NFL Team</th><th data-key="status">Status</th></tr></thead>
      <tbody></tbody>
    </table>

    <h2>IR / Reserve</h2>
    <table id="irTable">
      <thead><tr><th data-key="name">Player</th><th data-key="position">Pos</th><th data-key="fpos">Eligibility</th><th data-key="team">NFL Team</th><th data-key="status">Status</th></tr></thead>
      <tbody></tbody>
    </table>

    <h2>Cut Candidates (lowest dynasty value first &mdash; zero open bench slots, only 2 taxi slots open)</h2>
    <table id="cutTable">
      <thead><tr><th data-key="name">Player</th><th data-key="position">Pos</th><th data-key="fpos">Eligibility</th><th data-key="status">Status</th><th data-key="value_display" data-sort="rank_score">Value</th></tr></thead>
      <tbody></tbody>
    </table>
  </section>

  <section id="tab-budget" class="tabpane">
    <div id="budgetEmpty" class="flag">Live tracking hasn't started yet. Run <code>live_tracker.py</code> during the draft to populate this tab &mdash; it regenerates this file every poll cycle.</div>
    <div id="budgetContent" style="display:none">
      <h2>Team Budgets</h2>
      <table id="budgetTable">
        <thead><tr><th data-key="team_name">Team</th><th data-key="spent">Spent</th><th data-key="remaining">Remaining</th><th data-key="players_won">Players Won</th></tr></thead>
        <tbody></tbody>
      </table>
      <h2>Live Pick Log</h2>
      <div id="liveLog"></div>
    </div>
  </section>

</main>

<script>
const DATA = __DATA_JSON__;

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

// --- Tabs ---
document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// --- Header ---
document.getElementById("myTeamName").textContent = DATA.my_team_name;
document.getElementById("departedCount").textContent = DATA.departed_team_count;
document.getElementById("generatedAt").textContent = new Date(DATA.generated_at).toLocaleString();

(function () {
  const notes = [];
  if (!DATA.dynasty_values_are_real) {
    notes.push("Offensive dynasty $ values are APPROXIMATE (DynastyProcess unreachable) - falling back to position/status tiering.");
  }
  if (!DATA.idp_rankings_are_real) {
    notes.push("IDP (DL/LB/DB) rankings are APPROXIMATE (FantasyPros unreachable or no API key set) - falling back to position/status tiering instead of real ECR ranks.");
  }
  if (notes.length) {
    const f = document.getElementById("valueFlag");
    f.className = "flag";
    f.textContent = notes.join(" ");
  }
})();

// --- Generic sortable/filterable table renderer ---
function renderTable(tableEl, rows, opts) {
  opts = opts || {};
  const tbody = tableEl.querySelector("tbody");
  const ths = tableEl.querySelectorAll("th[data-key]");
  let sortKey = opts.defaultSort || "name";
  let sortDir = opts.defaultDir || 1;

  function draw(data) {
    tbody.innerHTML = data.map(p => {
      const cells = opts.columns.map(col => {
        if (col === "name") return `<td>${escapeHtml(p.name)}${p.unresolved ? ' <span class="unresolved">(unresolved id)</span>' : ''}</td>`;
        return `<td>${escapeHtml(p[col])}</td>`;
      }).join("");
      return `<tr>${cells}</tr>`;
    }).join("");
    if (opts.onDraw) opts.onDraw(data.length);
  }

  function sortRows(rows) {
    const sorted = [...rows].sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (sortKey === "rank_score") { av = av ?? Infinity; bv = bv ?? Infinity; }
      else { av = (av ?? "").toString().toLowerCase(); bv = (bv ?? "").toString().toLowerCase(); }
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
    return sorted;
  }

  ths.forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort || th.dataset.key;
      sortDir = (sortKey === key) ? -sortDir : -1;
      sortKey = key;
      draw(sortRows(opts.getRows()));
    });
  });

  opts.redraw = () => draw(sortRows(opts.getRows()));
  opts.redraw();
  return opts;
}

// --- Pool tab ---
const posFilter = document.getElementById("poolPosFilter");
const allPositions = [...new Set(DATA.pool.map(p => p.position))].filter(Boolean).sort();
allPositions.forEach(pos => {
  const o = document.createElement("option"); o.value = pos; o.textContent = pos;
  posFilter.appendChild(o);
});

const posLimits = DATA.position_limits, posCounts = DATA.position_counts;
function positionHasRoom(pos) {
  if (!(pos in posLimits)) return false;
  return (posCounts[pos] ?? 0) < posLimits[pos];
}

function poolRows() {
  const q = document.getElementById("poolSearch").value.trim().toLowerCase();
  const pos = posFilter.value;
  const fit = document.getElementById("poolFitFilter").value;
  return DATA.pool.filter(p => {
    if (q && !p.name.toLowerCase().includes(q)) return false;
    if (pos && p.position !== pos) return false;
    if (fit === "fits" && !p.fpos.split("/").some(positionHasRoom)) return false;
    return true;
  });
}

const poolOpts = renderTable(document.getElementById("poolTable"), DATA.pool, {
  columns: ["name", "position", "fpos", "former_team", "team", "status", "value_display"],
  defaultSort: "rank_score", defaultDir: 1,
  getRows: poolRows,
  onDraw: n => document.getElementById("poolCount").textContent = n + " players",
});
["poolSearch", "poolPosFilter", "poolFitFilter"].forEach(id => {
  document.getElementById(id).addEventListener("input", () => poolOpts.redraw());
});

// --- My Roster tab ---
const cardsEl = document.getElementById("posCards");
const allPosKeys = [...new Set([...Object.keys(posLimits), ...Object.keys(posCounts)])];
cardsEl.innerHTML = allPosKeys.map(pos => {
  const count = posCounts[pos] ?? 0;
  const limit = posLimits[pos];
  const cls = limit === undefined ? "" : (count >= limit ? "over" : "room");
  return `<div class="card ${cls}"><div class="pos">${pos}</div><div class="count">${count}${limit !== undefined ? " / " + limit : ""}</div></div>`;
}).join("");

const limitsFlagEl = document.getElementById("limitsFlag");
limitsFlagEl.textContent = "Position limits source: " + DATA.position_limits_source;
if (DATA.position_limits_source.toLowerCase().includes("assumed")) limitsFlagEl.classList.add("bad");

renderTable(document.getElementById("activeTable"), DATA.my_active, {
  columns: ["name", "position", "fpos", "team", "status", "value_display"],
  defaultSort: "rank_score", defaultDir: 1,
  getRows: () => DATA.my_active,
});
renderTable(document.getElementById("taxiTable"), DATA.my_taxi, {
  columns: ["name", "position", "fpos", "team", "status"],
  getRows: () => DATA.my_taxi,
});
renderTable(document.getElementById("irTable"), DATA.my_ir, {
  columns: ["name", "position", "fpos", "team", "status"],
  getRows: () => DATA.my_ir,
});
renderTable(document.getElementById("cutTable"), DATA.cut_candidates, {
  columns: ["name", "position", "fpos", "status", "value_display"],
  defaultSort: "rank_score", defaultDir: -1,
  getRows: () => DATA.cut_candidates,
});

// --- Budget tab ---
if (DATA.live) {
  document.getElementById("budgetEmpty").style.display = "none";
  document.getElementById("budgetContent").style.display = "block";
  const teams = DATA.live.teams || [];
  document.getElementById("budgetTable").querySelector("tbody").innerHTML = teams.map(t => `
    <tr>
      <td>${escapeHtml(t.team_name)}</td>
      <td>$${t.spent}</td>
      <td>$${t.remaining}</td>
      <td>${t.players_won.map(pw => escapeHtml(pw.name) + " ($" + pw.price + ")").join(", ") || "&mdash;"}</td>
    </tr>`).join("");
  const log = DATA.live.picks_log || [];
  document.getElementById("liveLog").innerHTML = log.map(escapeHtml).join("<br>");
}
</script>
</body>
</html>
"""


def render_html(payload: dict) -> str:
    html = _TEMPLATE.replace("__LEAGUE_NAME__", payload["league_name"])
    html = html.replace("__DATA_JSON__", json.dumps(payload))
    return html


def write_board_html(payload: dict, path: str = "board.html") -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(payload))
    print(f"Wrote {path}")
