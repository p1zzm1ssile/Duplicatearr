"use strict";

// ---------- Helpers ----------

const view = document.getElementById("view");
const APP = document.title;
const REPO = `https://github.com/p1zzm1ssile/${APP}`;
const EMAIL = "p1zzm1ssilerepo@gmail.com";

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", [`X-${APP}`]: "1", ...(options.headers || {}) },
  });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Please log in");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    error.data = data;
    throw error;
  }
  return data;
}

const post = (path, body = {}) => api(path, { method: "POST", body: JSON.stringify(body) });

// Builds elements. Text always goes in as text, never as HTML.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.style.cssText = value; // CSP allows styles set from script, not style attributes
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function ago(timestamp) {
  const seconds = Math.round(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400 * 2) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function splitPath(path) {
  const i = path.lastIndexOf("/");
  return [path.slice(0, i), path.slice(i + 1)];
}

const when = (timestamp) => new Date(timestamp * 1000).toLocaleString();


let refreshTimer = null;
function every(ms, fn) {
  clearInterval(refreshTimer);
  refreshTimer = setInterval(fn, ms);
}

function flash(node, ok, message) {
  node.className = `result ${ok ? "ok" : "bad"}`;
  node.textContent = (ok ? "✓ " : "✗ ") + message;
}

// ---------- Header ----------

async function refreshHealth() {
  const pill = document.getElementById("health");
  const text = document.getElementById("health-text");
  try {
    const h = await api("/api/status");
    pill.className = "pill " + (h.healthy ? "ok" : "bad");
    text.textContent = h.healthy ? "Healthy" : "Needs attention";
    pill.title = [...h.problems, `Version ${h.version}`].join("\n");
    return h;
  } catch {
    pill.className = "pill bad";
    text.textContent = "Not responding";
    return null;
  }
}

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout").catch(() => {});
  window.location.href = "/login";
});

api("/api/session").then((s) => {
  document.getElementById("whoami").textContent = s.user || "";
  if (s.user === "(local network)") document.getElementById("logout").textContent = "Log in";
});

// ---------- Dashboard ----------

const KINDS = { all: "Everything", movie: "Films", episode: "Episodes", extra: "Extras", image: "Pictures" };
const VERDICT_STYLE = {
  same: ["ok", "Same video"], likely: ["info", "Very likely the same"], unsure: ["warn", "Check by hand"],
  different: ["bad", "Frames differ"], editions: ["warn", "Different editions"], lengths: ["warn", "Different lengths"],
};
let dashKind = "all";
let showIgnored = false;
// Drawing every group at once can freeze the browser (a big library has tens of thousands of matching pictures),
// so the dashboard draws them a page at a time
const PAGE = 50;
let dashLimit = PAGE;

