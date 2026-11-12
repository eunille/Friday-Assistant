// Friday desktop shell: starts the engine, shows the widget and the full view,
// keeps a tray icon. The page never gets Node access; see preload.cjs.
const { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, screen, shell } = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const DEV = process.argv.includes("--dev");
const SMOKE = process.argv.includes("--smoke"); // build check: screenshot each window, then quit
const REPO = path.resolve(__dirname, "..", "..");
const WIDGET = { width: 340, height: 64 };

let engine = null; // { process, port, token }
let widget = null;
let full = null;
let tray = null;
let quitting = false;

// ---------------------------------------------------------------- engine

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function enginePython() {
  if (process.env.FRIDAY_PYTHON) return process.env.FRIDAY_PYTHON;
  const exe = process.platform === "win32" ? path.join("Scripts", "python.exe") : path.join("bin", "python");
  return path.join(REPO, ".venv", exe);
}

async function startEngine() {
  const port = await freePort();
  const token = crypto.randomBytes(24).toString("base64url");
  const args = ["-m", "friday", "serve", "--port", String(port)];
  if (SMOKE || process.env.FRIDAY_NO_VOICE) args.push("--no-voice");

  const child = spawn(enginePython(), args, {
    cwd: path.join(REPO, "engine"),
    env: { ...process.env, FRIDAY_TOKEN: token, PYTHONIOENCODING: "utf-8" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  const logFile = fs.createWriteStream(path.join(app.getPath("userData"), "engine.log"), { flags: "a" });
  child.stdout.pipe(logFile);
  child.stderr.pipe(logFile);
  child.on("exit", (code) => {
    if (!quitting) console.error(`Friday engine exited (code ${code})`);
    if (engine && engine.process === child) engine.process = null;
  });
  engine = { process: child, port, token };
}

function stopEngine() {
  if (engine && engine.process) {
    engine.process.kill();
    engine.process = null;
  }
}

// --------------------------------------------------------------- windows

function pageUrl(view, demo) {
  const hash = `#/${view}${demo ? `?demo=${demo}` : ""}`;
  if (DEV) return `http://localhost:5173/${hash}`;
  return `file://${path.join(__dirname, "..", "dist", "index.html").replace(/\\/g, "/")}${hash}`;
}

const webPreferences = {
  preload: path.join(__dirname, "preload.cjs"),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
};

function statePath() {
  return path.join(app.getPath("userData"), "window-state.json");
}

function loadWidgetPosition() {
  try {
    const saved = JSON.parse(fs.readFileSync(statePath(), "utf8"));
    const visible = screen.getAllDisplays().some(({ workArea: a }) =>
      saved.x >= a.x && saved.x < a.x + a.width && saved.y >= a.y && saved.y < a.y + a.height);
    if (visible) return { x: saved.x, y: saved.y };
  } catch {}
  const { workArea } = screen.getPrimaryDisplay();
  return { x: workArea.x + workArea.width - WIDGET.width - 24, y: workArea.y + workArea.height - WIDGET.height - 24 };
}

function saveWidgetPosition() {
  if (!widget || widget.isDestroyed()) return;
  const [x, y] = widget.getPosition();
  try {
    fs.writeFileSync(statePath(), JSON.stringify({ x, y }));
  } catch {}
}

function lockDown(win) {
  // The app's own windows never navigate away; links open in the real browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://") && !url.startsWith("http://localhost:5173")) event.preventDefault();
  });
}

function createWidget(demo) {
  widget = new BrowserWindow({
    ...WIDGET,
    ...loadWidgetPosition(),
    frame: false,
    transparent: true,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    show: false,
    webPreferences,
  });
  widget.setAlwaysOnTop(true, "screen-saver");
  lockDown(widget);
  widget.loadURL(pageUrl("widget", demo));
  widget.once("ready-to-show", () => widget.show());
  widget.on("moved", saveWidgetPosition);
  widget.on("closed", () => (widget = null));
}

function createFull(demo) {
  full = new BrowserWindow({
    width: 1120,
    height: 720,
    minWidth: 720,
    minHeight: 520,
    show: false,
    backgroundColor: "#16171a",
    autoHideMenuBar: true,
    title: "Friday",
    webPreferences,
  });
  lockDown(full);
  full.loadURL(pageUrl("main", demo));
  full.on("close", (event) => {
    if (quitting) return;
    event.preventDefault(); // closing the full view goes back to the widget
    collapse();
  });
  full.on("closed", () => (full = null));
}

function expand() {
  if (!full) createFull();
  full.show();
  full.focus();
  if (widget) widget.hide();
}

function collapse() {
  if (full) full.hide();
  if (!widget) createWidget();
  else widget.show();
}

// ------------------------------------------------------------------ tray

function trayIcon() {
  // A 32px blue dot, drawn here so the app needs no image file.
  const size = 32;
  const pixels = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const d = Math.hypot(x - 15.5, y - 15.5);
      const alpha = Math.max(0, Math.min(1, 13 - d));
      const i = (y * size + x) * 4;
      pixels[i] = 246; // B
      pixels[i + 1] = 140; // G
      pixels[i + 2] = 59; // R
      pixels[i + 3] = Math.round(alpha * 255);
    }
  }
  return nativeImage.createFromBitmap(pixels, { width: size, height: size });
}

