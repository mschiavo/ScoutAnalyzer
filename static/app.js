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

// Modals - Admin Matches
const adminMatchesModal = document.getElementById("admin-matches-modal");
const btnOpenMatchesModal = document.getElementById("btn-open-matches-modal");
const btnCloseMatchesModal = document.getElementById("btn-close-matches-modal");
const adminMatchesTbody = document.getElementById("admin-matches-tbody");
const btnClearAllMatches = document.getElementById("btn-clear-all-matches");
const btnQuickDeleteMatch = document.getElementById("btn-quick-delete-match");

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  checkAuth();
  fetchVersion();
});

async function fetchVersion() {
  try {
    const res = await fetch("/api/version");
    if (!res.ok) return;
    const v = await res.json();
    const badge = document.getElementById("app-version-badge");
    if (badge) {
      badge.textContent = `v${v.version} (${v.database_type})`;
      badge.title = `Database: ${v.sqlite_path || v.database_type} | Storage: ${v.storage_backend}`;
    }
  } catch (_) {}
}

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
    btnQuickDeleteMatch.style.display = state.currentMatchId ? "inline-block" : "none";
  } else {
    // Utente SCOUT: nascondi comandi admin e upload
    adminNavGroup.style.display = "none";
    btnQuickDeleteMatch.style.display = "none";
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
  btnRunAudit.addEventListener("click", () => {
    if (auditFileInput && auditFileInput.files && auditFileInput.files.length > 0) {
      uploadAndAuditFiles(auditFileInput.files);
    } else {
      runAuditFile();
    }
  });
  if (auditFileInput) {
    auditFileInput.addEventListener("change", (e) => {
      const files = e.target.files;
      const lbl = document.getElementById("upload-file-label");
      if (files && files.length === 1) {
        if (lbl) lbl.innerHTML = `<strong>File selezionato:</strong> <code>${escapeHtml(files[0].name)}</code>`;
        autoDetectMatchHierarchy(files[0].name);
      } else if (files && files.length > 1) {
        if (lbl) lbl.innerHTML = `<strong>Selezionati ${files.length} file .dvw</strong> per l'audit cumulativo.`;
        autoDetectMatchHierarchy(files[0].name);
      }
    });
  }
  document.querySelectorAll(".preset-file").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      auditFilePathInput.value = link.dataset.path;
      autoDetectMatchHierarchy(link.dataset.path);
    });
  });
  if (auditFilePathInput) {
    auditFilePathInput.addEventListener("input", (e) => {
      autoDetectMatchHierarchy(e.target.value);
    });
  }

  document.getElementById("btn-open-rosters").addEventListener("click", () => switchView("admin-rosters"));
  document.getElementById("btn-open-teams").addEventListener("click", openTeamManagement);
  document.getElementById("btn-roster-teams").addEventListener("click", openTeamManagement);
  document.getElementById("btn-close-teams").addEventListener("click", () => document.getElementById("admin-teams-modal").classList.remove("open"));
  document.getElementById("btn-import-teams").addEventListener("click", importTeamCatalog);
  document.getElementById("btn-import-a3f-teams").addEventListener("click", importA3FTeamCatalog);
  document.getElementById("admin-team-form").addEventListener("submit", saveTeamSettings);
  document.getElementById("admin-team-select").addEventListener("change", fillTeamSettings);
  document.getElementById("btn-rosters-back").addEventListener("click", () => switchView("dashboard"));
  btnSyncRosters.addEventListener("click", () => syncRosters(null, true));
  document.getElementById("btn-import-local-rosters").addEventListener("click", () => syncRosters());

  // Admin Modals
  btnOpenUsersModal.addEventListener("click", openAdminUsersModal);
  btnCloseUsersModal.addEventListener("click", () => adminUsersModal.classList.remove("open"));
  createUserForm.addEventListener("submit", handleSaveUser);

  btnOpenRulesModal.addEventListener("click", openAdminRulesModal);
  btnCloseRulesModal.addEventListener("click", () => adminRulesModal.classList.remove("open"));
  document.getElementById("substitution-settings-form").addEventListener("submit", saveSubstitutionSettings);
  btnAddRule.addEventListener("click", handleAddRule);
  btnRevalidateMatches.addEventListener("click", handleRevalidateMatches);

  btnOpenLoginsModal.addEventListener("click", openAdminLoginsModal);
  btnCloseLoginsModal.addEventListener("click", () => adminLoginsModal.classList.remove("open"));

  // Admin Matches Navigation & Actions
  btnOpenMatchesModal.addEventListener("click", () => switchView("admin-matches"));
  const btnBackToDashboard = document.getElementById("btn-back-to-dashboard");
  if (btnBackToDashboard) {
    btnBackToDashboard.addEventListener("click", () => switchView("dashboard"));
  }
  const btnAdminRevalAll = document.getElementById("btn-admin-revalidate-all");
  if (btnAdminRevalAll) {
    btnAdminRevalAll.addEventListener("click", handleAdminRevalidateAllMatches);
  }
  const btnClearAllMatchesPage = document.getElementById("btn-clear-all-matches-page");
  if (btnClearAllMatchesPage) {
    btnClearAllMatchesPage.addEventListener("click", clearAllMatches);
  }
  if (btnCloseMatchesModal) {
    btnCloseMatchesModal.addEventListener("click", () => adminMatchesModal.classList.remove("open"));
  }
  if (btnClearAllMatches) {
    btnClearAllMatches.addEventListener("click", clearAllMatches);
  }
  btnQuickDeleteMatch.addEventListener("click", () => {
    if (state.currentMatchId) {
      const currentMatch = state.matches.find(m => m.id === state.currentMatchId);
      const code = currentMatch ? currentMatch.match_code : "selezionata";
      deleteMatch(state.currentMatchId, code);
    }
  });

  // Dropdown Gestione Admin
  const btnAdminDropdown = document.getElementById("btn-admin-dropdown");
  const adminDropdownMenu = document.getElementById("admin-dropdown-menu");
  if (btnAdminDropdown && adminDropdownMenu) {
    btnAdminDropdown.addEventListener("click", (e) => {
      e.stopPropagation();
      adminDropdownMenu.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest("#admin-dropdown-wrapper")) {
        adminDropdownMenu.classList.remove("open");
      }
    });

    adminDropdownMenu.querySelectorAll(".dropdown-item").forEach(item => {
      item.addEventListener("click", () => {
        adminDropdownMenu.classList.remove("open");
      });
    });
  }
}