function bytes(n) {
  if (!n) return "0 GB";
  const units = ["bytes", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return i === 0 ? `${n} bytes` : `${n.toFixed(1)} ${units[i]}`;
}

function runtime(seconds) {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

function quality(f) {
  if (f.error) return f.error;
  const parts = [];
  if (f.height) parts.push(f.height >= 2000 ? "2160p" : f.height >= 1000 ? "1080p" : f.height >= 700 ? "720p" : `${f.height}p`);
  else if (f.width) parts.push(`${f.width}×${f.height}`);
  if (f.hdr) parts.push(f.hdr);
  if (f.codec) parts.push(f.codec.toUpperCase());
  if (f.audio) parts.push(`${f.audio_profile || f.audio.toUpperCase()}${f.channels ? " " + ({ 2: "2.0", 6: "5.1", 8: "7.1" }[f.channels] || `${f.channels}ch`) : ""}`);
  if (f.duration) parts.push(runtime(f.duration));
  return parts.join(" · ");
}

function groupCard(g, reload) {
  const result = el("span", { class: "result", role: "status" });
  const boxes = {};
  const [style, label] = g.kind === "image" ? ["ok", "Same picture"] : g.kind === "extra" ? ["ok", "Identical files"]
    : VERDICT_STYLE[g.verdict] || ["info", g.verdict];
  const rows = g.files.map((f) => {
    const [folder, name] = splitPath(f.path);
    boxes[f.path] = el("input", { type: "checkbox", checked: f.suggest === "remove", "aria-label": `Remove ${name}` });
    return el("tr", {},
      el("td", {}, boxes[f.path]),
      el("td", { class: "name" },
        el("div", { text: name }),
        el("div", { class: "path", text: folder }),
        el("div", { class: "row-wrap" },
          f.suggest === "keep" ? el("span", { class: "badge ok", text: "Suggested to keep" }) : null,
          f.tracked ? el("span", { class: "badge info", text: `Tracked by ${f.tracked}` }) : null,
          f.links > 1 ? el("span", { class: "badge warn", text: "Hardlinked: frees no space until the torrent is gone" }) : null,
          f.edition ? el("span", { class: "badge", text: f.edition }) : null)),
      el("td", { class: "small", text: g.kind === "image" ? `${f.width}×${f.height}` : quality(f) }),
      el("td", { class: "small nowrap", text: bytes(f.size) }));
  });

  const remove = el("button", { type: "button", class: "danger", text: "Move ticked to recycle folder" });
  remove.addEventListener("click", async () => {
    const paths = Object.entries(boxes).filter(([, b]) => b.checked).map(([p]) => p);
    if (!paths.length) { flash(result, false, "Tick the copies to remove first"); return; }
    if (paths.length === g.files.length) { flash(result, false, "Leave at least one copy unticked"); return; }
    if (!confirm(`Move ${paths.length} cop${paths.length === 1 ? "y" : "ies"} of "${g.title}" to the recycle folder? You can restore from History.`)) return;
    remove.disabled = true;
    try { flash(result, true, (await post("/api/recycle", { group: g.id, paths })).message); setTimeout(reload, 1200); }
    catch (e) { flash(result, false, e.message); remove.disabled = false; }
  });
  const ignore = el("button", { type: "button", text: g.ignored ? "Show again" : "Not duplicates" });
  ignore.addEventListener("click", async () => { await post("/api/ignore", { group: g.id, ignored: !g.ignored }); reload(); });

  return el("div", { class: "panel" },
    el("div", { class: "row-wrap" },
      el("span", { class: "badge", text: KINDS[g.kind] }),
      el("span", { class: `badge ${style}`, text: label }),
      g.reclaimable ? el("span", { class: "badge", text: `Frees ${bytes(g.reclaimable)}` }) : null),
    el("h2", { text: g.title }),
    el("p", { class: "muted small", text: g.verdict_text }),
    g.note ? el("div", { class: "notice warn small", text: g.note }) : null,
    el("table", {}, el("tbody", {}, rows)),
    el("div", { class: "card-actions" }, remove, ignore, result));
}

function progressText(p) {
  const n = (x) => x.toLocaleString();
  const took = p.started ? ` · started ${ago(p.started)}` : "";
  return (p.total ? `${n(p.done)} of ${n(p.total)} ${p.unit}` : `${n(p.done)} ${p.unit}`) + took;
}

async function showDashboard() {
  const d = await api("/api/results");
  const p = d.progress;
  const reload = () => showDashboard();
  const groups = d.groups.filter((g) => g.ignored === showIgnored);
  const visible = groups.filter((g) => dashKind === "all" || g.kind === dashKind);
  const ignoredCount = d.groups.filter((g) => g.ignored).length;
  const active = d.groups.filter((g) => !g.ignored);

  const scan = el("button", { type: "button", class: "primary", text: p.running ? "Scanning…" : "Scan now", disabled: p.running });
  scan.addEventListener("click", async () => {
    try { await post("/api/scan"); reload(); } catch (e) { alert(e.message); }
  });
  const stop = p.running ? el("button", { type: "button", text: "Stop", onclick: async () => { await post("/api/stop"); } }) : null;

  view.replaceChildren(...[
    el("div", { class: "toolbar" },
      el("h1", { text: "Dashboard" }),
      el("span", { class: "spacer" }),
      el("span", { class: "muted small", text: d.scanned_at ? `Last scan ${ago(d.scanned_at)}, ${d.files} videos` : "Not scanned yet" }),
      stop, scan),
    p.running ? el("div", { class: "panel" },
      el("strong", { text: p.phase + "…" }),
      p.total ? el("div", { class: "progress" }, el("span", { style: `width:${Math.round((100 * p.done) / p.total)}%` })) : null,
      el("div", { class: "muted small", id: "progress-text", text: progressText(p) })) : null,
    !d.libraries.length ? el("div", { class: "notice warn" }, "No library folders are set up. Add them in ",
      el("a", { href: "#/settings/general", text: "Settings" }), ".") : null,
    (d.missing_libraries || []).length ? el("div", { class: "notice bad", text: `These folders weren't found, so weren't scanned: ${d.missing_libraries.join(", ")}. Check the paths in Settings and the container's folder mappings.` }) : null,
    el("div", { class: "tiles" },
      ["movie", "episode", "extra", "image"].map((k) => el("div", { class: "tile" },
        el("span", { class: "num", text: String(active.filter((g) => g.kind === k).length) }),
        el("span", { class: "label", text: KINDS[k] }))),
      el("div", { class: "tile warn" }, el("span", { class: "num", text: bytes(active.reduce((s, g) => s + g.reclaimable, 0)) }),
        el("span", { class: "label", text: "Could be freed" })),
      el("div", { class: "tile ok" }, el("span", { class: "num", text: bytes(d.reclaimed) }),
        el("span", { class: "label", text: "Freed so far" }))),
    el("div", { class: "toolbar" },
      el("div", { class: "segmented", role: "group", "aria-label": "Show" },
        Object.entries(KINDS).map(([key, label]) => el("button", {
          type: "button", class: key === dashKind ? "active" : "",
          text: `${label} (${groups.filter((g) => key === "all" || g.kind === key).length})`,
          onclick: () => { dashKind = key; dashLimit = PAGE; reload(); },
        }))),
      ignoredCount ? el("label", { class: "chip" },
        el("input", { type: "checkbox", checked: showIgnored, onchange: (e) => { showIgnored = e.target.checked; dashLimit = PAGE; reload(); } }),
        `Show "not duplicates" (${ignoredCount})`) : null),
    el("p", { class: "muted small", text: "Copies Duplicatearr is sure about are ticked, keeping the best one (or the one Radarr or Sonarr tracks). Change the ticks as you like: nothing moves until you press the button, and moved copies can be restored from History." }),
    visible.length ? visible.slice(0, dashLimit).map((g) => groupCard(g, reload))
      : el("div", { class: "panel empty", text: !d.scanned_at ? "Press Scan now to look for duplicates." : "No duplicates here." }),
    visible.length > dashLimit ? el("div", { class: "panel empty" },
      el("p", { class: "muted small", text: `Showing ${dashLimit.toLocaleString()} of ${visible.length.toLocaleString()}` }),
      el("button", { type: "button", text: `Show ${Math.min(PAGE, visible.length - dashLimit)} more`,
        onclick: () => { dashLimit += PAGE; reload(); } })) : null,
    el("div", { class: "panel" },
      el("h2", { text: "Coming next" }),
      el("ul", {}, ["Your own rules, such as always keeping the 4K copy, applied by themselves once you trust them.",
        "Telling Jellyfin and Plex straight away when a copy is removed.", "Duplicate music and books."].map((t) => el("li", { text: t })))),
  ].flat().filter(Boolean));
  if (p.running) every(2000, async () => {
    const r = await api("/api/results");
    if (!r.progress.running) reload();
    else {
      // A new step has started: draw the page again for its heading and bar
      if (r.progress.phase !== p.phase || !!r.progress.total !== !!p.total) { reload(); return; }
      const bar = view.querySelector(".progress > span");
      if (bar && r.progress.total) bar.style.width = `${Math.round((100 * r.progress.done) / r.progress.total)}%`;
      const text = document.getElementById("progress-text");
      if (text) text.textContent = progressText(r.progress);
    }
  });
}

// ---------- History ----------

const STATE_TEXT = { recycled: "In the recycle folder", restored: "Restored", purged: "Emptied", deleted: "Deleted" };

async function showHistory() {
  const d = await api("/api/history");
  view.replaceChildren(...[
    el("h1", { text: "History" }),
    el("p", { class: "muted", text: d.recycle_days ? `Removed copies stay in the recycle folder for ${d.recycle_days} days, and can be restored until then.` : "The recycle folder is turned off (0 days), so removed copies are deleted straight away." }),
    d.entries.length ? el("div", { class: "panel" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "When" }), el("th", { text: "File" }), el("th", { text: "Size" }), el("th", { text: "" }))),
      el("tbody", {}, d.entries.map((e) => {
        const [folder, name] = splitPath(e.original);
        const action = e.state === "recycled" ? el("button", { type: "button", text: "Restore", onclick: async (ev) => {
          ev.target.disabled = true;
          try { alert((await post("/api/restore", { id: e.id })).message); showHistory(); }
          catch (err) { alert(err.message); ev.target.disabled = false; }
        } }) : el("span", { class: "muted small", text: STATE_TEXT[e.state] || e.state });
        return el("tr", {},
          el("td", { class: "small nowrap", text: when(e.at) }),
          el("td", { class: "name" }, el("div", { text: name }), el("div", { class: "path", text: folder }),
            el("div", { class: "muted small", text: e.group_title })),
          el("td", { class: "small nowrap", text: bytes(e.size) }),
          el("td", {}, action));
      })))) : el("div", { class: "panel empty", text: "Nothing has been removed yet." }),
  ]);
}

