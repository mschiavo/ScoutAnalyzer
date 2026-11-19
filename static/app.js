// ScoutAnalyzer - Frontend Single Page Application
let state = {
  matches: [],
  currentMatchId: null,
  currentMatchDetail: null,
  events: [],
  logs: [],
  selectedSet: "all",
  errorsOnly: false,
  activeEventIndex: 0
};

// DOM Elements
const matchSelect = document.getElementById("match-select");
const homeTeamName = document.getElementById("home-team-name");
const homeTeamCode = document.getElementById("home-team-code");
const awayTeamName = document.getElementById("away-team-name");
const awayTeamCode = document.getElementById("away-team-code");
const setsDisplay = document.getElementById("sets-display");

const kpiEvents = document.getElementById("kpi-events");
const kpiRotations = document.getElementById("kpi-rotations");
const kpiIssues = document.getElementById("kpi-issues");
const eventsCountLabel = document.getElementById("events-count-label");

const eventsTbody = document.getElementById("events-tbody");
const activeEventCaption = document.getElementById("active-event-caption");
const courtHomeTitle = document.getElementById("court-home-title");
const courtAwayTitle = document.getElementById("court-away-title");

const filterErrorsOnly = document.getElementById("filter-errors-only");
const setTabs = document.querySelectorAll("#set-tabs .tab");

// Modal Elements
const auditModal = document.getElementById("audit-modal");
const btnOpenAuditModal = document.getElementById("btn-open-audit-modal");
const btnCloseAuditModal = document.getElementById("btn-close-audit-modal");
const btnCancelAudit = document.getElementById("btn-cancel-audit");
const btnRunAudit = document.getElementById("btn-run-audit");
const auditFilePathInput = document.getElementById("audit-file-path");
const auditFileInput = document.getElementById("audit-file-input");
const auditStatus = document.getElementById("audit-status");
const btnSyncRosters = document.getElementById("btn-sync-rosters");

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  loadMatches();
});

function setupEventListeners() {
  matchSelect.addEventListener("change", (e) => {
    const matchId = e.target.value;
    if (matchId) {
      selectMatch(parseInt(matchId));
    }
  });

  setTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      setTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.selectedSet = tab.dataset.set;
      renderEventsTable();
    });
  });

  filterErrorsOnly.addEventListener("change", (e) => {
    state.errorsOnly = e.target.checked;
    renderEventsTable();
  });

  // Modal Open/Close
  btnOpenAuditModal.addEventListener("click", () => {
    auditModal.classList.add("open");
    auditStatus.innerHTML = "";
    if (auditFileInput) auditFileInput.value = "";
  });
  btnCloseAuditModal.addEventListener("click", () => auditModal.classList.remove("open"));
  btnCancelAudit.addEventListener("click", () => auditModal.classList.remove("open"));

  // Presets in modal
  document.querySelectorAll(".preset-file").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      auditFilePathInput.value = link.dataset.path;
    });
  });

  // Run Audit
  btnRunAudit.addEventListener("click", runAuditFile);

  // File Upload listener
  if (auditFileInput) {
    auditFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadAndAuditFile(e.target.files[0]);
      }
    });
  }

  // Sync Rosters
  btnSyncRosters.addEventListener("click", syncRosters);
}

// --- API CALLS ---
async function loadMatches() {
  try {
    const res = await fetch("/api/matches");
    state.matches = await res.json();
    populateMatchSelect();
    if (state.matches.length > 0) {
      matchSelect.value = state.matches[0].id;
      selectMatch(state.matches[0].id);
    }
  } catch (err) {
    console.error("Errore caricamento lista match:", err);
  }
}

