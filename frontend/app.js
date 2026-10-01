/* app.js - the web page logic (plain JavaScript, no frameworks needed). */
const $ = (s) => document.querySelector(s);
let TOKEN = sessionStorage.getItem("token") || "";
let USER = null;
let LAST_SEARCH = null;

/* ---------- helpers ---------- */
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function pct(x) { return (x * 100).toFixed(0) + "%"; }
function toast(msg, bad) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (bad ? " bad" : ""); t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 4500);
}
async function api(path, opts = {}) {
  const headers = Object.assign({ Authorization: "Bearer " + TOKEN }, opts.headers || {});
  let body = opts.body;
  if (body && !(body instanceof FormData)) { body = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, { method: opts.method || "GET", headers, body });
  if (res.status === 401 && TOKEN) { logoutLocal(); throw new Error("Session expired. Please log in again."); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) {}
    throw new Error(msg);
  }
  if (opts.raw) return res;
  return res.json();
}
async function downloadBlob(res, name) {
  const blob = await res.blob(); const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
/* Highlight words inside text. items = [{word, w}] where w is a signed weight. */
function highlight(text, items, mode) {
  const map = {}; let max = 0;
  items.forEach((i) => { const k = String(i.word).toLowerCase(); if (/^[a-z0-9'\-\/]+$/i.test(k)) { map[k] = i.w; max = Math.max(max, Math.abs(i.w)); } });
  const words = Object.keys(map); if (!words.length) return esc(text);
  const re = new RegExp("\\b(" + words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\b", "gi");
  let out = "", last = 0, m;
  while ((m = re.exec(text)) !== null) {
    const w = map[m[0].toLowerCase()]; const a = (0.18 + 0.6 * Math.abs(w) / (max || 1)).toFixed(2);
    const cls = mode === "blue" ? "hl-blue" : w >= 0 ? "hl-pos" : "hl-neg";
    out += esc(text.slice(last, m.index)) + '<span class="' + cls + '" style="--a:' + a + '" title="' + w + '">' + esc(m[0]) + "</span>";
    last = m.index + m[0].length;
  }
  return out + esc(text.slice(last));
}

/* ---------- login / logout ---------- */
async function doLogin() {
  $("#login-error").textContent = "";
  try {
    const r = await api("/api/auth/login", { method: "POST", body: { username: $("#login-user").value, password: $("#login-pass").value } });
    TOKEN = r.token; USER = r.user; sessionStorage.setItem("token", TOKEN); startApp();
  } catch (e) { $("#login-error").textContent = e.message; }
}
function logoutLocal() { TOKEN = ""; USER = null; sessionStorage.removeItem("token"); $("#app-view").hidden = true; $("#login-view").hidden = false; }
$("#login-btn").onclick = doLogin;
$("#login-pass").onkeydown = (e) => { if (e.key === "Enter") doLogin(); };
$("#logout-btn").onclick = async () => { try { await api("/api/auth/logout", { method: "POST" }); } catch (e) {} logoutLocal(); };
$("#modal-close").onclick = () => ($("#modal").hidden = true);

const TABS = {
  dashboard: ["Dashboard", ["admin_staff", "dept_admin", "super_admin"], viewDashboard],
  upload: ["Upload & Classify", ["admin_staff", "super_admin"], viewUpload],
  repo: ["Repository", ["admin_staff", "dept_admin", "super_admin"], viewRepo],
  search: ["Semantic Search", ["dept_admin", "super_admin"], viewSearch],
  admin: ["Administration", ["super_admin"], viewAdmin],
};
async function startApp() {
  if (!USER) { try { USER = await api("/api/auth/me"); } catch (e) { return logoutLocal(); } }
  $("#login-view").hidden = true; $("#app-view").hidden = false;
  $("#who-name").textContent = USER.full_name || USER.username; $("#who-role").textContent = USER.role_label;
  const nav = $("#nav"); nav.innerHTML = "";
  Object.entries(TABS).forEach(([key, [label, roles]]) => {
    if (!roles.includes(USER.role)) return;
    const b = document.createElement("button"); b.textContent = label; b.dataset.key = key; b.onclick = () => openTab(key); nav.appendChild(b);
  });
  openTab("dashboard");
}
function openTab(key) {
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.key === key));
  TABS[key][2]().catch((e) => toast(e.message, true));
}

/* ---------- dashboard ---------- */
async function viewDashboard() {
  const [s, sys] = await Promise.all([api("/api/stats"), api("/api/system")]);
  const m = sys.model || {};
  $("#main").innerHTML = `
  <div class="grid">
    <div class="stat"><b>${s.saved}</b>Documents in repository</div>
    <div class="stat"><b>${s.pending}</b>Awaiting review (not saved)</div>
    <div class="stat"><b>${s.low_confidence}</b>Low-confidence classifications</div>
    <div class="stat"><b>${sys.indexed_passages}</b>Searchable passages</div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Documents per category</h2>
    ${s.per_category.length ? s.per_category.map((c) => `<div style="margin:8px 0"><div class="row"><span class="grow">${esc(c.name)}</span><b>${c.n}</b></div>
      <div class="bar"><i style="width:${s.saved ? (100 * c.n) / s.saved : 0}%"></i></div></div>`).join("") : '<p class="muted">No documents saved yet. Go to Upload &amp; Classify.</p>'}
  </div>
  <div class="card"><h2>System status</h2>
    <table class="t"><tr><th>Component</th><th>Status</th></tr>
    <tr><td>Database</td><td>${esc(sys.database)}</td></tr>
    <tr><td>OCR engine</td><td>${esc(sys.ocr)}</td></tr>
    <tr><td>Semantic search engine</td><td>${esc(sys.embedding_engine)}</td></tr>
    <tr><td>Classifier</td><td>TF-IDF + Logistic Regression &middot; trained on ${m.samples || "?"} documents &middot; hold-out accuracy ${m.holdout_accuracy ?? "n/a"} &middot; ${esc(m.trained_at || "")}</td></tr>
    <tr><td>Explainability</td><td>LIME (classification) and word-removal similarity (search)</td></tr></table>
    <p class="muted">The AI supports decisions; administrative staff always confirm the final category.</p></div>`;
}

/* ---------- upload & classify ---------- */
async function viewUpload() {
  $("#main").innerHTML = `<div class="card"><h2>1. Upload a document</h2>
    <p class="muted">PDF, DOCX, TXT or a scanned image (PNG, JPG, TIFF). Scans are read with OCR.</p>
    <div class="row"><input type="file" id="up-file" class="grow" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.bmp">
    <button id="up-btn" class="btn primary">Scan &amp; Analyse</button></div></div><div id="up-result"></div>`;
  $("#up-btn").onclick = async () => {
    const f = $("#up-file").files[0]; if (!f) return toast("Choose a file first.", true);
    const btn = $("#up-btn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Analysing...';
    try { const fd = new FormData(); fd.append("file", f); const d = await api("/api/documents/analyze", { method: "POST", body: fd }); await renderAnalysis(d); }
    catch (e) { toast(e.message, true); }
    btn.disabled = false; btn.textContent = "Scan & Analyse";
  };
}
async function renderAnalysis(d) {
  const cats = await api("/api/categories"); const ex = d.explanation || {};
  const probs = Object.entries(ex.probabilities || {});
  const feats = (ex.features || []).map((f) => ({ word: f.word, w: f.weight }));
  $("#up-result").innerHTML = `
  <div class="card"><h2>2. AI result for: ${esc(d.filename)}</h2>
    <div class="row"><span>Suggested category:</span> <span class="tag">${esc(d.predicted_category)}</span>
      <span class="tag ${d.low_confidence ? "warn" : "ok"}">Confidence ${pct(d.confidence)}</span>
      <span class="muted">Read by: ${esc(d.ocr_method)}${d.ocr_confidence ? " (OCR confidence " + d.ocr_confidence.toFixed(0) + "%)" : ""}</span></div>
    ${d.low_confidence ? '<div class="note">The AI is not sure about this document. Please check it carefully before saving.</div>' : ""}
    <div class="two"><div><h3>How sure is the AI?</h3>
      ${probs.map(([k, v]) => `<div style="margin:6px 0"><div class="row"><span class="grow">${esc(k)}</span><b>${pct(v)}</b></div><div class="bar ${k === d.predicted_category ? "" : "amber"}"><i style="width:${v * 100}%"></i></div></div>`).join("")}</div>
    <div><h3>Why? Words that decided it <span class="muted">(${esc(ex.method || "")})</span></h3>
      <table class="t"><tr><th>Word</th><th>Influence</th></tr>
      ${feats.map((f) => `<tr><td>${esc(f.word)}</td><td style="color:${f.w >= 0 ? "var(--green)" : "var(--red)"}">${f.w >= 0 ? "+" : ""}${f.w}</td></tr>`).join("")}</table></div></div>
    <h3>Document text with explanation</h3>
    <div class="legend"><span><b style="background:rgba(26,158,92,.5);padding:0 6px">&nbsp;</b> supports "${esc(d.predicted_category)}"</span><span><b style="background:rgba(214,69,69,.5);padding:0 6px">&nbsp;</b> points away</span></div>
    <div class="doc-text">${highlight(d.text, feats, "signed")}</div>
    <h3>3. Staff decision</h3>
    <div class="row"><span>Save as:</span><select id="up-cat">${cats.map((c) => `<option ${c.name === d.predicted_category ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
      <button id="save-btn" class="btn primary">Save to Repository</button><button id="discard-btn" class="btn danger">Discard</button></div>
    <p class="muted">You may change the category if the AI is wrong. Your choice is recorded in the audit log.</p></div>`;
  $("#save-btn").onclick = async () => {
    try { await api("/api/documents/" + d.id + "/save", { method: "POST", body: { category: $("#up-cat").value } });
      toast("Saved to repository."); $("#up-result").innerHTML = ""; $("#up-file").value = ""; } catch (e) { toast(e.message, true); }
  };
  $("#discard-btn").onclick = async () => { try { await api("/api/documents/" + d.id, { method: "DELETE" }); $("#up-result").innerHTML = ""; toast("Discarded."); } catch (e) { toast(e.message, true); } };
}

/* ---------- repository ---------- */
async function viewRepo() {
  const [docs, cats] = await Promise.all([api("/api/documents"), api("/api/categories")]);
  $("#main").innerHTML = `<div class="card"><div class="row"><h2 class="grow">Repository</h2>
    <select id="repo-filter"><option value="">All categories</option>${cats.map((c) => `<option>${esc(c.name)}</option>`).join("")}</select></div>
    <table class="t"><tr><th>ID</th><th>File</th><th>Category</th><th>AI confidence</th><th>Saved</th><th></th></tr>
    ${docs.map((d) => `<tr data-cat="${esc(d.final_category)}"><td>${d.id}</td><td>${esc(d.filename)}</td><td><span class="tag">${esc(d.final_category)}</span></td>
      <td>${pct(d.confidence)}</td><td class="muted">${esc(d.saved_at)}</td>
      <td><button class="btn small" data-view="${d.id}">View</button> <button class="btn small" data-dl="${d.id}" data-name="${esc(d.filename)}">Download</button>
      ${USER.role !== "dept_admin" ? `<button class="btn small danger" data-del="${d.id}">Delete</button>` : ""}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">Nothing saved yet.</td></tr>'}</table></div>`;
  $("#repo-filter").onchange = (e) => document.querySelectorAll("tr[data-cat]").forEach((r) => (r.hidden = e.target.value && r.dataset.cat !== e.target.value));
  attachDocButtons();
}
function attachDocButtons() {
  document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => openDoc(b.dataset.view)));
  document.querySelectorAll("[data-dl]").forEach((b) => (b.onclick = async () => { try { downloadBlob(await api("/api/documents/" + b.dataset.dl + "/download", { raw: true }), b.dataset.name); } catch (e) { toast(e.message, true); } }));
  document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { if (!confirm("Delete this document permanently?")) return;
    try { await api("/api/documents/" + b.dataset.del, { method: "DELETE" }); toast("Deleted."); viewRepo(); } catch (e) { toast(e.message, true); } }));
}
async function openDoc(id, query) {
  const d = await api("/api/documents/" + id); const ex = d.explanation || {};
  const feats = (ex.features || []).map((f) => ({ word: f.word, w: f.weight }));
  $("#modal-body").innerHTML = `<h2>${esc(d.filename)}</h2>
    <div class="row"><span class="tag">${esc(d.final_category || d.predicted_category)}</span><span class="muted">AI suggested: ${esc(d.predicted_category)} (${pct(d.confidence)}) &middot; read by ${esc(d.ocr_method)} &middot; uploaded by ${esc(d.uploaded_by)}</span></div>
    <h3>Why the AI classified it this way <span class="muted">(${esc(ex.method || "")})</span></h3>
    <div class="doc-text">${highlight(d.text, feats, "signed")}</div>`;
  $("#modal").hidden = false;
}

/* ---------- semantic search ---------- */
async function viewSearch() {
  const cats = await api("/api/categories");
  $("#main").innerHTML = `<div class="card"><h2>Semantic search</h2>
    <p class="muted">Ask in normal words, e.g. "students who still owe tuition" or "notice about examination timetable". The system matches meaning, not just exact words.</p>
    <div class="row"><input type="text" id="q" placeholder="Type your question..." class="grow">
    <select id="q-cat"><option value="">All categories</option>${cats.map((c) => `<option>${esc(c.name)}</option>`).join("")}</select>
    <select id="q-k"><option>3</option><option selected>5</option><option>10</option></select>
    <button id="q-btn" class="btn primary">Search</button><button id="q-export" class="btn">Export summary (CSV)</button></div></div><div id="q-res"></div>`;
  $("#q").onkeydown = (e) => { if (e.key === "Enter") runSearch(); };
  $("#q-btn").onclick = runSearch;
  $("#q-export").onclick = async () => {
    if (!LAST_SEARCH) return toast("Run a search first.", true);
    try { downloadBlob(await api("/api/search/export", { method: "POST", body: LAST_SEARCH, raw: true }), "search_summary.csv"); } catch (e) { toast(e.message, true); }
  };
}
async function runSearch() {
  const body = { query: $("#q").value, top_k: +$("#q-k").value, category: $("#q-cat").value || null };
  $("#q-res").innerHTML = '<p><span class="spinner"></span>Searching...</p>';
  try {
    const r = await api("/api/search", { method: "POST", body }); LAST_SEARCH = body;
    $("#q-res").innerHTML = `<p class="muted">Engine: ${esc(r.engine)} &middot; ${r.results.length} result(s), best first</p>` +
      (r.results.map((d) => `<div class="result"><div class="head"><div><b>#${d.rank} ${esc(d.filename)}</b> <span class="tag">${esc(d.final_category)}</span></div>
        <div style="min-width:180px"><div class="muted">Similarity ${d.score.toFixed(3)}</div><div class="bar green"><i style="width:${Math.max(3, Math.min(100, d.score * 100))}%"></i></div></div></div>
        <div class="passage">${esc(d.passage)}</div>
        <div class="row"><button class="btn small" data-why="${d.id}">Why this result?</button><button class="btn small" data-view="${d.id}">View document</button>
        <button class="btn small" data-dl="${d.id}" data-name="${esc(d.filename)}">Download</button></div><div id="why-${d.id}"></div></div>`).join("") || '<p class="muted">Nothing found. Save some documents first.</p>');
    attachDocButtons();
    document.querySelectorAll("[data-why]").forEach((b) => (b.onclick = () => explainResult(b.dataset.why, body.query)));
  } catch (e) { $("#q-res").innerHTML = ""; toast(e.message, true); }
}
async function explainResult(id, query) {
  const box = $("#why-" + id); box.innerHTML = '<p><span class="spinner"></span>Working out why...</p>';
  try {
    const ex = await api("/api/search/explain", { method: "POST", body: { query, document_id: +id } });
    const items = ex.terms.map((t) => ({ word: t.word, w: t.score }));
    box.innerHTML = `<div class="note"><b>Why this result?</b> The passage scored ${ex.score} against your question. Words below are the ones that, when removed,
      lowered the match the most (${esc(ex.method)}).<div class="doc-text" style="margin-top:8px;max-height:none">${highlight(ex.passage, items, "blue")}</div>
      <p>${ex.terms.map((t) => `<span class="tag" style="margin:2px">${esc(t.word)} &nbsp;+${t.score}</span>`).join("")}</p></div>`;
  } catch (e) { box.innerHTML = ""; toast(e.message, true); }
}

/* ---------- administration ---------- */
async function viewAdmin() {
  const [users, cats, logs, sys] = await Promise.all([api("/api/admin/users"), api("/api/admin/categories"), api("/api/admin/logs"), api("/api/system")]);
  const roles = { admin_staff: "Administrative Staff", dept_admin: "Departmental Admin", super_admin: "System SuperAdmin" };
  const opt = (sel) => Object.entries(roles).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${v}</option>`).join("");
  $("#main").innerHTML = `
  <div class="card"><h2>Manage user roles</h2>
    <table class="t"><tr><th>Username</th><th>Name</th><th>Role</th><th>Active</th><th></th></tr>
    ${users.map((u) => `<tr><td>${esc(u.username)}</td><td>${esc(u.full_name)}</td>
      <td><select data-role="${u.id}">${opt(u.role)}</select></td><td><input type="checkbox" data-active="${u.id}" ${u.active ? "checked" : ""}></td>
      <td><button class="btn small" data-edit="${u.id}" data-un="${esc(u.username)}" data-fn="${esc(u.full_name)}">Edit name</button> <button class="btn small" data-pw="${u.id}">Reset password</button></td></tr>`).join("")}</table>
    <h3>Add a user</h3><div class="row"><input id="nu-user" placeholder="username"><input id="nu-name" placeholder="full name"><input id="nu-pass" type="password" placeholder="password (6+)">
    <select id="nu-role">${opt("admin_staff")}</select><button id="nu-btn" class="btn primary">Create</button></div></div>
  <div class="card"><h2>Document categories</h2>
    ${cats.map((c) => `<label style="display:inline-block;margin:4px 14px 4px 0"><input type="checkbox" data-cat="${c.id}" ${c.active ? "checked" : ""}> ${esc(c.name)}</label>`).join("")}
    <div class="row" style="margin-top:10px"><input id="nc-name" placeholder="New category name"><button id="nc-btn" class="btn">Add category</button></div>
    <p class="muted">A new category needs example documents: save some documents under it, then retrain the model.</p></div>
  <div class="card"><h2>Classification model</h2>
    <p>Trained on <b>${sys.model.samples}</b> documents &middot; hold-out accuracy <b>${sys.model.holdout_accuracy ?? "n/a"}</b> &middot; macro F1 <b>${sys.model.holdout_macro_f1 ?? "n/a"}</b> &middot; ${esc(sys.model.trained_at)}</p>
    <button id="rt-btn" class="btn primary">Retrain using seed data + staff-confirmed documents</button><span id="rt-out" class="muted"></span></div>
  <div class="card"><h2>Audit log (latest 200 events)</h2><div style="max-height:380px;overflow:auto"><table class="t"><tr><th>Time (UTC)</th><th>User</th><th>Action</th><th>Detail</th></tr>
    ${logs.map((l) => `<tr><td class="muted">${esc(l.created_at)}</td><td>${esc(l.username)}</td><td><span class="tag">${esc(l.action)}</span></td><td>${esc(l.detail)}</td></tr>`).join("")}</table></div></div>`;
  const reload = () => viewAdmin().catch((e) => toast(e.message, true));
  const patch = async (url, body) => { try { await api(url, { method: "PATCH", body }); toast("Updated."); reload(); } catch (e) { toast(e.message, true); reload(); } };
  document.querySelectorAll("[data-role]").forEach((s) => (s.onchange = () => patch("/api/admin/users/" + s.dataset.role, { role: s.value })));
  document.querySelectorAll("[data-active]").forEach((c) => (c.onchange = () => patch("/api/admin/users/" + c.dataset.active, { active: c.checked })));
  document.querySelectorAll("[data-pw]").forEach((b) => (b.onclick = () => { const p = prompt("New password (6+ characters):"); if (p) patch("/api/admin/users/" + b.dataset.pw, { password: p }); }));
  document.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => {
    const un = prompt("Username:", b.dataset.un); if (un === null) return;
    const fn = prompt("Full name:", b.dataset.fn); if (fn === null) return;
    patch("/api/admin/users/" + b.dataset.edit, { username: un, full_name: fn });
  }));
  document.querySelectorAll("[data-cat]").forEach((c) => (c.onchange = () => patch("/api/admin/categories/" + c.dataset.cat, { active: c.checked })));
  $("#nu-btn").onclick = async () => { try { await api("/api/admin/users", { method: "POST", body: { username: $("#nu-user").value, full_name: $("#nu-name").value, password: $("#nu-pass").value, role: $("#nu-role").value } }); toast("User created."); reload(); } catch (e) { toast(e.message, true); } };
  $("#nc-btn").onclick = async () => { try { await api("/api/admin/categories", { method: "POST", body: { name: $("#nc-name").value } }); toast("Category added."); reload(); } catch (e) { toast(e.message, true); } };
  $("#rt-btn").onclick = async () => { $("#rt-out").textContent = " Training..."; try { const m = await api("/api/admin/retrain", { method: "POST" }); toast("Model retrained on " + m.samples + " documents."); reload(); } catch (e) { $("#rt-out").textContent = ""; toast(e.message, true); } };
}

/* ---------- start ---------- */
if (TOKEN) startApp();