// ---------- Logs ----------

async function showLogs() {
  let kind = "all";
  const box = el("div", { class: "log", role: "log", "aria-live": "polite" });
  const search = el("input", { type: "search", placeholder: "Search logs", "aria-label": "Search logs" });
  const auto = el("input", { type: "checkbox", checked: true });
  const buttons = {};
  const segmented = el("div", { class: "segmented", role: "group", "aria-label": "Show" },
    ["all", "issues", "actions"].map((k) => (buttons[k] = el("button", {
      type: "button", class: k === kind ? "active" : "",
      text: { all: "All", issues: "Issues", actions: "Actions" }[k],
      onclick: () => { kind = k; Object.values(buttons).forEach((b) => b.classList.remove("active")); buttons[k].classList.add("active"); load(true); },
    }))));

  view.replaceChildren(
    el("h1", { text: "Logs" }),
    el("p", { class: "muted small", text: `Issues shows errors and warnings. Actions shows every change ${APP} made.` }),
    el("div", { class: "toolbar" }, segmented,
      el("div", { style: "flex:1;min-width:180px" }, search),
      el("label", { class: "chip" }, auto, "Auto refresh"),
      el("a", { class: "button", href: "/api/logs/download", text: "Download all logs" })),
    box);

  let lines = [];
  function render(scroll) {
    const term = search.value.trim().toLowerCase();
    const filtered = lines.filter((l) => !term || l.message.toLowerCase().includes(term));
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.replaceChildren(...(filtered.length ? filtered.map((l) => el("div", { class: "line" },
      el("span", { class: "time", text: l.time }), el("span", { class: `lvl lvl-${l.level}`, text: l.level }), l.message))
      : [el("div", { class: "empty", text: kind === "issues" ? "No issues. All good!" : "Nothing to show yet." })]));
    if (scroll || atBottom) box.scrollTop = box.scrollHeight;
  }

  async function load(scroll) {
    try {
      lines = (await api(`/api/logs?filter=${kind}`)).lines;
      render(scroll);
    } catch (e) {
      box.replaceChildren(el("div", { class: "error-text", text: e.message }));
    }
  }

  search.addEventListener("input", () => render(false));
  await load(true);
  every(5000, () => { if (auto.checked) load(false); });
}