function populateMatchSelect() {
  matchSelect.innerHTML = "";
  if (state.matches.length === 0) {
    matchSelect.innerHTML = '<option value="">Nessuna partita a DB. Esegui un audit!</option>';
    return;
  }
  state.matches.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.match_code} - ${m.home_code} vs ${m.away_code} (${m.scheduled_date || "N.D."})`;
    matchSelect.appendChild(opt);
  });
}

async function selectMatch(matchId) {
  state.currentMatchId = matchId;
  matchSelect.value = matchId;
  try {
    const [detailRes, eventsRes, logsRes] = await Promise.all([
      fetch(`/api/matches/${matchId}`),
      fetch(`/api/matches/${matchId}/events?limit=3000`),
      fetch(`/api/matches/${matchId}/logs`)
    ]);

    state.currentMatchDetail = await detailRes.json();
    state.events = await eventsRes.json();
    state.logs = await logsRes.json();

    updateMatchSummary();
    renderEventsTable();

    if (state.events.length > 0) {
      showEventOnCourt(state.events[0], 0);
    }
  } catch (err) {
    console.error("Errore recupero dettagli match:", err);
  }
}

// --- RENDER FUNCTIONS ---
function updateMatchSummary() {
  const md = state.currentMatchDetail;
  if (!md || !md.match) return;

  const m = md.match;
  homeTeamName.textContent = m.home_name || "Casa";
  homeTeamCode.textContent = m.home_code || "*";
  awayTeamName.textContent = m.away_name || "Ospite";
  awayTeamCode.textContent = m.away_code || "a";

  courtHomeTitle.textContent = `${m.home_name || "CASA"} (*)`;
  courtAwayTitle.textContent = `${m.away_name || "OSPITE"} (a)`;

  // Sets pill
  setsDisplay.innerHTML = "";
  if (md.sets && md.sets.length > 0) {
    md.sets.forEach(s => {
      const pill = document.createElement("div");
      pill.className = "set-score-pill";
      if (s.winning_team === "*") pill.classList.add("home-won");
      else if (s.winning_team === "a") pill.classList.add("away-won");

      pill.innerHTML = `
        <span class="set-label">SET ${s.set_number}</span>
        <span class="set-points">${s.home_score || 0}:${s.away_score || 0}</span>
      `;
      setsDisplay.appendChild(pill);
    });
  }

  // KPIs
  kpiEvents.textContent = `Eventi: ${state.events.length}`;
  const totalIssues = state.logs.length;
  kpiIssues.textContent = `Anomalie: ${totalIssues}`;

  // Conta formazioni distinte
  let distinctRotations = new Set();
  state.events.forEach(e => {
    if (e.home_lineup && e.home_lineup.some(x => x !== null)) {
      distinctRotations.add(JSON.stringify(e.home_lineup));
    }
  });
  kpiRotations.textContent = `Formazioni: ${distinctRotations.size}`;
}

function renderEventsTable() {
  eventsTbody.innerHTML = "";

  const filteredEvents = state.events.filter(ev => {
    if (state.selectedSet !== "all" && ev.set_number !== parseInt(state.selectedSet)) {
      return false;
    }
    if (state.errorsOnly && ev.is_valid === 1 && !ev.error_note) {
      return false;
    }
    return true;
  });

  eventsCountLabel.textContent = `${filteredEvents.length} azioni mostrate (su ${state.events.length} totali)`;

  if (filteredEvents.length === 0) {
    eventsTbody.innerHTML = `<tr><td colspan="10" class="empty-state">Nessun evento corrisponde ai filtri selezionati.</td></tr>`;
    return;
  }

  filteredEvents.forEach((ev, idx) => {
    const tr = document.createElement("tr");
    if (ev.is_valid === 0 || ev.error_note) {
      tr.classList.add("has-error");
    }
    if (idx === state.activeEventIndex) {
      tr.classList.add("active-row");
    }

    // Evaluation Badge
    let evalBadge = "-";
    if (ev.evaluation) {
      let evalClass = "eval-minus";
      if (ev.evaluation === "#") evalClass = "eval-hash";
      else if (ev.evaluation === "=") evalClass = "eval-equal";
      else if (ev.evaluation === "/") evalClass = "eval-slash";
      else if (ev.evaluation === "+") evalClass = "eval-plus";
      else if (ev.evaluation === "!") evalClass = "eval-excl";
      evalBadge = `<span class="eval-badge ${evalClass}">${ev.evaluation}</span>`;
    }

    // Team Chip
    const teamClass = ev.team_code === "*" ? "home" : "away";
    const teamLabel = ev.team_code === "*" ? "Casa" : "Osp.";

    // Zone Info
    let zoneInfo = "-";
    if (ev.start_zone || ev.end_zone) {
      zoneInfo = `Z${ev.start_zone || "?"} ➔ Z${ev.end_zone || "?"}${ev.end_subzone || ""}`;
    }

    // Rotations Info
    const rotInfo = `P${ev.home_setter_pos || "?"} vs P${ev.away_setter_pos || "?"}`;

    // Codice ed eventi speciali (Sostituzione, Cambio Palleggio, Rotazione)
    let codeDisplay = `<code>${escapeHtml(ev.extended_code)}</code>`;
    const rawCode = ev.extended_code || "";
    if (rawCode.length >= 3 && (rawCode.startsWith("*c") || rawCode.startsWith("ac")) && rawCode.includes(":")) {
      const subParts = rawCode.substring(2).split(":");
      codeDisplay = `<span class="badge-subst">🔄 Cambio: #${subParts[0]} ➔ #${subParts[1]}</span>`;
    } else if (rawCode.length >= 3 && (rawCode.startsWith("*P") || rawCode.startsWith("aP")) && !rawCode.includes(">")) {
      codeDisplay = `<span class="badge-setter-code">🎯 Palleggio: #${rawCode.substring(2)}</span>`;
    } else if (rawCode.length >= 3 && (rawCode.startsWith("*z") || rawCode.startsWith("az")) && !rawCode.includes(">")) {
      codeDisplay = `<span class="badge-rot-code">⚡ Rotazione: P${rawCode.substring(2)}</span>`;
    }

    // Note / Error
    let noteHtml = '<span style="color:#64748b;">OK</span>';
    if (ev.error_note) {
      noteHtml = `<span class="error-tag">⚠️ ${escapeHtml(ev.error_note)}</span>`;
    }

    tr.innerHTML = `
      <td>${ev.event_index}</td>
      <td>${ev.set_number}</td>
      <td><span class="team-chip ${teamClass}">${teamLabel}</span></td>
      <td><strong>${ev.shirt_number !== null ? ev.shirt_number : "-"}</strong></td>
      <td>${ev.skill || "-"}</td>
      <td>${evalBadge}</td>
      <td>${codeDisplay}</td>
      <td>${zoneInfo}</td>
      <td><small>${rotInfo}</small></td>
      <td>${noteHtml}</td>
    `;

    tr.addEventListener("click", () => {
      document.querySelectorAll(".events-table tbody tr").forEach(r => r.classList.remove("active-row"));
      tr.classList.add("active-row");
      state.activeEventIndex = idx;
      showEventOnCourt(ev, idx);
    });

    eventsTbody.appendChild(tr);
  });
}