function createTray() {
  tray = new Tray(trayIcon());
  tray.setToolTip("Friday");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Friday", click: expand },
    { label: "Show widget", click: collapse },
    { type: "separator" },
    { label: "Quit Friday", click: () => app.quit() },
  ]));
  tray.on("click", () => (full && full.isVisible() ? collapse() : expand()));
}

// ------------------------------------------------------------------- ipc

ipcMain.handle("engine:info", () => (engine ? { port: engine.port, token: engine.token } : null));
ipcMain.on("window:expand", expand);
ipcMain.on("window:collapse", collapse);
ipcMain.on("app:quit", () => app.quit());
ipcMain.on("widget:resize", (_event, height) => {
  if (!widget) return;
  const target = Math.max(WIDGET.height, Math.min(420, Math.round(Number(height) || WIDGET.height)));
  const [x, y] = widget.getPosition();
  const [, current] = widget.getSize();
  // Grow upwards so the pill stays where the user put it.
  widget.setBounds({ x, y: y + current - target, width: WIDGET.width, height: target });
});

// ------------------------------------------------------------- smoke run

async function smoke() {
  const out = process.env.FRIDAY_SMOKE_DIR || app.getPath("temp");
  const shots = [
    ["widget", "speaking", WIDGET.width, WIDGET.height],
    ["widget", "approval", WIDGET.width, 240],
    ["main", "speaking", 1120, 720],
    ["main", "approval", 1120, 720],
    ["main", "history", 1120, 720],
  ];
  for (const [view, demo, width, height] of shots) {
    const win = new BrowserWindow({ width, height, show: false, frame: false, useContentSize: true,
      transparent: view === "widget", backgroundColor: view === "widget" ? "#00000000" : "#16171a", webPreferences });
    await win.loadURL(pageUrl(view, demo));
    await new Promise((r) => setTimeout(r, 1200));
    const image = await win.webContents.capturePage();
    fs.writeFileSync(path.join(out, `friday-${view}-${demo}.png`), image.toPNG());
    win.destroy();
  }
  console.log(`smoke: wrote ${shots.length} screenshots to ${out}`);
}

// ------------------------------------------------------------------- app

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", expand);

  app.whenReady().then(async () => {
    if (SMOKE) {
      await smoke();
      app.exit(0);
      return;
    }
    await startEngine();
    createTray();
    createWidget();
  });

  app.on("window-all-closed", () => {}); // Friday lives in the tray until Quit
  app.on("before-quit", () => {
    quitting = true;
    saveWidgetPosition();
    stopEngine();
  });
}