// --- MATCH DATA API & RENDER ---
async function loadMatches(preferredMatchId = null) {
  try {
    const res = await authFetch("/api/matches");
    if (!res.ok) return;
    state.matches = await res.json();
    populateMatchSelect();
    if (state.matches.length > 0) {
      let targetId = state.matches[0].id;
      if (preferredMatchId && state.matches.some(m => m.id === preferredMatchId)) {
        targetId = preferredMatchId;
      }
      matchSelect.value = targetId;
      await selectMatch(targetId);
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
    const home = m.home_name || m.home_code || "Casa";
    const away = m.away_name || m.away_code || "Ospite";
    opt.textContent = `${home} - ${away}`;
    matchSelect.appendChild(opt);
  });
}

function resetMatchDisplay() {
  homeTeamName.textContent = "--";
  homeTeamCode.textContent = "---";
  awayTeamName.textContent = "--";
  awayTeamCode.textContent = "---";
  setsDisplay.innerHTML = '<span class="no-match-msg">Nessuna partita disponibile</span>';
  eventsTbody.innerHTML = '<tr><td colspan="10" class="empty-state">Nessuna partita disponibile.</td></tr>';
  if (btnQuickDeleteMatch) btnQuickDeleteMatch.style.display = "none";
}

async function selectMatch(matchId) {
  if (!matchId) return;
  state.currentMatchId = matchId;
  matchSelect.value = matchId;
  if (btnQuickDeleteMatch && state.currentUser && state.currentUser.role === "ADMIN") {
    btnQuickDeleteMatch.style.display = "inline-block";
  }
  try {
    const [detailRes, eventsRes, logsRes] = await Promise.all([
      authFetch(`/api/matches/${matchId}`),
      authFetch(`/api/matches/${matchId}/events?limit=3000`),
      authFetch(`/api/matches/${matchId}/logs`)
    ]);

    if (!detailRes.ok) {
      const err = await detailRes.json().catch(() => ({}));
      console.warn(`[MatchDetail] Partita #${matchId} non caricabile:`, err.detail || detailRes.statusText);
      resetMatchDisplay();
      return;
    }

    state.currentMatchDetail = await detailRes.json();
    state.events = await eventsRes.json();
    state.logs = await logsRes.json();

    if (filterErrorsOnly) {
      state.errorsOnly = filterErrorsOnly.checked;
    }

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
    const isError = ev.is_valid === 0 || ev.is_valid === false || Boolean(ev.error_note);
    if (state.errorsOnly && !isError) {
      return false;
    }
    return true;
  });

  // Mostra eventuali anomalie a livello di set/gara registrate nei logs
  const generalSetLogs = (state.logs || []).filter(l => {
    if (l.validation_source === "ROSTER_VARIATION" && l.parsed_status === "OK") return !state.errorsOnly && state.selectedSet === "all";
    if (!state.errorsOnly) return false;
    if (!l.line_number || (l.raw_code && l.raw_code.startsWith("SET_"))) {
      if (state.selectedSet === "all") return true;
      if (l.raw_code === `SET_${state.selectedSet}`) return true;
    }
    return false;
  });

  const totalShown = filteredEvents.length + generalSetLogs.length;
  eventsCountLabel.textContent = `${totalShown} elementi mostrati (su ${state.events.length} azioni totali)`;

  if (totalShown === 0) {
    const emptyMsg = state.errorsOnly
      ? "Nessuna anomalia riscontrata per i filtri selezionati."
      : "Nessun evento corrisponde ai filtri selezionati.";
    eventsTbody.innerHTML = `<tr><td colspan="10" class="empty-state">${emptyMsg}</td></tr>`;
    return;
  }

  // Visualizza prima le anomalie di set generali se il filtro errori e' attivo
  generalSetLogs.forEach(g => {
    const gTr = document.createElement("tr");
    const isNote = g.validation_source === "ROSTER_VARIATION" && g.parsed_status === "OK";
    if (!isNote) {
      gTr.className = "has-error";
      gTr.style.background = "rgba(239, 68, 68, 0.12)";
    }
    gTr.innerHTML = `
      <td>${isNote ? "Nota" : '<span class="badge-danger">ALERT</span>'}</td>
      <td>${escapeHtml(g.raw_code || "-")}</td>
      <td colspan="5"><strong>${escapeHtml(g.error_summary || "Anomalia rilevata")}</strong></td>
      <td>-</td>
      <td>-</td>
      <td><span class="error-tag">${escapeHtml(g.parsed_status || "WARNING")}</span></td>
    `;
    if (g.validation_source === "ROSTER_VARIATION" && !isNote && state.currentUser?.role === "ADMIN") {
      const button = document.createElement("button");
      button.className = "btn btn-secondary btn-sm";
      button.textContent = "Conferma variazioni";
      button.addEventListener("click", async () => {
        const match = state.currentMatchDetail.match;
        const variations = state.logs.filter(log => log.validation_source === "ROSTER_VARIATION" && log.parsed_status === "WARNING");
        try {
          if (await confirmRosterVariations(match.id, match.file_hash, variations.map(log => log.error_summary))) {
            await selectMatch(match.id);
          }
        } catch (error) {
          alert(error.message);
        }
      });
      gTr.cells[3].replaceChildren(button);
    }
    eventsTbody.appendChild(gTr);
  });

  filteredEvents.forEach((ev, idx) => {
    const tr = document.createElement("tr");
    const isError = ev.is_valid === 0 || ev.is_valid === false || Boolean(ev.error_note);
    if (isError) {
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
  const textName = g.querySelector(".p-name");
  if (textName) {
    if (p && p.last_name) {
      let lName = p.last_name.trim().toUpperCase();
      if (lName.length > 9) lName = lName.substring(0, 8) + ".";
      textName.textContent = lName;
    } else {
      textName.textContent = "";
    }
  }

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
function autoDetectMatchHierarchy(filename) {
  if (!filename) return;
  const lower = filename.toLowerCase();

  // Categoria & Girone nel codice file, es. b1fb, a3fa, cfc.
  const catGirMatch = lower.match(/(?:^|[^a-z0-9])(b1f|b2f|a1f|a2f|a3f|cf|df)([a-z])(?=$|[^a-z0-9])/);
  if (catGirMatch) {
    const cat = catGirMatch[1].toUpperCase();
    const gir = catGirMatch[2].toUpperCase();
    const catSelect = document.getElementById("upload-categoria");
    if (catSelect) catSelect.value = cat;
    const girInput = document.getElementById("upload-girone");
    if (girInput) girInput.value = gir;
  }

  // 2. Giornata: es. &01, g03, giornata_04, and01, andata02, 01_cor-vol
  const gioMatch = lower.match(/(?:giornata[_-]?|g|and[_-]?|&|^)(\d{1,2})/);
  if (gioMatch) {
    const gioNum = parseInt(gioMatch[1], 10);
    const gioFormatted = String(gioNum).padStart(2, "0");
    const gioInput = document.getElementById("upload-giornata");
    if (gioInput) gioInput.value = gioFormatted;
  }

  // 3. Campionato / Stagione: es. 2026-2027 o 2026_2027 o 2026
  const campMatch = lower.match(/(20\d{2}[-_/]?20\d{2})/);
  if (campMatch) {
    const campFormatted = campMatch[1].replace(/[_/]/, "-");
    const campInput = document.getElementById("upload-campionato");
    if (campInput) campInput.value = campFormatted;
  }
}

async function uploadAndAuditFiles(fileList) {
  if (!fileList || fileList.length === 0) return;

  const files = Array.from(fileList);
  btnRunAudit.disabled = true;

  const camp = document.getElementById("upload-campionato").value.trim() || "2026-2027";
  const cat = document.getElementById("upload-categoria").value || "B1F";
  const gir = document.getElementById("upload-girone").value.trim() || "B";
  const gio = document.getElementById("upload-giornata").value.trim() || "01";

  let successCount = 0;
  let failCount = 0;
  let discardedCount = 0;
  const errors = [];
  const rosterWarnings = [];
  let lastMatchId = null;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    auditStatus.innerHTML = `
      <span style="color:#38bdf8;">
        ⏳ Caricamento e audit (${i + 1}/${files.length}): <b>${escapeHtml(file.name)}</b>...
      </span>
    `;

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("campionato", camp);
      formData.append("categoria", cat);
      formData.append("girone", gir);
      formData.append("giornata", gio);

      const data = await submitMatchAudit(options => {
        for (const [key, value] of Object.entries(options)) formData.set(key, value);
        return authFetch("/api/audit/upload", { method: "POST", body: formData });
      });
      if (!data) {
        discardedCount++;
        continue;
      }
      successCount++;
      lastMatchId = data.match_id;
      rosterWarnings.push(...data.roster_issues.map(issue => `${file.name}: ${issue}`));
      rosterWarnings.push(...(await pendingRosterVariations(data)).map(issue => `${file.name}: ${issue}`));
    } catch (err) {
      console.error(`Errore upload ${file.name}:`, err);
      failCount++;
      errors.push(`${file.name}: ${err.message}`);
    }
  }

  auditStatus.innerHTML = `
    <div style="color:#10b981; font-weight:bold;">
      ${successCount} file caricati, ${discardedCount} scartati, ${failCount} errori.
      ${errors.map(error => `<div style="color:#ef4444;">${escapeHtml(error)}</div>`).join("")}
      ${rosterWarnings.map(warning => `<div class="error-tag">${escapeHtml(warning)}</div>`).join("")}
    </div>
  `;

  await loadMatches(lastMatchId);

  if (failCount || rosterWarnings.length) {
    btnRunAudit.disabled = false;
    return;
  }

  setTimeout(() => {
    auditModal.classList.remove("open");
    btnRunAudit.disabled = false;
  }, 2200);
}

async function runAuditFile() {
  const path = auditFilePathInput.value.trim();
  if (!path) {
    auditStatus.innerHTML = '<span style="color:#ef4444;">Inserisci il percorso di un file .dvw</span>';
    return;
  }

  const camp = document.getElementById("upload-campionato").value.trim() || "2026-2027";
  const cat = document.getElementById("upload-categoria").value || "B1F";
  const gir = document.getElementById("upload-girone").value.trim() || "B";
  const gio = document.getElementById("upload-giornata").value.trim() || "01";

  auditStatus.innerHTML = '<span style="color:#38bdf8;">⏳ Esecuzione audit in corso...</span>';
  btnRunAudit.disabled = true;

  try {
    const data = await submitMatchAudit(options => authFetch("/api/audit/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: path,
        campionato: camp,
        categoria: cat,
        girone: gir,
        giornata: gio,
        ...options
      })
    }));
    if (!data) {
      auditStatus.textContent = "Caricamento scartato.";
      btnRunAudit.disabled = false;
      return;
    }

    const issues = [...data.roster_issues, ...await pendingRosterVariations(data)];
    auditStatus.innerHTML = `
      <div style="color:#10b981; font-weight:bold;">✅ Audit completato con successo!</div>
      <div style="margin-top:6px; color:#cbd5e1;">
        Partita: <b>${escapeHtml(data.match_code)}</b> | Storage: <code>${escapeHtml(data.storage_path || "--")}</code><br>
        Eventi: ${data.events_count} | Set: ${data.sets_count}
        ${issues.map(issue => `<div class="error-tag">${escapeHtml(issue)}</div>`).join("")}
      </div>
    `;

    await loadMatches();
    selectMatch(data.match_id);

    if (issues.length) {
      btnRunAudit.disabled = false;
      return;
    }

    setTimeout(() => {
      auditModal.classList.remove("open");
      btnRunAudit.disabled = false;
    }, 1800);

  } catch (err) {
    auditStatus.textContent = err.message;
    btnRunAudit.disabled = false;
  }
}

