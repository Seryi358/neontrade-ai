/**
 * NeonTrade AI - Electron Main Process
 * Self-contained desktop app: auto-starts Python backend on launch.
 */

const { app, BrowserWindow, Menu, shell, dialog, protocol, Notification } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const net = require('net');
const url = require('url');
const http = require('http');

let mainWindow;
let splashWindow;
let backendProcess;
let backendRestartCount = 0;
const MAX_BACKEND_RESTARTS = 3;
let isQuitting = false;
let notificationPoller = null;

// ── GPU Compatibility (Intel Mac EGL workaround) ────────────────
// Force software rendering to avoid EGL/GPU black screen on Intel Macs.
// IMPORTANT: only disableHardwareAcceleration — do NOT add --disable-gpu
// or --disable-gpu-compositing, as those cause the compositor itself to
// fail and produce a black window.
app.disableHardwareAcceleration();

// ── Paths ──────────────────────────────────────────────────────────
function getBundledBackendDir() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }
  return path.join(__dirname, '../../backend');
}

function getWritableBackendDir() {
  return path.join(app.getPath('userData'), 'backend');
}

function getIconPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app', 'src', 'assets', 'icon.png');
  }
  return path.join(__dirname, '../src/assets/icon.png');
}

function getFontPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app', 'src', 'assets', 'fonts');
  }
  return path.join(__dirname, '../src/assets/fonts');
}

