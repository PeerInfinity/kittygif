import { drawLevel, legendFor } from "./render.js";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
let py = null, boot = null, current = null;

function say(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = cls;
}

function loadScript(src) {
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = () => rej(new Error("could not load " + src));
    document.head.appendChild(s);
  });
}

// ---------------------------------------------------------------- boot Pyodide
async function start() {
  const cfg = window.KITTYGIF;
  const base = cfg.cdn(cfg.pyodideVersion);
  const build = await (await fetch("build.json")).json();
  $("build-info").textContent =
    `kittygif ${build.kittygif} · wheel ${build.wheel} · Pyodide ${cfg.pyodideVersion} · built ${build.built}`;

  try {
    say("loading Python (Pyodide " + cfg.pyodideVersion + ")…", "busy");
    await loadScript(base + "pyodide.js");
    py = await loadPyodide({ indexURL: base });

    say("installing Pillow…", "busy");
    await py.loadPackage("micropip");
    const micropip = py.pyimport("micropip");
    await micropip.install("Pillow");

    say("installing the kittygif wheel…", "busy");
    await micropip.install(new URL("wheels/" + build.wheel, location.href).href);

    const driver = await (await fetch("driver.py")).text();
    py.runPython(driver, { globals: py.globals });
    boot = JSON.parse(py.runPython("boot_info()"));

    say(`ready — kittygif ${boot.kittygif}, reading container v${boot.readable_versions.join(" and v")}. Drop a level above.`, "ok");
  } catch (err) {
    say("The converter could not start: " + err + "\nSee the repository for the command-line tool.", "bad");
    throw err;
  }
}

// ---------------------------------------------------------------- conversion
async function convertFile(file) {
  if (!py) { say("still loading…", "busy"); return; }
  say(`converting ${file.name} (${file.size.toLocaleString()} bytes)…`, "busy");
  $("result").classList.add("hidden");
  await new Promise(r => setTimeout(r, 0));            // let the status paint

  try {
    const buf = new Uint8Array(await file.arrayBuffer());
    py.FS.writeFile("/tmp/kittygif-in", buf);
    py.globals.set("_fn", file.name);
    const payload = JSON.parse(py.runPython(
      'run("/tmp/kittygif-in", "/tmp/kittygif-out", _fn)'));
    const bytes = py.FS.readFile("/tmp/kittygif-out");
    show(file, payload, bytes);
    say(`converted ${file.name} → ${payload.direction === "gif2kitty" ? ".kitty" : ".gif"}`, "ok");
  } catch (err) {
    const msg = String(err.message || err);
    // Pyodide wraps the Python traceback; the last line is the message that matters.
    const last = msg.trim().split("\n").filter(Boolean).pop();
    say("Could not convert " + file.name + ":\n" + last, "bad");
  }
}