// ---------- Settings ----------

let settings = null;

function fieldInput(field, value, onChange) {
  const id = `f-${field.key}`;
  const help = field.help ? el("div", { class: "help", text: field.help }) : null;
  const error = el("div", { class: "error-text", id: `${id}-error` });

  if (field.type === "bool") {
    const input = el("input", { type: "checkbox", id, checked: !!value, onchange: onChange });
    return { node: el("label", { class: "switch", for: id }, input, el("span", { class: "track" }),
      el("span", { class: "text" }, field.label, help, error)), get: () => input.checked, input };
  }

  let input;
  if (field.type === "select") {
    input = el("select", { id, onchange: onChange }, field.options.map((o) => el("option", { value: o, text: o, selected: o === value })));
  } else if (field.type === "secret") {
    input = el("input", { type: "password", id, autocomplete: "new-password", oninput: onChange,
      placeholder: value && value.set ? "•••••••• saved (type to replace)" : "Not set" });
  } else {
    input = el("input", { type: field.type === "int" ? "number" : "text", id, value: value ?? "", oninput: onChange,
      min: field.min, max: field.max, placeholder: field.placeholder, spellcheck: "false" });
  }
  return {
    node: el("label", { class: "field", for: id }, el("span", { class: "label", text: field.label }), input, help, error),
    get: () => field.type === "secret" ? (input.value === "" ? null : input.value) : input.value,
    input,
  };
}

