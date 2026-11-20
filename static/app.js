// ScoutAnalyzer 3000 - Frontend Single Page Application with Login Gate & Admin Management
let state = {
  authToken: localStorage.getItem("scout_token") || null,
  currentUser: null,
  matches: [],
  currentMatchId: null,
  currentMatchDetail: null,
  events: [],
  logs: [],
  selectedSet: "all",
  errorsOnly: false,
  activeEventIndex: 0,
  teamsList: []
};

// DOM Elements - Login Gate
const loginOverlay = document.getElementById("login-overlay");
const loginForm = document.getElementById("login-form");
const loginUsernameInput = document.getElementById("login-username");
const loginPasswordInput = document.getElementById("login-password");
const loginError = document.getElementById("login-error");
const btnLogin = document.getElementById("btn-login");

// DOM Elements - App Container & Header
const appContainer = document.getElementById("app-container");
const userDisplay = document.getElementById("user-display");
const btnLogout = document.getElementById("btn-logout");
const adminNavGroup = document.getElementById("admin-nav-group");
const matchSelect = document.getElementById("match-select");
const homeTeamName = document.getElementById("home-team-name");
const homeTeamCode = document.getElementById("home-team-code");
const awayTeamName = document.getElementById("away-team-name");
const awayTeamCode = document.getElementById("away-team-code");
const setsDisplay = document.getElementById("sets-display");

// KPIs & Filters
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

// Modals - Audit
const auditModal = document.getElementById("audit-modal");
const btnOpenAuditModal = document.getElementById("btn-open-audit-modal");
const btnCloseAuditModal = document.getElementById("btn-close-audit-modal");
const btnCancelAudit = document.getElementById("btn-cancel-audit");
const btnRunAudit = document.getElementById("btn-run-audit");
const auditFilePathInput = document.getElementById("audit-file-path");
const auditFileInput = document.getElementById("audit-file-input");
const auditStatus = document.getElementById("audit-status");
const btnSyncRosters = document.getElementById("btn-sync-rosters");

// Modals - Admin Users
const adminUsersModal = document.getElementById("admin-users-modal");
const btnOpenUsersModal = document.getElementById("btn-open-users-modal");
const btnCloseUsersModal = document.getElementById("btn-close-users-modal");
const createUserForm = document.getElementById("create-user-form");
const userFormTitle = document.getElementById("user-form-title");
const editUserId = document.getElementById("edit-user-id");
const newUsername = document.getElementById("new-username");
const newPassword = document.getElementById("new-password");
const passwordHint = document.getElementById("password-hint");
const newEmail = document.getElementById("new-email");
const newRole = document.getElementById("new-role");
const teamsCheckboxList = document.getElementById("teams-checkbox-list");
const usersTbody = document.getElementById("users-tbody");
const userFormStatus = document.getElementById("user-form-status");

// Modals - Admin Rules
const adminRulesModal = document.getElementById("admin-rules-modal");
const btnOpenRulesModal = document.getElementById("btn-open-rules-modal");
const btnCloseRulesModal = document.getElementById("btn-close-rules-modal");
const rulesTbody = document.getElementById("rules-tbody");
const btnAddRule = document.getElementById("btn-add-rule");
const btnRevalidateMatches = document.getElementById("btn-revalidate-matches");
const ruleDesc = document.getElementById("rule-desc");
const ruleTermSkill = document.getElementById("rule-term-skill");
const ruleTermEval = document.getElementById("rule-term-eval");
const ruleFollowSkills = document.getElementById("rule-follow-skills");
const ruleFollowEvals = document.getElementById("rule-follow-evals");
const ruleMustOpponent = document.getElementById("rule-must-opponent");

// Modals - Admin Logins
const adminLoginsModal = document.getElementById("admin-logins-modal");
const btnOpenLoginsModal = document.getElementById("btn-open-logins-modal");
const btnCloseLoginsModal = document.getElementById("btn-close-logins-modal");
const loginsTbody = document.getElementById("logins-tbody");

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  checkAuth();
});

// --- AUTHENTICATION & SLIDING SESSION ---
async function authFetch(url, options = {}) {
  const headers = options.headers || {};
  if (state.authToken) {
    headers["Authorization"] = `Bearer ${state.authToken}`;
  }
  options.headers = headers;

  const res = await fetch(url, options);

  // Sliding session token renewal
  const renewed = res.headers.get("X-Renewed-Token");
  if (renewed) {
    state.authToken = renewed;
    localStorage.setItem("scout_token", renewed);
  }

  if (res.status === 401 && !url.includes("/api/auth/login")) {
    handleLogout();
  }

  return res;
}