function show(file, payload, bytes) {
  current = { payload, bytes, file };
  const src = payload.source, rep = payload.report;

  $("res-title").textContent =
    `${file.name} → ${payload.tilemap.game}${payload.out_ext}`;

  const stat = [
    ["grid", `${src.grid[0]} × ${src.grid[1]}`],
    ["cells", rep.cells.total.toLocaleString()],
    ["read as", src.space === "gif" ? "level gif" : `.kitty container v${src.file_version}`],
    ["level name", src.name || "(none)"],
  ];
  if (src.robot) stat.push(["robot", `${src.robot[0]} , ${src.robot[1]}`]);
  $("res-stat").innerHTML = stat
    .map(([k, v]) => `<div>${k} <b>${escapeHtml(String(v))}</b></div>`).join("");

  const geom = drawLevel($("canvas"), payload.tilemap, payload.config);
  $("legend").innerHTML = legendFor(payload.tilemap, payload.config)
    .map(([name, cat]) => cat.color
      ? `<span><i style="background:${cat.color}"></i>${escapeHtml(name)}</span>`
      : `<span><i style="border-color:#8a8fae;background:none"></i>${escapeHtml(name)} (no derived colour)</span>`)
    .join("");
  $("legend-note").textContent =
    `the level the conversion PRODUCED, ${geom.width}×${geom.height} at ${geom.scale} px per tile; ` +
    `colours are the table's own — each category takes the colour of the gif id it is paired with.`;

  // ---- report
  $("risk").innerHTML = rep.solvability_at_risk
    ? `<div class="risk"><b>Solvability warning.</b> Something in this level has no
       equivalent in the target format and was substituted. The level still converts and
       still loads — but a route that needed the substituted tile may no longer exist.</div>`
    : "";
  const rows = rep.entries.filter(e => e.count);
  $("report-table").innerHTML =
    `<tr><th class="num">cells</th><th>class</th><th>from</th><th>to</th><th>note</th></tr>` +
    `<tr><td class="num"><b>${rep.cells.by_class.a}</b></td><td class="cls-a">mappable</td>
        <td colspan="3" class="note">carried across exactly</td></tr>` +
    rows.filter(e => e.class !== "a").map(e => `
      <tr><td class="num">${e.count}</td>
          <td class="cls-${e.class}">${escapeHtml(e.class_label)}</td>
          <td>${e.source_id} ${escapeHtml(e.source_name)}</td>
          <td>${e.target_id === null ? "—" : e.target_id} ${escapeHtml(e.target_name)}</td>
          <td class="note">${escapeHtml(e.note || "")}</td></tr>`).join("") +
    (rows.some(e => e.class !== "a") ? "" :
      `<tr><td class="num">0</td><td colspan="4" class="note">nothing degraded, nothing substituted</td></tr>`);

  // ---- download
  buildDownload(payload);
  $("result").classList.remove("hidden");
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildDownload(payload) {
  const picker = $("slot-picker");
  const stem = (payload.tilemap.game || "level").replace(/[^A-Za-z0-9 _-]/g, "") || "level";

  if (payload.out_ext !== ".gif") {
    picker.innerHTML = `<p class="note">A <code>.kitty</code> is loaded by name from the web
      editor's own storage, so any filename works.</p>`;
    setName(stem.toLowerCase() + ".kitty");
    return;
  }

  const slots = boot.slots.map((f, i) => `
    <label><input type="radio" name="slot" value="${f}" ${i === 0 ? "checked" : ""}>${f}
      <span class="dim">replaces that level</span></label>`).join("");
  picker.innerHTML = `
    <p>The compilation loads a custom level <b>only</b> as an overwrite of one of its own
      level files, under <b>exactly</b> that filename. Pick the slot this level should take:</p>
    <div class="slots">${slots}
      <label><input type="radio" name="slot" value="">free filename
        <span class="dim">⚠ will not be loaded by the game</span></label>
    </div>
    <div class="risk">Back the original file up first. Verifying the game's files through your
      store restores it if you lose it.</div>`;
  const update = () => {
    const chosen = picker.querySelector('input[name="slot"]:checked').value;
    setName(chosen || (stem.toLowerCase() + ".gif"));
  };
  picker.addEventListener("change", update);
  update();
}

let downloadName = "level";
function setName(name) {
  downloadName = name;
  $("download-name").textContent = "→ " + name;
}

$("download").addEventListener("click", () => {
  if (!current) return;
  const blob = new Blob([current.bytes], { type: "application/octet-stream" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = downloadName;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------- drop target
const drop = $("drop"), input = $("file");
drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") input.click(); });
input.addEventListener("change", () => { if (input.files[0]) convertFile(input.files[0]); });
for (const ev of ["dragenter", "dragover"]) {
  drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("hot"); });
}
for (const ev of ["dragleave", "drop"]) {
  drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("hot"); });
}
drop.addEventListener("drop", e => {
  const f = e.dataTransfer.files[0];
  if (f) convertFile(f);
});

// ---------------------------------------------------------------- the gallery
async function gallery() {
  const data = await (await fetch("samples/samples.json")).json();
  $("gallery").innerHTML = data.samples.map(s => `
    <figure>
      <img src="samples/${s.name}/${s.name}.preview.png" alt="${escapeHtml(s.name)}" loading="lazy">
      <figcaption>
        <b>${escapeHtml(s.name)}</b> — ${escapeHtml(s.blurb)}
        <div class="meta">${s.grid[0]}×${s.grid[1]} · ${s.distinct_ids} distinct ids ·
          authored as <code>.${s.authored_in === "gif" ? "gif" : "kitty"}</code> ·
          engine win at tick ${s.ticks_to_win ?? s.ticks}</div>
        <div class="dl">
          <a href="samples/${s.name}/${s.name}.gif" download>.gif</a>
          <a href="samples/${s.name}/${s.name}.kitty" download>.kitty</a>
          <a href="samples/${s.name}/${s.name}.report.json">report</a>
        </div>
      </figcaption>
    </figure>`).join("");
}

gallery().catch(e => console.error(e));
start().catch(e => console.error(e));