async function showSettings(tab, savedMessage) {
  if (!settings) settings = await api("/api/settings");
  if (!settings.tabs[tab]) tab = "general";

  const fields = settings.fields.filter((f) => f.tab === tab);
  const getters = {};
  const status = el("span", { class: "muted small", role: "status" });
  let dirty = false;
  const markDirty = () => { dirty = true; status.textContent = "Unsaved changes"; status.style.color = "var(--warn)"; };

  const formValues = () => Object.fromEntries(Object.entries(getters).map(([k, g]) => [k, g()]));

  function testButton(target) {
    const result = el("span", { class: "result" });
    const button = el("button", { type: "button", text: "Test connection" });
    button.addEventListener("click", async () => {
      button.disabled = true;
      result.className = "result muted";
      result.textContent = "Testing…";
      try {
        const r = await post("/api/test", { target, values: formValues() });
        flash(result, r.ok, r.message);
      } catch (e) {
        flash(result, false, e.message);
      } finally {
        button.disabled = false;
      }
    });
    return el("div", { class: "card-actions" }, button, result);
  }

  const sections = [];
  for (const field of fields) {
    let section = sections.find((s) => s.title === field.section);
    if (!section) sections.push(section = { title: field.section, fields: [] });
    section.fields.push(field);
  }

  const content = sections.map((section) => {
    const rendered = section.fields.map((f) => {
      const input = fieldInput(f, settings.values[f.key], markDirty);
      getters[f.key] = input.get;
      return input;
    });
    return el("div", { class: "panel" },
      el("h2", { text: section.title }),
      el("div", { class: "grid-2" }, rendered.map((r) => r.node)),
      tab !== "general" && section.title === "Connection" ? testButton(tab) : null);
  });

  if (tab !== "general") content.unshift(el("p", { class: "muted", text: `Optional. ${APP} only reads from ${settings.tabs[tab]} until you choose to change something.` }));
  if (tab === "general") content.push(...accountPanels());

  const saveButton = el("button", { class: "primary", type: "button", text: `Save ${settings.tabs[tab]}` });
  saveButton.addEventListener("click", async () => {
    saveButton.disabled = true;
    view.querySelectorAll(".error-text[id$='-error']").forEach((e) => (e.textContent = ""));
    try {
      const r = await api("/api/settings", { method: "PUT", body: JSON.stringify({ values: formValues() }) });
      settings.values = r.values;
      dirty = false;
      status.style.color = "var(--ok)";
      status.textContent = "✓ Saved. Changes are in effect now.";
      refreshHealth();
    } catch (e) {
      status.style.color = "var(--bad)";
      const errors = (e.data && e.data.errors) || {};
      for (const [key, message] of Object.entries(errors)) {
        const box = document.getElementById(`f-${key}-error`);
        if (box) box.textContent = message;
      }
      status.textContent = Object.keys(errors).length ? "Please fix the highlighted settings." : e.message;
    } finally {
      saveButton.disabled = false;
    }
  });

  view.replaceChildren(
    el("h1", { text: "Settings" }),
    el("div", { class: "tabs", role: "tablist" }, Object.entries(settings.tabs).map(([key, label]) =>
      el("button", { type: "button", role: "tab", class: key === tab ? "active" : "", "aria-selected": String(key === tab), text: label,
        onclick: () => {
          if (dirty && !confirm("You have unsaved changes on this tab. Leave without saving?")) return;
          location.hash = `#/settings/${key}`;
        } }))),
    ...content,
    el("div", { class: "savebar" }, saveButton, status));

  if (savedMessage) {
    status.style.color = "var(--ok)";
    status.textContent = savedMessage;
  }
  window.onbeforeunload = () => (dirty ? true : undefined);
}