async function confirmRosterVariations(matchId, hash, variations) {
  if (!variations.length || !confirm(`Variazioni dichiarate a referto:\n${variations.join("\n")}\n\nConfermarle come note per questa rilevazione?`)) return false;
  const res = await authFetch(`/api/admin/matches/${matchId}/confirm-roster-variations?file_hash=${encodeURIComponent(hash)}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseErrorResponse(res, "Impossibile confermare le variazioni"));
  return true;
}

async function pendingRosterVariations(data) {
  const variations = data.roster_variations || [];
  try {
    return await confirmRosterVariations(data.match_id, data.file_hash, variations) ? [] : variations;
  } catch (error) {
    return [...variations, error.message];
  }
}

async function submitMatchAudit(submit) {
  const options = {};
  for (let attempt = 0; attempt < 3; attempt++) {
    const res = await submit(options);
    const data = await res.json();
    if (res.ok) return data;
    const detail = data.detail;
    if (res.status === 409 && detail?.code === "identical_file") {
      alert(`File identico già importato.\n${auditMatchSummary(detail.matches[0])}`);
      return null;
    }
    if (res.status === 409 && detail?.code === "duplicate_match" && !options.replace_match_id && !options.create_new) {
      const decision = await chooseDuplicateAudit(detail);
      if (!decision) return null;
      Object.assign(options, decision);
      continue;
    }
    if (res.status === 409 && detail?.code === "unknown_rosters" && !options.roster_policy) {
      const names = detail.teams.map(team => `${team.name} (${team.code})`).join(", ");
      options.roster_policy = confirm(`Roster sconosciuti: ${names}.\n\nPremi OK per salvarli nel database oppure Annulla per importare solo la gara.`) ? "add" : "skip";
      continue;
    }
    throw new Error(detail?.message || detail || "Errore durante il caricamento");
  }
  throw new Error("Impossibile completare le conferme di importazione.");
}

function auditMatchSummary(match) {
  return `${match.home_name || "—"} (casa) · ${match.away_name || "—"} (ospite) · Rilevatore ${match.scout_author || "non indicato"} · Giornata ${match.giornata ?? "—"} · ${match.match_code}.dvw`;
}

function chooseDuplicateAudit({ incoming, matches }) {
  const dialog = document.getElementById("duplicate-audit-dialog");
  const existing = document.getElementById("duplicate-audit-existing");
  const target = document.getElementById("duplicate-audit-target");
  document.getElementById("duplicate-audit-incoming").textContent = `Nuovo file: ${auditMatchSummary(incoming)}`;
  existing.replaceChildren(...matches.map(match => {
    const item = document.createElement("li");
    item.textContent = `Import #${match.id} · ${auditMatchSummary(match)}`;
    return item;
  }));
  const replaceable = matches.filter(match => match.replaceable);
  target.replaceChildren(...replaceable.map(match => new Option(`#${match.id} · ${match.match_code}`, match.id)));
  target.disabled = !replaceable.length;
  document.getElementById("duplicate-audit-replace").disabled = !replaceable.length;
  dialog.returnValue = "discard";
  return new Promise(resolve => {
    dialog.addEventListener("close", () => {
      if (dialog.returnValue === "replace" && target.value) {
        const original = replaceable.find(match => match.id === Number(target.value));
        resolve({ replace_match_id: original.id, ...(original.file_hash ? { replace_file_hash: original.file_hash } : {}) });
      }
      else if (dialog.returnValue === "new") resolve({ create_new: true });
      else resolve(null);
    }, { once: true });
    dialog.showModal();
  });
}