function showEventOnCourt(ev, idx) {
  if (!ev) return;

  const hName = (state.currentMatchDetail && state.currentMatchDetail.match) ? state.currentMatchDetail.match.home_name : "CASA";
  const aName = (state.currentMatchDetail && state.currentMatchDetail.match) ? state.currentMatchDetail.match.away_name : "OSPITE";

  courtHomeTitle.textContent = `${hName} (*) - P${ev.home_setter_pos || "?"}`;
  courtAwayTitle.textContent = `${aName} (a) - P${ev.away_setter_pos || "?"}`;

  activeEventCaption.textContent = `Azione #${ev.event_index} (Set ${ev.set_number}) - ${ev.extended_code || ""} | Casa P${ev.home_setter_pos || "?"} vs Ospite P${ev.away_setter_pos || "?"}`;

  // Aggiorna Casa (Z1 a Z6)
  const hLineup = ev.home_lineup || [null, null, null, null, null, null];
  updateZoneNode("h-zone-1", hLineup[0], 1, "*", ev);
  updateZoneNode("h-zone-2", hLineup[1], 2, "*", ev);
  updateZoneNode("h-zone-3", hLineup[2], 3, "*", ev);
  updateZoneNode("h-zone-4", hLineup[3], 4, "*", ev);
  updateZoneNode("h-zone-5", hLineup[4], 5, "*", ev);
  updateZoneNode("h-zone-6", hLineup[5], 6, "*", ev);

  // Aggiorna Ospite (Z1 a Z6)
  const aLineup = ev.away_lineup || [null, null, null, null, null, null];
  updateZoneNode("a-zone-1", aLineup[0], 1, "a", ev);
  updateZoneNode("a-zone-2", aLineup[1], 2, "a", ev);
  updateZoneNode("a-zone-3", aLineup[2], 3, "a", ev);
  updateZoneNode("a-zone-4", aLineup[3], 4, "a", ev);
  updateZoneNode("a-zone-5", aLineup[4], 5, "a", ev);
  updateZoneNode("a-zone-6", aLineup[5], 6, "a", ev);
}