function accountPanels() {
  const current = el("input", { type: "password", autocomplete: "current-password" });
  const user = el("input", { type: "text", value: settings.username, autocomplete: "username" });
  const password = el("input", { type: "password", autocomplete: "new-password" });
  const confirmBox = el("input", { type: "password", autocomplete: "new-password" });
  const rules = el("ul", { class: "rules" });
  const result = el("div", { class: "result", role: "status" });
  const RULES = [
    ["At least 8 characters", (p) => p.length >= 8],
    ["An uppercase letter", (p) => /[A-Z]/.test(p)],
    ["A lowercase letter", (p) => /[a-z]/.test(p)],
    ["A number", (p) => /[0-9]/.test(p)],
    ["A special character, like ! ? # or @", (p) => /[^A-Za-z0-9]/.test(p)],
  ];
  const renderRules = () => rules.replaceChildren(...RULES.map(([t, c]) => el("li", { class: c(password.value) ? "met" : "", text: t })));
  password.addEventListener("input", renderRules);
  renderRules();

  const change = el("button", { type: "button", text: "Change password" });
  change.addEventListener("click", async () => {
    result.className = "result bad";
    const missing = RULES.filter(([, c]) => !c(password.value));
    if (missing.length) { result.textContent = "The new password still needs: " + missing.map(([t]) => t.toLowerCase()).join(", "); return; }
    if (password.value !== confirmBox.value) { result.textContent = "The new passwords don't match"; return; }
    change.disabled = true;
    try {
      await post("/api/password", { current: current.value, username: user.value.trim(), password: password.value });
      result.className = "result ok";
      result.textContent = "✓ Password changed. Other devices have been logged out.";
      settings.username = user.value.trim();
      current.value = password.value = confirmBox.value = "";
      renderRules();
    } catch (e) {
      result.textContent = e.message;
    } finally {
      change.disabled = false;
    }
  });

  return [
    el("div", { class: "panel" },
      el("h2", { text: "Account" }),
      el("div", { class: "notice warn small" },
        el("strong", { text: `Keep ${APP} on your home network. ` }),
        "We don't recommend putting it behind a reverse proxy (Nginx Proxy Manager, SWAG, Traefik, Cloudflare Tunnel and the like) for access from outside. Use a VPN such as WireGuard or Tailscale instead. The local network login bypass above never applies to requests that come through a proxy."),
      el("div", { class: "grid-2" },
        el("label", { class: "field" }, el("span", { class: "label", text: "Username" }), user),
        el("label", { class: "field" }, el("span", { class: "label", text: "Current password" }), current),
        el("label", { class: "field" }, el("span", { class: "label", text: "New password" }), password, rules),
        el("label", { class: "field" }, el("span", { class: "label", text: "Confirm new password" }), confirmBox)),
      el("div", { class: "card-actions" }, change, result)),
    el("div", { class: "panel" },
      el("h2", { text: "Log files" }),
      el("p", { class: "muted small", text: `Everything ${APP} has logged, including older rotated files, as one zip. Handy for reporting a problem.` }),
      el("a", { class: "button", href: "/api/logs/download", text: "Download all logs" })),
  ];
}

// ---------- Contact ----------

function showContact() {
  view.replaceChildren(
    el("h1", { text: "Contact" }),
    el("div", { class: "panel" },
      el("h2", { text: "Report a problem or suggest an idea" }),
      el("p", { class: "muted", text: "Bugs and ideas go on GitHub, where you can follow the fix and others with the same problem can find it. Saying which versions of Unraid and your apps you run, and what you expected to happen, helps a lot. Logs are under Settings > General > Log files." }),
      el("div", { class: "row-wrap" },
        el("a", { class: "button primary", href: `${REPO}/issues/new?title=%5B${APP}%5D%20`, target: "_blank", rel: "noopener", text: "Report an issue" }),
        el("a", { class: "button", href: `${REPO}/issues`, target: "_blank", rel: "noopener", text: "See open issues" }))),
    el("div", { class: "panel" },
      el("h2", { text: "Contact me" }),
      el("p", { class: "muted" }, "For anything that doesn't belong on a public page, email ",
        el("a", { href: `mailto:${EMAIL}?subject=${APP}`, text: EMAIL }), ".")));
}

// ---------- Router ----------

async function route() {
  window.onbeforeunload = null;
  clearInterval(refreshTimer);
  const [, page = "", sub = ""] = (location.hash || "#/").split("/");
  const name = page || "dashboard";
  document.querySelectorAll("nav.main a").forEach((a) => a.classList.toggle("active", a.dataset.page === name));
  try {
    if (name === "history") await showHistory();
    else if (name === "logs") await showLogs();
    else if (name === "settings") await showSettings(sub || "general");
    else if (name === "contact") showContact();
    else await showDashboard();
  } catch (e) {
    view.replaceChildren(el("div", { class: "notice bad", text: e.message }));
  }
}

window.addEventListener("hashchange", route);
route();
refreshHealth();
setInterval(refreshHealth, 15000);