async function checkAuth() {
  if (!state.authToken) {
    showLoginGate();
    return;
  }

  try {
    const res = await authFetch("/api/auth/me");
    if (!res.ok) {
      showLoginGate();
      return;
    }
    const user = await res.json();
    state.currentUser = user;
    hideLoginGate();
    updateUserInterfaceForRole();
    await loadMatches();
  } catch (err) {
    showLoginGate();
  }
}

function showLoginGate() {
  loginOverlay.style.display = "flex";
  appContainer.style.display = "none";
  state.authToken = null;
  state.currentUser = null;
  localStorage.removeItem("scout_token");
}

function hideLoginGate() {
  loginOverlay.style.display = "none";
  appContainer.style.display = "flex";
}

async function handleLogin(e) {
  e.preventDefault();
  loginError.textContent = "";
  btnLogin.disabled = true;
  btnLogin.textContent = "Accesso in corso...";

  const username = loginUsernameInput.value.trim();
  const password = loginPasswordInput.value;

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Credenziali non valide.");
    }

    state.authToken = data.access_token;
    localStorage.setItem("scout_token", data.access_token);
    state.currentUser = data.user;

    hideLoginGate();
    updateUserInterfaceForRole();
    await loadMatches();

  } catch (err) {
    loginError.textContent = `❌ ${err.message}`;
  } finally {
    btnLogin.disabled = false;
    btnLogin.textContent = "Accedi alla Piattaforma";
  }
}

function handleLogout() {
  state.authToken = null;
  state.currentUser = null;
  localStorage.removeItem("scout_token");
  showLoginGate();
}

function updateUserInterfaceForRole() {
  if (!state.currentUser) return;

  const role = state.currentUser.role;
  userDisplay.textContent = `${state.currentUser.username} (${role})`;

  if (role === "ADMIN") {
    adminNavGroup.style.display = "flex";
  } else {
    // Utente SCOUT: nascondi comandi admin e upload
    adminNavGroup.style.display = "none";
  }
}

// --- SETUP EVENT LISTENERS ---
function setupEventListeners() {
  loginForm.addEventListener("submit", handleLogin);
  btnLogout.addEventListener("click", handleLogout);

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

  // Modal Audit
  btnOpenAuditModal.addEventListener("click", () => {
    auditModal.classList.add("open");
    auditStatus.innerHTML = "";
    if (auditFileInput) auditFileInput.value = "";
  });
  btnCloseAuditModal.addEventListener("click", () => auditModal.classList.remove("open"));
  btnCancelAudit.addEventListener("click", () => auditModal.classList.remove("open"));
  btnRunAudit.addEventListener("click", runAuditFile);
  if (auditFileInput) {
    auditFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadAndAuditFile(e.target.files[0]);
      }
    });
  }
  document.querySelectorAll(".preset-file").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      auditFilePathInput.value = link.dataset.path;
    });
  });

  // Roster sync
  btnSyncRosters.addEventListener("click", syncRosters);

  // Admin Modals
  btnOpenUsersModal.addEventListener("click", openAdminUsersModal);
  btnCloseUsersModal.addEventListener("click", () => adminUsersModal.classList.remove("open"));
  createUserForm.addEventListener("submit", handleSaveUser);

  btnOpenRulesModal.addEventListener("click", openAdminRulesModal);
  btnCloseRulesModal.addEventListener("click", () => adminRulesModal.classList.remove("open"));
  btnAddRule.addEventListener("click", handleAddRule);
  btnRevalidateMatches.addEventListener("click", handleRevalidateMatches);

  btnOpenLoginsModal.addEventListener("click", openAdminLoginsModal);
  btnCloseLoginsModal.addEventListener("click", () => adminLoginsModal.classList.remove("open"));
}

// --- MATCH DATA API & RENDER ---
async function loadMatches() {
  try {
    const res = await authFetch("/api/matches");
    if (!res.ok) return;
    state.matches = await res.json();
    populateMatchSelect();
    if (state.matches.length > 0) {
      matchSelect.value = state.matches[0].id;
      selectMatch(state.matches[0].id);
    } else {
      resetMatchDisplay();
    }
  } catch (err) {
    console.error("Errore caricamento lista match:", err);
  }
}