async function openTeamManagement() {
  document.getElementById("admin-teams-modal").classList.add("open");
  const status = document.getElementById("admin-teams-status");
  status.textContent = "Caricamento squadre…";
  try {
    await refreshTeamOptions();
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  }
}

async function refreshTeamOptions(selectedId = "") {
  const res = await authFetch("/api/admin/teams");
  if (!res.ok) throw new Error(await parseErrorResponse(res, "Impossibile caricare le squadre"));
  const teams = await res.json();
  const select = document.getElementById("admin-team-select");
  select.replaceChildren(new Option("Nuova squadra", ""));
  for (const team of teams) {
    const option = new Option(`${team.name} (${team.code})`, team.id);
    option.dataset.code = team.code;
    option.dataset.name = team.name;
    option.dataset.rosterCode = team.roster_code || "";
    select.append(option);
  }
  document.getElementById("admin-team-count").textContent = teams.length === 1
    ? "1 squadra censita" : `${teams.length} squadre censite`;
  select.value = selectedId;
  fillTeamSettings();
  if (document.getElementById("view-admin-rosters").style.display === "flex") await renderAdminRosters();
}

function fillTeamSettings() {
  const select = document.getElementById("admin-team-select");
  const selected = select.selectedOptions[0]?.dataset || {};
  const code = document.getElementById("admin-team-code");
  code.value = selected.code || "";
  code.readOnly = Boolean(select.value);
  document.getElementById("admin-team-name").value = selected.name || "";
  document.getElementById("admin-team-roster-code").value = selected.rosterCode || "";
}