// ── Copy backend to writable location ──────────────────────────────
function copyDirSync(src, dest) {
  if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirSync(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function ensureWritableBackend() {
  const bundled = getBundledBackendDir();
  const writable = getWritableBackendDir();

  if (!app.isPackaged) {
    // Dev mode: use the source backend directly (already writable)
    return bundled;
  }

  // Check if we need to copy/update
  const marker = path.join(writable, '.version');
  const currentVersion = app.getVersion();
  let needsCopy = !fs.existsSync(writable) || !fs.existsSync(path.join(writable, 'main.py'));

  if (!needsCopy && fs.existsSync(marker)) {
    const existing = fs.readFileSync(marker, 'utf8').trim();
    if (existing !== currentVersion) needsCopy = true;
  } else if (!needsCopy) {
    needsCopy = true; // No version marker, force copy
  }

  if (needsCopy) {
    console.log('[App] Copying backend to writable location:', writable);
    try {
      copyDirSync(bundled, writable);
      fs.writeFileSync(marker, currentVersion);
    } catch (e) {
      console.error('[App] Copy failed:', e.message);
      // Try to use bundled directly as fallback
      return bundled;
    }
  } else {
    // Always refresh .env from bundled (in case user updated)
    const bundledEnv = path.join(bundled, '.env');
    const writableEnv = path.join(writable, '.env');
    if (fs.existsSync(bundledEnv) && !fs.existsSync(writableEnv)) {
      fs.copyFileSync(bundledEnv, writableEnv);
    }
  }

  return writable;
}

// ── Splash Screen ──────────────────────────────────────────────────
function createSplash() {
  const fontDir = getFontPath();
  let fontBase64 = '';
  const regularFont = path.join(fontDir, 'TerminessNerdFont-Regular.ttf');
  if (fs.existsSync(regularFont)) {
    try {
      fontBase64 = fs.readFileSync(regularFont).toString('base64');
    } catch {}
  }

  splashWindow = new BrowserWindow({
    width: 420,
    height: 340,
    frame: false,
    transparent: false,
    backgroundColor: '#0a0a1a',
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  const fontFace = fontBase64
    ? `@font-face { font-family: 'Terminess'; src: url('data:font/ttf;base64,${fontBase64}') format('truetype'); font-weight: normal; font-style: normal; }`
    : '';

  const fontFamily = fontBase64
    ? "'Terminess', 'SF Mono', 'Menlo', 'Courier New', monospace"
    : "'SF Mono', 'Menlo', 'Courier New', monospace";

  const html = `<!DOCTYPE html>
<html><head><style>
  ${fontFace}
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: linear-gradient(145deg, #0a0a1a 0%, #1a0a2e 40%, #0f0a20 100%);
    font-family: ${fontFamily};
    border-radius: 18px; border: 1px solid rgba(235,78,202,0.3);
    overflow: hidden; -webkit-app-region: drag;
  }
  .glow-ring {
    width: 80px; height: 80px; border-radius: 50%;
    border: 2px solid transparent; margin-bottom: 24px;
    background: linear-gradient(#0a0a1a, #0a0a1a) padding-box,
                linear-gradient(135deg, #00f0ff, #7b6ff0, #eb4eca) border-box;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 20px rgba(0,240,255,0.3), 0 0 40px rgba(235,78,202,0.2);
    animation: pulse 2s ease-in-out infinite;
  }
  .glow-ring span {
    font-size: 34px; font-weight: bold;
    background: linear-gradient(135deg, #00f0ff, #7b6ff0, #eb4eca);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 20px rgba(0,240,255,0.3), 0 0 40px rgba(235,78,202,0.2); }
    50% { box-shadow: 0 0 35px rgba(0,240,255,0.5), 0 0 60px rgba(235,78,202,0.35); }
  }
  h1 { font-size: 26px; letter-spacing: 8px; color: #eb4eca; margin-bottom: 6px;
    text-shadow: 0 0 10px rgba(235,78,202,0.5), 0 0 20px rgba(235,78,202,0.3); }
  .subtitle { font-size: 11px; color: #00f0ff; letter-spacing: 5px; margin-bottom: 30px; }
  .status {
    font-size: 10px; color: #888; letter-spacing: 2px;
    animation: blink 1.5s step-end infinite;
  }
  @keyframes blink { 50% { opacity: 0.4; } }
  .bar {
    width: 180px; height: 2px; background: #1a1a2e; border-radius: 2px;
    margin-top: 14px; overflow: hidden;
  }
  .bar-fill {
    height: 100%; width: 30%; background: linear-gradient(90deg, #eb4eca, #00f0ff);
    border-radius: 2px; animation: loading 1.8s ease-in-out infinite;
  }
  @keyframes loading {
    0% { transform: translateX(-100%); width: 30%; }
    50% { width: 60%; }
    100% { transform: translateX(400%); width: 30%; }
  }
</style></head><body>
  <div class="glow-ring"><span>N</span></div>
  <h1>NEONTRADE</h1>
  <div class="subtitle">AI TRADING SYSTEM</div>
  <div class="status" id="s">INICIANDO SISTEMA...</div>
  <div class="bar"><div class="bar-fill"></div></div>
</body></html>`;

  // Use loadURL with data URI - works without nodeIntegration
  splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  splashWindow.center();
}

function updateSplash(msg) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.executeJavaScript(
      `document.getElementById('s').textContent = ${JSON.stringify(msg)};`
    ).catch(() => {});
  }
}

// ── Port Check ─────────────────────────────────────────────────────
function checkPort(port) {
  return new Promise((resolve) => {
    const s = new net.Socket();
    s.setTimeout(500);
    s.on('connect', () => { s.destroy(); resolve(true); });
    s.on('timeout', () => { s.destroy(); resolve(false); });
    s.on('error', () => { s.destroy(); resolve(false); });
    s.connect(port, '127.0.0.1');
  });
}

async function waitForBackend(maxSec = 60) {
  for (let i = 0; i < maxSec * 2; i++) {
    const ok = await checkPort(8000);
    if (ok) return true;
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

// ── Python Detection ───────────────────────────────────────────────
function findPython() {
  // Order matters: prefer user-installed Python (has deps) over system Python 3.9
  const candidates = [
    '/usr/local/bin/python3',
    '/opt/homebrew/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/Current/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/3.14/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/3.11/bin/python3',
    '/Library/Frameworks/Python.framework/Versions/3.10/bin/python3',
    'python3', 'python',
    '/usr/bin/python3',
    // Windows paths
    'C:\\Python314\\python.exe',
    'C:\\Python313\\python.exe',
    'C:\\Python312\\python.exe',
  ];

  // First pass: find a Python that already has our dependencies
  for (const cmd of candidates) {
    try {
      const v = execSync(`"${cmd}" --version 2>&1`, { encoding: 'utf8', timeout: 5000 });
      if (!v.includes('3.')) continue;
      // Check if it has uvicorn (our key dependency)
      execSync(`"${cmd}" -c "import uvicorn" 2>&1`, { timeout: 5000 });
      console.log(`[App] Found Python with deps: ${cmd} (${v.trim()})`);
      return cmd;
    } catch {}
  }

  // Second pass: any Python 3.x (will need to pip install)
  for (const cmd of candidates) {
    try {
      const v = execSync(`"${cmd}" --version 2>&1`, { encoding: 'utf8', timeout: 5000 });
      if (v.includes('3.')) {
        console.log(`[App] Found Python (no deps): ${cmd} (${v.trim()})`);
        return cmd;
      }
    } catch {}
  }
  return null;
}

// ── Backend ────────────────────────────────────────────────────────
async function startBackend() {
  let backendDir;
  try {
    updateSplash('PREPARANDO BACKEND...');
    backendDir = ensureWritableBackend();
  } catch (e) {
    console.error('[App] ensureWritableBackend failed:', e);
    dialog.showMessageBoxSync({
      type: 'error',
      title: 'Error de inicialización',
      message: `No se pudo preparar el backend:\n${e.message}`,
    });
    return false;
  }

  // Ensure .env exists (never bundled - user must provide credentials)
  const envPath = path.join(backendDir, '.env');
  if (!fs.existsSync(envPath)) {
    // Try source location (dev mode only)
    const srcEnv = path.join(__dirname, '../../backend/.env');
    if (!app.isPackaged && fs.existsSync(srcEnv)) {
      try { fs.copyFileSync(srcEnv, envPath); } catch {}
    }

    // Copy .env.example as template if no .env found
    if (!fs.existsSync(envPath)) {
      const bundledExample = path.join(getBundledBackendDir(), '.env.example');
      const srcExample = path.join(__dirname, '../../backend/.env.example');
      const example = fs.existsSync(bundledExample) ? bundledExample : srcExample;
      if (fs.existsSync(example)) {
        try { fs.copyFileSync(example, envPath); } catch {}
      }
    }

    if (!fs.existsSync(envPath)) {
      dialog.showMessageBoxSync({
        type: 'error',
        title: 'Configuración requerida',
        message: 'No se encontró .env con credenciales del broker.\n\nCrea el archivo en:\n' + backendDir,
      });
      return false;
    }
  }

  // Create required directories (now in writable location)
  for (const dir of ['data', 'logs']) {
    const p = path.join(backendDir, dir);
    try {
      if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
    } catch (e) {
      console.error(`[App] mkdir ${dir} failed:`, e.message);
    }
  }

  // Find Python
  updateSplash('DETECTANDO PYTHON...');
  const python = findPython();
  if (!python) {
    dialog.showMessageBoxSync({
      type: 'error',
      title: 'Python no encontrado',
      message: 'NeonTrade AI necesita Python 3.10+\n\nDescárgalo en:\nhttps://www.python.org/downloads/',
    });
    return false;
  }
  console.log('[App] Using Python:', python);

  // Check/install dependencies
  updateSplash('VERIFICANDO DEPENDENCIAS...');
  try {
    execSync(`"${python}" -c "import uvicorn, httpx, loguru, fastapi" 2>&1`, { timeout: 10000 });
  } catch {
    updateSplash('INSTALANDO DEPENDENCIAS...');
    try {
      const reqPath = path.join(backendDir, 'requirements.txt');
      if (fs.existsSync(reqPath)) {
        execSync(`"${python}" -m pip install -r "${reqPath}" -q --disable-pip-version-check`, {
          cwd: backendDir,
          timeout: 180000,
          encoding: 'utf8',
        });
      }
    } catch (e) {
      console.error('[Backend] pip install failed:', e.message);
    }
  }

  // Start backend server
  updateSplash('INICIANDO TRADING ENGINE...');
  console.log('[App] Starting backend in:', backendDir);

  backendProcess = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  backendProcess.stdout.on('data', (d) => console.log(`[API] ${d}`));
  backendProcess.stderr.on('data', (d) => {
    const msg = d.toString();
    console.log(`[API] ${msg}`);
    if (msg.includes('Application startup complete')) {
      updateSplash('CONECTANDO A BROKER...');
    }
  });
  backendProcess.on('error', (e) => {
    console.error('[API] Start failed:', e);
    updateSplash('ERROR AL INICIAR BACKEND');
  });
  backendProcess.on('exit', (code) => {
    console.log(`[API] Exited (code ${code})`);
    if (isQuitting) return;

    if (code && code !== 0 && mainWindow) {
      backendRestartCount++;
      if (backendRestartCount <= MAX_BACKEND_RESTARTS) {
        console.log(`[App] Auto-restarting backend (attempt ${backendRestartCount}/${MAX_BACKEND_RESTARTS})...`);
        setTimeout(() => startBackend(), 2000);
      } else {
        dialog.showMessageBox(mainWindow, {
          type: 'warning',
          title: 'Backend detenido',
          message: `El servidor backend se detuvo inesperadamente tras ${MAX_BACKEND_RESTARTS} intentos de reinicio.\n\nRevisa los logs en la carpeta backend/logs/`,
        });
      }
    }
  });

  return true;
}

// ── Dist directory ─────────────────────────────────────────────────
function getDistDir() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app.asar', 'dist');
  }
  return path.join(__dirname, '..', 'dist');
}

// ── Custom protocol for serving dist files ─────────────────────────
function setupProtocol() {
  protocol.handle('neontrade', (request) => {
    const distDir = getDistDir();
    let reqPath = new URL(request.url).pathname;
    // Remove leading slash
    if (reqPath.startsWith('/')) reqPath = reqPath.substring(1);
    // Default to index.html
    if (!reqPath || reqPath === '') reqPath = 'index.html';

    const filePath = path.join(distDir, reqPath);

    try {
      const data = fs.readFileSync(filePath);
      const ext = path.extname(filePath).toLowerCase();
      const mimeTypes = {
        '.html': 'text/html',
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.svg': 'image/svg+xml',
        '.ttf': 'font/ttf',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ico': 'image/x-icon',
      };
      const contentType = mimeTypes[ext] || 'application/octet-stream';
      return new Response(data, {
        headers: { 'Content-Type': contentType },
      });
    } catch (e) {
      console.error(`[Protocol] File not found: ${filePath}`);
      return new Response('Not Found', { status: 404 });
    }
  });
}

// ── Main Window ────────────────────────────────────────────────────
function createWindow() {
  const iconPath = getIconPath();

  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 900,
    minHeight: 650,
    backgroundColor: '#0f0a1a',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    title: '',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    show: false,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
  });

  // Load via custom protocol (avoids file:// path issues in asar)
  mainWindow.loadURL('neontrade://app/index.html');

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) shell.openExternal(url);
    return { action: 'deny' };
  });

  // Log ALL renderer messages for debugging
  mainWindow.webContents.on('console-message', (e, level, msg) => {
    const prefix = ['[Renderer:LOG]', '[Renderer:WARN]', '[Renderer:ERR]'][level] || '[Renderer]';
    console.log(`${prefix} ${msg}`);
  });

  // Catch renderer crashes
  mainWindow.webContents.on('render-process-gone', (e, details) => {
    console.error('[Renderer] Process gone:', details.reason, details.exitCode);
  });

  mainWindow.webContents.on('did-fail-load', (e, code, desc, url) => {
    console.error(`[Renderer] Failed to load: ${desc} (${code}) - ${url}`);
  });

  // Inject custom title bar with Terminess Nerd Font
  mainWindow.webContents.on('did-finish-load', () => {
    const fontDir = getFontPath();
    let titleFontBase64 = '';
    const regularFont = path.join(fontDir, 'TerminessNerdFont-Bold.ttf');
    if (fs.existsSync(regularFont)) {
      try {
        titleFontBase64 = fs.readFileSync(regularFont).toString('base64');
      } catch {}
    }

    const fontFaceCSS = titleFontBase64
      ? `@font-face { font-family: 'TerminessTitleBar'; src: url('data:font/ttf;base64,${titleFontBase64}') format('truetype'); }`
      : '';
    const fontCSS = titleFontBase64
      ? "'TerminessTitleBar', 'SF Mono', monospace"
      : "'SF Mono', 'Menlo', monospace";

    mainWindow.webContents.executeJavaScript(`
      (function() {
        var style = document.createElement('style');
        style.textContent = \`
          ${fontFaceCSS}
          #neontrade-custom-titlebar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 38px;
            display: flex;
            align-items: center;
            justify-content: center;
            -webkit-app-region: drag;
            z-index: 99999;
            pointer-events: none;
            font-family: ${fontCSS};
          }
          #neontrade-custom-titlebar span {
            font-size: 13px;
            letter-spacing: 4px;
            color: #eb4eca;
            text-shadow: 0 0 8px rgba(235,78,202,0.4);
            font-weight: bold;
          }
        \`;
        document.head.appendChild(style);
        var bar = document.createElement('div');
        bar.id = 'neontrade-custom-titlebar';
        bar.innerHTML = '<span>NEONTRADE AI</span>';
        document.body.appendChild(bar);
      })();
    `).catch(() => {});
  });

  mainWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── Native macOS Notifications ───────────────────────────────────────