function populateMatchSelect() {
  matchSelect.innerHTML = "";
  if (state.matches.length === 0) {
    matchSelect.innerHTML = '<option value="">Nessuna partita disponibile per il tuo account.</option>';
    return;
  }
  state.matches.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.match_code} - ${m.home_code} vs ${m.away_code} (${m.scheduled_date || "N.D."})`;
    matchSelect.appendChild(opt);
  });
}

function resetMatchDisplay() {
  homeTeamName.textContent = "--";
  homeTeamCode.textContent = "---";
  awayTeamName.textContent = "--";
  awayTeamCode.textContent = "---";
  setsDisplay.innerHTML = '<span class="no-match-msg">Nessuna partita disponibile</span>';
  eventsTbody.innerHTML = '<tr><td colspan="10" class="empty-state">Nessuna partita autorizzata.</td></tr>';
}

async function selectMatch(matchId) {
  state.currentMatchId = matchId;
  matchSelect.value = matchId;
  try {
    const [detailRes, eventsRes, logsRes] = await Promise.all([
      authFetch(`/api/matches/${matchId}`),
      authFetch(`/api/matches/${matchId}/events?limit=3000`),
      authFetch(`/api/matches/${matchId}/logs`)
    ]);

    if (!detailRes.ok) {
      alert("Accesso negato o partita non disponibile.");
      return;
    }

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

  kpiEvents.textContent = `Eventi: ${state.events.length}`;
  kpiIssues.textContent = `Anomalie: ${state.logs.length}`;

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

    const teamClass = ev.team_code === "*" ? "home" : "away";
    const teamLabel = ev.team_code === "*" ? "Casa" : "Osp.";

    let zoneInfo = "-";
    if (ev.start_zone || ev.end_zone) {
      zoneInfo = `Z${ev.start_zone || "?"} ➔ Z${ev.end_zone || "?"}${ev.end_subzone || ""}`;
    }

    const rotInfo = `P${ev.home_setter_pos || "?"} vs P${ev.away_setter_pos || "?"}`;

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

  const hLineup = ev.home_lineup || [null, null, null, null, null, null];
  updateZoneNode("h-zone-1", hLineup[0], 1, "*", ev);
  updateZoneNode("h-zone-2", hLineup[1], 2, "*", ev);
  updateZoneNode("h-zone-3", hLineup[2], 3, "*", ev);
  updateZoneNode("h-zone-4", hLineup[3], 4, "*", ev);
  updateZoneNode("h-zone-5", hLineup[4], 5, "*", ev);
  updateZoneNode("h-zone-6", hLineup[5], 6, "*", ev);

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

  g.classList.remove("is-setter", "is-server", "is-libero");

  const setterPos = teamCode === "*" ? ev.home_setter_pos : ev.away_setter_pos;
  if (setterPos === zoneNum) {
    g.classList.add("is-setter");
  }

  if (zoneNum === 1 && ev.skill === "S" && ev.team_code === teamCode) {
    g.classList.add("is-server");
  }

  if (isPlayerLibero(shirtNum, teamCode)) {
    g.classList.add("is-libero");
  }

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

// --- AUDIT MODAL ACTIONS (ADMIN ONLY) ---
async function uploadAndAuditFile(file) {
  if (!file) return;

  auditStatus.innerHTML = `<span style="color:#38bdf8;">⏳ Caricamento e audit di <b>${escapeHtml(file.name)}</b> in corso...</span>`;
  btnRunAudit.disabled = true;

  try {
    const formData = new FormData();
    formData.append("file", file);

    const res = await authFetch("/api/audit/upload", {
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

  auditStatus.innerHTML = '<span style="color:#38bdf8;">⏳ Esecuzione audit in corso...</span>';
  btnRunAudit.disabled = true;

  try {
    const res = await authFetch("/api/audit/file", {
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
        Partita: <b>${data.match_code}</b> | Eventi: ${data.events_count} | Set: ${data.sets_count}
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
    const res = await authFetch("/api/rosters/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();
    alert("Sincronizzazione completata con successo!");
  } catch (err) {
    alert(`Errore sincronizzazione roster: ${err.message}`);
  } finally {
    btnSyncRosters.disabled = false;
    btnSyncRosters.textContent = "🔄 Roster";
  }
}

// --- ADMIN USERS MANAGEMENT ---
async function openAdminUsersModal() {
  adminUsersModal.classList.add("open");
  userFormStatus.innerHTML = "";
  resetUserForm();
  await Promise.all([loadAdminTeams(), loadAdminUsers()]);
}

async function loadAdminTeams() {
  try {
    const res = await authFetch("/api/admin/teams");
    if (!res.ok) return;
    state.teamsList = await res.json();
    teamsCheckboxList.innerHTML = "";
    state.teamsList.forEach(t => {
      const lbl = document.createElement("label");
      lbl.className = "team-checkbox-item";
      lbl.innerHTML = `
        <input type="checkbox" value="${t.id}" class="team-chk" />
        <span><strong>${t.code}</strong> - ${t.name}</span>
      `;
      teamsCheckboxList.appendChild(lbl);
    });
  } catch (err) {
    console.error("Errore caricamento squadre:", err);
  }
}

async function loadAdminUsers() {
  try {
    const res = await authFetch("/api/admin/users");
    if (!res.ok) return;
    const users = await res.json();
    usersTbody.innerHTML = "";
    users.forEach(u => {
      const tr = document.createElement("tr");
      const teamBadges = (u.teams || []).map(t => `<small style="background:#26334d; padding:2px 4px; border-radius:3px;">${t.code}</small>`).join(" ") || "<em>Nessuna</em>";
      tr.innerHTML = `
        <td><strong>${u.username}</strong></td>
        <td><span class="team-chip ${u.role === 'ADMIN' ? 'home' : 'away'}">${u.role}</span></td>
        <td>${u.email || "-"}</td>
        <td>${teamBadges}</td>
        <td>
          <button class="btn btn-secondary" style="padding:2px 8px; font-size:0.75rem;" onclick="editUser(${u.id})">✏️</button>
          <button class="btn btn-danger" style="padding:2px 8px; font-size:0.75rem;" onclick="deleteUser(${u.id})">🗑️</button>
        </td>
      `;
      usersTbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Errore caricamento utenti:", err);
  }
}

function resetUserForm() {
  editUserId.value = "";
  userFormTitle.textContent = "Nuovo Utente";
  newUsername.value = "";
  newUsername.disabled = false;
  newPassword.value = "";
  newPassword.required = true;
  passwordHint.style.display = "none";
  newEmail.value = "";
  newRole.value = "SCOUT";
  document.querySelectorAll(".team-chk").forEach(chk => chk.checked = false);
}

window.editUser = function(userId) {
  authFetch("/api/admin/users").then(r => r.json()).then(users => {
    const u = users.find(x => x.id === userId);
    if (!u) return;

    editUserId.value = u.id;
    userFormTitle.textContent = `Modifica Utente: ${u.username}`;
    newUsername.value = u.username;
    newUsername.disabled = true;
    newPassword.value = "";
    newPassword.required = false;
    passwordHint.style.display = "block";
    newEmail.value = u.email || "";
    newRole.value = u.role;

    const userTeamIds = new Set(u.team_ids || []);
    document.querySelectorAll(".team-chk").forEach(chk => {
      chk.checked = userTeamIds.has(parseInt(chk.value));
    });
  });
};

window.deleteUser = async function(userId) {
  if (!confirm("Sei sicuro di voler eliminare questo utente?")) return;
  try {
    const res = await authFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Errore cancellazione");
    await loadAdminUsers();
  } catch (err) {
    alert(err.message);
  }
};

async function handleSaveUser(e) {
  e.preventDefault();
  userFormStatus.innerHTML = '<span style="color:#38bdf8;">Salvataggio...</span>';

  const uid = editUserId.value;
  const selectedTeams = Array.from(document.querySelectorAll(".team-chk:checked")).map(c => parseInt(c.value));

  try {
    if (uid) {
      // Modifica
      const payload = {
        email: newEmail.value || null,
        role: newRole.value,
        team_ids: selectedTeams
      };
      if (newPassword.value) payload.password = newPassword.value;

      const res = await authFetch(`/api/admin/users/${uid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error((await res.json()).detail);
    } else {
      // Creazione
      const payload = {
        username: newUsername.value.trim(),
        password: newPassword.value,
        email: newEmail.value || null,
        role: newRole.value,
        team_ids: selectedTeams
      };
      const res = await authFetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error((await res.json()).detail);
    }

    userFormStatus.innerHTML = '<span style="color:#10b981;">Salvataggio riuscito!</span>';
    resetUserForm();
    await loadAdminUsers();

  } catch (err) {
    userFormStatus.innerHTML = `<span style="color:#ef4444;">❌ ${err.message}</span>`;
  }
}