async function saveTeamSettings(event) {
  event.preventDefault();
  const status = document.getElementById("admin-teams-status");
  const teamId = document.getElementById("admin-team-select").value;
  const payload = {
    code: document.getElementById("admin-team-code").value.trim(),
    name: document.getElementById("admin-team-name").value.trim(),
    roster_code: document.getElementById("admin-team-roster-code").value.trim() || null
  };
  const button = event.submitter;
  button.disabled = true;
  try {
    const res = await authFetch(`/api/admin/teams${teamId ? `/${teamId}` : ""}`, {
      method: teamId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(await parseErrorResponse(res, "Impossibile salvare la squadra"));
    await refreshTeamOptions(teamId);
    status.textContent = "Squadra salvata.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function importTeamCatalog(event) {
  if (!confirm("Importare il catalogo B1F, girone B, stagione 2026/27?")) return;
  const button = event.currentTarget;
  const status = document.getElementById("admin-teams-status");
  button.disabled = true;
  try {
    const res = await authFetch("/api/admin/teams/import-b1f-b", { method: "POST" });
    if (!res.ok) throw new Error(await parseErrorResponse(res, "Importazione del catalogo non riuscita"));
    const data = await res.json();
    await refreshTeamOptions();
    status.textContent = !data.added && !data.linked && !data.conflicts.length
      ? "Catalogo già importato. Scegli una squadra dal menu per consultarla."
      : [`Squadre aggiunte: ${data.added}. Codici roster completati: ${data.linked}.`, ...data.conflicts].join(" ");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function importA3FTeamCatalog(event) {
  if (!confirm("Importare il catalogo A3F, girone B, stagione 2026/27?")) return;
  const button = event.currentTarget;
  const status = document.getElementById("admin-teams-status");
  button.disabled = true;
  try {
    const res = await authFetch("/api/admin/teams/import-a3f-b", { method: "POST" });
    if (!res.ok) throw new Error(await parseErrorResponse(res, "Importazione del catalogo A3F non riuscita"));
    const data = await res.json();
    await refreshTeamOptions();
    status.textContent = !data.added && !data.linked && !data.conflicts.length
      ? "Catalogo A3F già importato. I codici squadra DVW provvisori saranno aggiornati al primo scout riconosciuto per nome."
      : [`Squadre aggiunte: ${data.added}. Codici roster completati: ${data.linked}. I codici DVW provvisori saranno aggiornati al primo scout riconosciuto per nome.`, ...data.conflicts].join(" ");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function syncRosters(teamCode, download = false) {
  if (btnSyncRosters.disabled) return;
  const status = document.getElementById("roster-status");
  const buttons = [btnSyncRosters, document.getElementById("btn-import-local-rosters"), ...document.querySelectorAll(".btn-roster-action")];
  buttons.forEach(button => { button.disabled = true; });
  status.textContent = download ? "Download e sincronizzazione in corso…" : "Importazione in corso…";
  try {
    const res = await authFetch("/api/rosters/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ team_code: teamCode, download })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Importazione non riuscita");
    const results = data.results.map(entry => Array.isArray(entry) ? entry[1] : entry);
    const errors = results.filter(result => result.status !== "SUCCESS").map(result => result.message);
    const backups = results.filter(result => result.backup_created).length;
    status.textContent = results.length
      ? [`${results.length - errors.length} di ${results.length} roster sincronizzati.`, ...(backups ? [`Backup creati: ${backups}.`] : []), ...errors].join(" ")
      : "Nessuna squadra con codice roster configurato.";
    await renderAdminRosters();
  } catch (err) {
    status.textContent = `Errore importazione roster: ${err.message}`;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}

async function renderAdminRosters() {
  const tbody = document.getElementById("admin-rosters-tbody");
  const showMessage = message => {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${escapeHtml(message)}</td></tr>`;
  };
  showMessage("Caricamento roster…");
  try {
    const res = await authFetch("/api/admin/rosters");
    if (!res.ok) throw new Error("Impossibile caricare i roster.");
    const teams = await res.json();
    if (!teams.length) {
      showMessage("Nessuna squadra presente nel database.");
      return;
    }
    tbody.replaceChildren();
    for (const team of teams) {
      const row = tbody.insertRow();
      for (const value of [team.name, team.code, team.roster_code || "Codice roster mancante", team.active_players]) {
        row.insertCell().textContent = value;
      }
      const actions = row.insertCell();
      actions.innerHTML = '<button type="button" class="btn btn-secondary btn-sm" aria-expanded="false">Dettaglio</button>';
      actions.firstElementChild.addEventListener("click", event => toggleRosterDetail(row, team.id, event.currentTarget));
      if (team.roster_code) {
        for (const [label, download] of [["Importa .sq", false], ["Riscarica e sincronizza", true]]) {
          const button = document.createElement("button");
          button.className = "btn btn-secondary btn-sm btn-roster-action";
          button.textContent = label;
          button.addEventListener("click", () => syncRosters(team.code, download));
          actions.append(" ", button);
        }
      }
      const remove = document.createElement("button");
      remove.className = "btn btn-danger btn-sm btn-roster-action";
      remove.textContent = "Disattiva roster";
      remove.addEventListener("click", () => disableRoster(team));
      actions.append(" ", remove);
    }
  } catch (err) {
    showMessage(err.message);
  }
}

async function disableRoster(team) {
  if (btnSyncRosters.disabled || !confirm(`Disattivare il roster di ${team.name}? Le gare resteranno visibili.`)) return;
  const status = document.getElementById("roster-status");
  try {
    const res = await authFetch(`/api/admin/rosters/${team.id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await parseErrorResponse(res, "Impossibile disattivare il roster"));
    status.textContent = `Roster di ${team.name} disattivato.`;
    await renderAdminRosters();
  } catch (err) {
    status.textContent = err.message;
  }
}

async function toggleRosterDetail(row, teamId, button) {
  if (button.getAttribute("aria-expanded") === "true") {
    row.nextElementSibling.remove();
    button.setAttribute("aria-expanded", "false");
    return;
  }
  const detail = document.createElement("tr");
  row.after(detail);
  const cell = detail.insertCell();
  cell.colSpan = row.cells.length;
  cell.textContent = "Caricamento atlete…";
  button.setAttribute("aria-expanded", "true");
  try {
    const res = await authFetch(`/api/admin/rosters/${teamId}`);
    if (!res.ok) throw new Error("Impossibile caricare il dettaglio del roster.");
    const players = await res.json();
    if (!players.length) {
      cell.textContent = "Nessuna atleta registrata per questa squadra.";
      return;
    }
    cell.innerHTML = `<table class="simple-table">
      <thead><tr><th>Maglia</th><th>Atleta</th><th>Ruolo</th><th>Dal</th><th>Al</th></tr></thead>
      <tbody>${players.map(player => `<tr>${[
        player.shirt_number, `${player.last_name} ${player.first_name}`, player.role,
        player.valid_from, player.valid_to || "Attiva"
      ].map(value => `<td>${escapeHtml(String(value ?? "—"))}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>`;
  } catch (err) {
    cell.textContent = err.message;
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
      lbl.title = `${t.code} - ${t.name}`;
      lbl.innerHTML = `
        <input type="checkbox" value="${t.id}" class="team-chk" />
        <span class="team-code-badge">${escapeHtml(t.code)}</span>
        <span class="team-sep">-</span>
        <span class="team-name-text">${escapeHtml(t.name)}</span>
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
      const teamBadges = u.role === "ADMIN" ? "Tutte" :
        (u.teams || []).map(t => `<small style="background:#26334d; padding:2px 4px; border-radius:3px;">${escapeHtml(t.code)}</small>`).join(" ") || "<em>Nessuna</em>";
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
  await Promise.all([loadAdminRules(), loadSubstitutionSettings()]);
}

async function loadSubstitutionSettings() {
  const input = document.getElementById("max-substitutions-per-set");
  const button = input.form.querySelector("button");
  const status = document.getElementById("substitution-settings-status");
  input.disabled = button.disabled = true;
  status.textContent = "Caricamento limite…";
  try {
    const response = await authFetch("/api/admin/rules/substitutions");
    if (!response.ok) throw new Error(await parseErrorResponse(response, "Impossibile caricare il limite"));
    input.value = (await response.json()).max_substitutions_per_set;
    input.disabled = button.disabled = false;
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  }
}

async function saveSubstitutionSettings(event) {
  event.preventDefault();
  const input = document.getElementById("max-substitutions-per-set");
  const button = event.currentTarget.querySelector("button");
  const status = document.getElementById("substitution-settings-status");
  button.disabled = true;
  try {
    const response = await authFetch("/api/admin/rules/substitutions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_substitutions_per_set: input.valueAsNumber })
    });
    if (!response.ok) throw new Error(await parseErrorResponse(response, "Impossibile salvare il limite"));
    input.value = (await response.json()).max_substitutions_per_set;
    status.textContent = "Limite salvato. Usa Rivalida Gare per aggiornare le anomalie delle gare già caricate.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
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

async function parseErrorResponse(res, defaultMsg = "Errore durante l'operazione") {
  try {
    const text = await res.text();
    if (!text) return defaultMsg;
    try {
      const j = JSON.parse(text);
      return j.detail || j.error || text;
    } catch (_) {
      return text;
    }
  } catch (_) {
    return defaultMsg;
  }
}

async function handleRevalidateMatches() {
  btnRevalidateMatches.disabled = true;
  btnRevalidateMatches.textContent = "⏳ Rivalutazione...";
  try {
    const res = await requestRevalidation("/api/admin/rules/revalidate");
    if (!res) return;
    if (!res.ok) {
      throw new Error(await parseErrorResponse(res, "Errore durante la rivalutazione"));
    }
    const data = await res.json();
    const count = data.revalidated_matches ? data.revalidated_matches.length : 0;
    alert(`Rivalutazione completata su ${count} partite!`);
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

// --- VIEW SWITCHING (SPA) ---
function switchView(viewName) {
  const views = ["dashboard", "admin-matches", "admin-rosters"];
  const selected = views.includes(viewName) ? viewName : "dashboard";
  for (const view of views) {
    document.getElementById(`view-${view}`).style.display = view === selected ? "flex" : "none";
  }
  if (selected === "admin-matches") renderAdminMatchesFullTable();
  if (selected === "admin-rosters") renderAdminRosters();
}
window.switchView = switchView;

function openMatchInDashboard(matchId) {
  switchView("dashboard");
  selectMatch(matchId);
}
window.openMatchInDashboard = openMatchInDashboard;

async function renderAdminMatchesFullTable() {
  const tbody = document.getElementById("admin-matches-full-tbody");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Caricamento partite...</td></tr>';
  try {
    const res = await authFetch("/api/matches");
    if (!res.ok) throw new Error("Errore nel recupero delle partite");
    const matches = await res.json();

    if (!matches || matches.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Nessuna partita presente nel database.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    matches.forEach(m => {
      const tr = document.createElement("tr");
      const logsColor = (m.logs_count || 0) > 0 ? "#f87171" : "#10b981";
      tr.innerHTML = `
        <td><code>${escapeHtml(m.match_code)}</code></td>
        <td><span class="scout-author-chip">${escapeHtml(m.scout_author || "N.D.")}</span></td>
        <td><strong>${escapeHtml(m.home_name || m.home_code || "-")}</strong></td>
        <td><strong>${escapeHtml(m.away_name || m.away_code || "-")}</strong></td>
        <td style="text-align: center;"><span class="score-badge-final">${m.final_score || "0 - 0"}</span></td>
        <td><span class="set-partials-text">${escapeHtml(m.set_scores || "N.D.")}</span></td>
        <td style="text-align: center;"><b>${m.events_count || 0}</b></td>
        <td style="text-align: center;"><b style="color: ${logsColor};">${m.logs_count || 0}</b></td>
        <td style="text-align: center; white-space: nowrap;">
          <button class="btn btn-primary btn-sm" onclick="openMatchInDashboard(${m.id})">👁️ Apri Gara</button>
          <button class="btn btn-secondary btn-sm" id="btn-reval-${m.id}" onclick="revalidateMatchFromAdmin(${m.id})">🔄 Valida Gara</button>
          <button class="btn btn-danger btn-sm" onclick="deleteMatch(${m.id}, '${escapeHtml(m.match_code)}')">🗑️ Elimina</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="color:#ef4444;">${err.message}</td></tr>`;
  }
}

async function requestRevalidation(url) {
  const response = await authFetch(url, { method: "POST" });
  if (response.status !== 409) return response;
  const data = await response.clone().json();
  if (data.detail?.code !== "inactive_rosters") return response;
  const names = data.detail.teams.map(team => team.name).join(", ");
  if (!confirm(`Roster disattivati: ${names}.\n\nVuoi riabilitarli e continuare la rivalidazione?`)) return null;
  return authFetch(`${url}?reactivate_rosters=true`, { method: "POST" });
}

async function revalidateMatchFromAdmin(matchId) {
  const btn = document.getElementById(`btn-reval-${matchId}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳...";
  }
  try {
    const res = await requestRevalidation(`/api/admin/matches/${matchId}/revalidate`);
    if (!res) return;
    if (!res.ok) {
      throw new Error(await parseErrorResponse(res, "Errore durante la validazione della partita"));
    }
    const data = await res.json();
    alert(`Validazione completata per gara #${matchId}! Anomalie rilevate: ${data.issues_count}`);
    await renderAdminMatchesFullTable();
    await loadMatches();
  } catch (err) {
    alert(err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄 Valida Gara";
    }
  }
}
window.revalidateMatchFromAdmin = revalidateMatchFromAdmin;

async function handleAdminRevalidateAllMatches() {
  const btn = document.getElementById("btn-admin-revalidate-all");
  const count = (state.matches && state.matches.length) ? state.matches.length : 0;
  if (count > 30) {
    const ok = confirm(`Ci sono ${count} gare caricate a sistema (più di 30).\nLa validazione completa potrebbe richiedere del tempo.\n\nVuoi continuare?`);
    if (!ok) return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Validazione in corso...";
  }
  try {
    const res = await requestRevalidation("/api/admin/rules/revalidate");
    if (!res) return;
    if (!res.ok) {
      throw new Error(await parseErrorResponse(res, "Errore durante la rivalutazione massiva"));
    }
    const data = await res.json();
    const revalCount = data.revalidated_matches ? data.revalidated_matches.length : count;
    alert(`Rivalutazione massiva completata con successo su ${revalCount} partite!`);
    await renderAdminMatchesFullTable();
    await loadMatches();
  } catch (err) {
    alert(err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄 Valida Tutte le Gare";
    }
  }
}
window.handleAdminRevalidateAllMatches = handleAdminRevalidateAllMatches;

// --- ADMIN MATCHES MANAGEMENT ---
async function openAdminMatchesModal() {
  switchView("admin-matches");
}

async function renderAdminMatchesTable() {
  adminMatchesTbody.innerHTML = '<tr><td colspan="8" class="empty-state">Caricamento partite...</td></tr>';
  try {
    const res = await authFetch("/api/matches");
    if (!res.ok) throw new Error("Errore nel recupero delle partite");
    const matches = await res.json();

    if (!matches || matches.length === 0) {
      adminMatchesTbody.innerHTML = '<tr><td colspan="8" class="empty-state">Nessuna partita presente nel database.</td></tr>';
      return;
    }

    adminMatchesTbody.innerHTML = "";
    matches.forEach(m => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>#${m.id}</strong></td>
        <td><code>${escapeHtml(m.match_code)}</code></td>
        <td>${m.scheduled_date || "N.D."}</td>
        <td>${escapeHtml(m.home_name || m.home_code || "-")}</td>
        <td>${escapeHtml(m.away_name || m.away_code || "-")}</td>
        <td>${m.sets_count || 0}</td>
        <td>${m.events_count || 0}</td>
        <td>
          <button class="btn btn-danger btn-sm" onclick="deleteMatch(${m.id}, '${escapeHtml(m.match_code)}')">🗑️ Elimina</button>
        </td>
      `;
      adminMatchesTbody.appendChild(tr);
    });
  } catch (err) {
    adminMatchesTbody.innerHTML = `<tr><td colspan="8" class="empty-state" style="color:#ef4444;">${err.message}</td></tr>`;
  }
}

async function deleteMatch(matchId, matchCode) {
  if (!confirm(`Sei sicuro di voler eliminare la gara ${matchCode} (ID #${matchId}) e tutti i suoi dati dal database e dallo storage?`)) {
    return;
  }

  try {
    const res = await authFetch(`/api/matches/${matchId}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Errore durante l'eliminazione");

    await loadMatches();
    if (adminMatchesModal && adminMatchesModal.classList.contains("open")) {
      await renderAdminMatchesTable();
    }
    await renderAdminMatchesFullTable();

    if (state.currentMatchId === matchId) {
      if (state.matches.length > 0) {
        selectMatch(state.matches[0].id);
      } else {
        state.currentMatchId = null;
        resetMatchDisplay();
      }
    }
  } catch (err) {
    alert("Errore eliminazione partita: " + err.message);
  }
}
window.deleteMatch = deleteMatch;

async function clearAllMatches() {
  if (!confirm("ATTENZIONE: Sei sicuro di voler eliminare TUTTE le partite archiviate nel database e nello storage? Questa operazione è irreversibile!")) {
    return;
  }

  try {
    const res = await authFetch("/api/admin/matches/clear", { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Errore svuotamento partite");

    await loadMatches();
    if (adminMatchesModal && adminMatchesModal.classList.contains("open")) {
      await renderAdminMatchesTable();
    }
    await renderAdminMatchesFullTable();
    state.currentMatchId = null;
    resetMatchDisplay();
    alert("Tutte le partite sono state eliminate con successo.");
  } catch (err) {
    alert("Errore svuotamento partite: " + err.message);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