function updateZoneNode(nodeId, shirtNum, zoneNum, teamCode, ev) {
  const g = document.getElementById(nodeId);
  if (!g) return;

  const textNum = g.querySelector(".p-num");
  textNum.textContent = shirtNum !== null && shirtNum !== undefined ? shirtNum : "?";

  // Reset classi speciali
  g.classList.remove("is-setter", "is-server", "is-libero");

  const setterPos = teamCode === "*" ? ev.home_setter_pos : ev.away_setter_pos;
  if (setterPos === zoneNum) {
    g.classList.add("is-setter");
  }

  // Battitore in Z1
  if (zoneNum === 1 && ev.skill === "S" && ev.team_code === teamCode) {
    g.classList.add("is-server");
  }

  // Verifica Libero
  if (isPlayerLibero(shirtNum, teamCode)) {
    g.classList.add("is-libero");
  }

  // Tooltip con anagrafica
  const p = getPlayerInfo(shirtNum, teamCode);
  if (p) {
    g.setAttribute("title", `#${shirtNum} ${p.first_name || ""} ${p.last_name || ""} (${p.role_name || ""})`);
  } else {
    g.removeAttribute("title");
  }
}

function getPlayerInfo(shirtNum, teamCode) {
  if (!state.currentMatchDetail || shirtNum === null) return null;
  const roster = teamCode === "*" ? state.currentMatchDetail.players_home : state.currentMatchDetail.players_visiting;
  if (!roster) return null;
  return roster.find(x => x.shirt_number === shirtNum) || null;
}

function isPlayerLibero(shirtNum, teamCode) {
  const p = getPlayerInfo(shirtNum, teamCode);
  return p && (p.role_code === "L" || p.role_name === "Libero");
}

// --- AUDIT MODAL ACTIONS ---
async function uploadAndAuditFile(file) {
  if (!file) return;

  auditStatus.innerHTML = `<span style="color:#38bdf8;">⏳ Caricamento e audit di <b>${escapeHtml(file.name)}</b> in corso...</span>`;
  btnRunAudit.disabled = true;

  try {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/api/audit/upload", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Errore durante il caricamento");
    }

    auditStatus.innerHTML = `
      <div style="color:#10b981; font-weight:bold;">✅ Audit completato con successo!</div>
      <div style="margin-top:6px; color:#cbd5e1;">
        Partita: <b>${data.match_code}</b> | Eventi: ${data.events_count} | Set: ${data.sets_count}<br>
        Violazioni sintattiche: ${data.syntax_issues_count} | Anomalie State Engine: ${data.state_issues_count}
      </div>
    `;

    await loadMatches();
    selectMatch(data.match_id);

    setTimeout(() => {
      auditModal.classList.remove("open");
      btnRunAudit.disabled = false;
    }, 1800);

  } catch (err) {
    auditStatus.innerHTML = `<span style="color:#ef4444;">❌ ${err.message}</span>`;
    btnRunAudit.disabled = false;
  }
}

async function runAuditFile() {
  const path = auditFilePathInput.value.trim();
  if (!path) {
    auditStatus.innerHTML = '<span style="color:#ef4444;">Inserisci il percorso di un file .dvw</span>';
    return;
  }

  auditStatus.innerHTML = '<span style="color:#38bdf8;">⏳ Esecuzione audit e analisi dello state engine in corso...</span>';
  btnRunAudit.disabled = true;

  try {
    const res = await fetch("/api/audit/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: path })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Errore durante l'audit");
    }

    auditStatus.innerHTML = `
      <div style="color:#10b981; font-weight:bold;">✅ Audit completato con successo!</div>
      <div style="margin-top:6px; color:#cbd5e1;">
        Partita: <b>${data.match_code}</b> | Eventi: ${data.events_count} | Set: ${data.sets_count}<br>
        Violazioni sintattiche: ${data.syntax_issues_count} | Anomalie State Engine: ${data.state_issues_count}
      </div>
    `;

    await loadMatches();
    selectMatch(data.match_id);

    setTimeout(() => {
      auditModal.classList.remove("open");
      btnRunAudit.disabled = false;
    }, 1800);

  } catch (err) {
    auditStatus.innerHTML = `<span style="color:#ef4444;">❌ ${err.message}</span>`;
    btnRunAudit.disabled = false;
  }
}

async function syncRosters() {
  btnSyncRosters.disabled = true;
  btnSyncRosters.textContent = "⏳ Sincronizzazione...";
  try {
    const res = await fetch("/api/rosters/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();
    alert(`Sincronizzazione completata con successo! Aggiornati i roster da Volley Network.`);
  } catch (err) {
    alert(`Errore sincronizzazione roster: ${err.message}`);
  } finally {
    btnSyncRosters.disabled = false;
    btnSyncRosters.textContent = "🔄 Sincronizza Roster";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