// --- ADMIN RULES MANAGEMENT ---
async function openAdminRulesModal() {
  adminRulesModal.classList.add("open");
  await loadAdminRules();
}

async function loadAdminRules() {
  try {
    const res = await authFetch("/api/admin/rules/terminal");
    if (!res.ok) return;
    const rules = await res.json();
    rulesTbody.innerHTML = "";
    rules.forEach((r, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(r.description || "-")}</td>
        <td><code>${r.terminal_skill}</code></td>
        <td><code>${r.terminal_eval}</code></td>
        <td><code>${(r.followup_skills || []).join(", ")}</code></td>
        <td><code>${(r.followup_evals || []).join(", ")}</code></td>
        <td>${r.must_be_opponent ? "Avversaria" : "Stessa Squadra"}</td>
        <td>
          <button class="btn btn-danger" style="padding:2px 8px; font-size:0.75rem;" onclick="deleteRule(${idx})">🗑️</button>
        </td>
      `;
      rulesTbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Errore caricamento regole:", err);
  }
}

window.deleteRule = async function(idx) {
  if (!confirm("Eliminare questa regola di tocco correlato?")) return;
  try {
    const res = await authFetch(`/api/admin/rules/terminal/${idx}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail);
    await loadAdminRules();
  } catch (err) {
    alert(err.message);
  }
};