function sendNativeNotification(title, body) {
  if (!Notification.isSupported()) return;
  const notif = new Notification({
    title,
    body,
    silent: false,
  });
  notif.on('click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
  notif.show();
}

function startNotificationPoller() {
  notificationPoller = setInterval(async () => {
    if (isQuitting) return;

    try {
      // Fetch unread notifications from backend
      const notifications = await httpGet('http://127.0.0.1:8000/api/v1/notifications');
      if (Array.isArray(notifications)) {
        for (const notif of notifications) {
          sendNativeNotification(notif.title || 'NeonTrade AI', notif.body || '');
        }
      }
    } catch (e) {
      // Silent - backend may be restarting
    }
  }, 5000); // Poll every 5 seconds
}

function stopNotificationPoller() {
  if (notificationPoller) {
    clearInterval(notificationPoller);
    notificationPoller = null;
  }
}

function httpGet(reqUrl) {
  return new Promise((resolve, reject) => {
    const req = http.get(reqUrl, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve(null); }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

// ── Menu ───────────────────────────────────────────────────────────
function createMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{
      label: 'NeonTrade AI',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    }] : []),
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { role: 'resetZoom' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac ? [{ type: 'separator' }, { role: 'front' }] : [{ role: 'close' }]),
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── App Lifecycle ──────────────────────────────────────────────────
// Register protocol scheme before app is ready
protocol.registerSchemesAsPrivileged([{
  scheme: 'neontrade',
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
}]);

app.whenReady().then(async () => {
  try {
    setupProtocol();
    createSplash();
    createMenu();

    // Check if backend already running (e.g., user started manually)
    const alreadyUp = await checkPort(8000);
    if (!alreadyUp) {
      const ok = await startBackend();
      if (!ok) { app.quit(); return; }

      updateSplash('CONECTANDO A CAPITAL.COM...');
      const ready = await waitForBackend(60);
      if (!ready) {
        if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
        dialog.showMessageBoxSync({
          type: 'error',
          title: 'Error de conexión',
          message: 'No se pudo iniciar el servidor backend.\n\n' +
                   'Asegúrate de que Python 3 y las dependencias estén instaladas.\n' +
                   'Revisa logs en: backend/logs/',
        });
        app.quit();
        return;
      }
    }

    updateSplash('CARGANDO INTERFAZ...');
    createWindow();

    // Start native notification polling
    startNotificationPoller();
    console.log('[App] Native notifications enabled');
  } catch (e) {
    console.error('[App] Fatal error:', e);
    dialog.showMessageBoxSync({
      type: 'error',
      title: 'Error fatal',
      message: `NeonTrade AI falló al iniciar:\n\n${e.message}\n\nRevisa la consola para más detalles.`,
    });
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

app.on('before-quit', () => {
  isQuitting = true;
  stopNotificationPoller();
  if (backendProcess && !backendProcess.killed) {
    try {
      backendProcess.kill('SIGTERM');
      // Force kill after 5 seconds if still alive
      setTimeout(() => {
        if (backendProcess && !backendProcess.killed) {
          backendProcess.kill('SIGKILL');
        }
      }, 5000);
      console.log('[API] Backend stopped');
    } catch {}
  }
});