async function handleAddRule() {
  const desc = ruleDesc.value.trim();
  const tSkill = ruleTermSkill.value;
  const tEval = ruleTermEval.value;
  const fSkills = ruleFollowSkills.value.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
  const fEvals = ruleFollowEvals.value.split(",").map(e => e.trim()).filter(Boolean);
  const isOpp = ruleMustOpponent.value === "true";

  if (!desc || fSkills.length === 0 || fEvals.length === 0) {
    alert("Compila tutti i campi della regola.");
    return;
  }

  try {
    const res = await authFetch("/api/admin/rules/terminal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description: desc,
        terminal_skill: tSkill,
        terminal_eval: tEval,
        followup_skills: fSkills,
        followup_evals: fEvals,
        must_be_opponent: isOpp
      })
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    ruleDesc.value = "";
    ruleFollowSkills.value = "";
    ruleFollowEvals.value = "";
    await loadAdminRules();
  } catch (err) {
    alert(err.message);
  }
}

async function handleRevalidateMatches() {
  btnRevalidateMatches.disabled = true;
  btnRevalidateMatches.textContent = "⏳ Rivalutazione...";
  try {
    const res = await authFetch("/api/admin/rules/revalidate", { method: "POST" });
    const data = await res.json();
    alert(`Rivalutazione completata su ${data.revalidated_matches.length} partite!`);
    if (state.currentMatchId) selectMatch(state.currentMatchId);
  } catch (err) {
    alert(err.message);
  } finally {
    btnRevalidateMatches.disabled = false;
    btnRevalidateMatches.textContent = "🔄 Rivalida Gare";
  }
}

// --- ADMIN LOGINS AUDIT (IP TRACKING) ---
async function openAdminLoginsModal() {
  adminLoginsModal.classList.add("open");
  await loadAdminLogins();
}

async function loadAdminLogins() {
  try {
    const res = await authFetch("/api/admin/logins?limit=100");
    if (!res.ok) return;
    const logins = await res.json();
    loginsTbody.innerHTML = "";
    logins.forEach(l => {
      const tr = document.createElement("tr");
      const statusClass = l.login_status === "SUCCESS" ? "team-chip home" : "team-chip away";
      tr.innerHTML = `
        <td><small>${l.logged_at}</small></td>
        <td><strong>${escapeHtml(l.username)}</strong></td>
        <td><code>${escapeHtml(l.ip_address || "N.D.")}</code></td>
        <td><span class="${statusClass}">${l.login_status}</span></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(l.user_agent || "-")}</small></td>
      `;
      loginsTbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Errore caricamento log accessi:", err);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
