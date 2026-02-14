const {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Tray,
  Menu,
  nativeImage,
  clipboard
} = require('electron');
const path = require('path');
const fs = require('fs');

const OllamaClient = require('./services/ai');
const ClipboardMonitor = require('./services/clipboard');
const OCRService = require('./services/ocr');

// ─── Load Config ───────────────────────────────────────────────
const configPath = path.join(__dirname, 'config.json');
let config;
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (err) {
  console.error('Failed to load config.json, using defaults:', err.message);
  config = {
    ollama: { baseUrl: 'http://localhost:11434', model: 'llama3.2', systemPrompt: 'You are a helpful AI assistant.' },
    hotkeys: { toggle: 'CommandOrControl+Shift+Space', ocr: 'CommandOrControl+Shift+O', sendClipboard: 'CommandOrControl+Shift+A' },
    clipboard: { monitorInterval: 500 },
    window: { width: 420, height: 600, opacity: 0.95, x: null, y: null },
    chatHistoryFile: 'chat_history.json'
  };
}

// ─── Services ──────────────────────────────────────────────────
const ollamaClient = new OllamaClient(config.ollama.baseUrl);
const clipboardMonitor = new ClipboardMonitor(config.clipboard.monitorInterval);
const ocrService = new OCRService();

let mainWindow = null;
let tray = null;
let isClickThrough = false;

// ─── Single Instance Lock ──────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ─── Create Tray Icon (programmatic) ──────────────────────────
function createTrayIcon() {
  // Generate a 16x16 green circle icon
  const size = 16;
  const canvas = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">
    <circle cx="8" cy="8" r="7" fill="#4ade80" stroke="#166534" stroke-width="1"/>
  </svg>`;

  const base64 = Buffer.from(canvas).toString('base64');
  const dataUrl = `data:image/svg+xml;base64,${base64}`;
  return nativeImage.createFromDataURL(dataUrl);
}

// ─── Save Config ───────────────────────────────────────────────
function saveConfig() {
  try {
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  } catch (err) {
    console.error('Failed to save config:', err.message);
  }
}

// ─── Create Main Window ────────────────────────────────────────
function createWindow() {
  const winOptions = {
    width: config.window.width,
    height: config.window.height,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  };

  // Restore position if saved
  if (config.window.x !== null && config.window.y !== null) {
    winOptions.x = config.window.x;
    winOptions.y = config.window.y;
  } else {
    winOptions.center = true;
  }

  mainWindow = new BrowserWindow(winOptions);

  // Make invisible to screen capture
  mainWindow.setContentProtection(true);
  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  mainWindow.setOpacity(config.window.opacity);

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Save window position on move (debounced)
  let moveTimeout = null;
  mainWindow.on('move', () => {
    clearTimeout(moveTimeout);
    moveTimeout = setTimeout(() => {
      const [x, y] = mainWindow.getPosition();
      config.window.x = x;
      config.window.y = y;
      saveConfig();
    }, 500);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─── Register Global Hotkeys ───────────────────────────────────
function registerHotkeys() {
  // Toggle overlay visibility
  globalShortcut.register(config.hotkeys.toggle, () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
      // Disable click-through when showing
      if (isClickThrough) {
        isClickThrough = false;
        mainWindow.setIgnoreMouseEvents(false);
      }
    }
  });

  // Screenshot + OCR
  globalShortcut.register(config.hotkeys.ocr, async () => {
    if (!mainWindow) return;
    try {
      const text = await ocrService.captureAndRecognize(mainWindow);
      mainWindow.webContents.send('ocr:result', text);
      mainWindow.show();
    } catch (err) {
      mainWindow.webContents.send('ocr:result', `[OCR Error] ${err.message}`);
      mainWindow.show();
    }
  });

  // Send clipboard to chat
  globalShortcut.register(config.hotkeys.sendClipboard, () => {
    if (!mainWindow) return;
    const text = clipboard.readText();
    if (text) {
      mainWindow.webContents.send('clipboard:change', text);
      mainWindow.show();
    }
  });
}

// ─── Setup Tray ────────────────────────────────────────────────
function setupTray() {
  const icon = createTrayIcon();
  tray = new Tray(icon);
  tray.setToolTip('AI Overlay');

  const updateTrayMenu = () => {
    const contextMenu = Menu.buildFromTemplate([
      {
        label: mainWindow && mainWindow.isVisible() ? 'Hide Overlay' : 'Show Overlay',
        click: () => {
          if (mainWindow.isVisible()) {
            mainWindow.hide();
          } else {
            mainWindow.show();
            mainWindow.focus();
          }
        }
      },
      { type: 'separator' },
      {
        label: 'Opacity',
        submenu: [
          { label: '95%', click: () => { mainWindow.setOpacity(0.95); config.window.opacity = 0.95; saveConfig(); } },
          { label: '70%', click: () => { mainWindow.setOpacity(0.70); config.window.opacity = 0.70; saveConfig(); } },
          { label: '40%', click: () => { mainWindow.setOpacity(0.40); config.window.opacity = 0.40; saveConfig(); } },
          { label: '20%', click: () => { mainWindow.setOpacity(0.20); config.window.opacity = 0.20; saveConfig(); } }
        ]
      },
      {
        label: isClickThrough ? 'Disable Click-Through' : 'Enable Click-Through',
        click: () => {
          isClickThrough = !isClickThrough;
          mainWindow.setIgnoreMouseEvents(isClickThrough);
          updateTrayMenu();
        }
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          app.quit();
        }
      }
    ]);
    tray.setContextMenu(contextMenu);
  };

  updateTrayMenu();
  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

// ─── IPC Handlers ──────────────────────────────────────────────
function setupIPC() {
  // Chat: send message and stream response
  ipcMain.handle('chat:send', (event, { messages, model }) => {
    const useModel = model || config.ollama.model;

    // Prepend system prompt if not already present
    const fullMessages = [...messages];
    if (fullMessages.length === 0 || fullMessages[0].role !== 'system') {
      fullMessages.unshift({ role: 'system', content: config.ollama.systemPrompt });
    }

    ollamaClient.streamChat(
      useModel,
      fullMessages,
      (token) => {
        if (mainWindow) mainWindow.webContents.send('chat:token', token);
      },
      (stats) => {
        if (mainWindow) mainWindow.webContents.send('chat:done', stats);
      },
      (error) => {
        if (mainWindow) mainWindow.webContents.send('chat:error', error.message);
      }
    );

    return { started: true };
  });

  // Chat: stop generation
  ipcMain.handle('chat:stop', () => {
    ollamaClient.abort();
    return { stopped: true };
  });

  // Clipboard: read current
  ipcMain.handle('clipboard:read', () => {
    return clipboardMonitor.getCurrentText();
  });

  // OCR: capture and recognize
  ipcMain.handle('ocr:capture', async () => {
    try {
      const text = await ocrService.captureAndRecognize(mainWindow);
      return { success: true, text };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });

  // History: load from disk
  ipcMain.handle('history:load', () => {
    const historyPath = path.join(__dirname, config.chatHistoryFile);
    try {
      if (fs.existsSync(historyPath)) {
        return JSON.parse(fs.readFileSync(historyPath, 'utf8'));
      }
    } catch (err) {
      console.warn('Could not load chat history:', err.message);
    }
    return [];
  });

  // History: save to disk
  ipcMain.handle('history:save', (_event, messages) => {
    const historyPath = path.join(__dirname, config.chatHistoryFile);
    try {
      fs.writeFileSync(historyPath, JSON.stringify(messages, null, 2));
      return { success: true };
    } catch (err) {
      console.error('Could not save chat history:', err.message);
      return { success: false, error: err.message };
    }
  });

  // Window: set opacity
  ipcMain.handle('window:set-opacity', (_event, value) => {
    if (mainWindow) {
      mainWindow.setOpacity(value);
      config.window.opacity = value;
      saveConfig();
    }
  });

  // Window: set click-through
  ipcMain.handle('window:set-click-through', (_event, value) => {
    if (mainWindow) {
      isClickThrough = value;
      mainWindow.setIgnoreMouseEvents(value);
    }
  });

  // Window: hide
  ipcMain.handle('window:hide', () => {
    if (mainWindow) mainWindow.hide();
  });

  // Config: get
  ipcMain.handle('config:get', () => {
    return config;
  });

  // Health: check Ollama connection
  ipcMain.handle('app:check-ollama', async () => {
    return await ollamaClient.checkConnection();
  });

  // Transcript: get live transcript from Python app
  ipcMain.handle('transcript:get-live', () => {
    const transcriptPath = path.join(
      process.env.LOCALAPPDATA || path.join(require('os').homedir(), 'AppData', 'Local'),
      'meeting-transcriber',
      'live_transcript.json'
    );

    try {
      if (fs.existsSync(transcriptPath)) {
        const raw = fs.readFileSync(transcriptPath, 'utf8');
        const data = JSON.parse(raw);
        return { success: true, data };
      }
      return { success: false, error: 'No live transcript found. Start live transcription first.' };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });
}

// ─── App Ready ─────────────────────────────────────────────────
app.whenReady().then(async () => {
  createWindow();
  setupIPC();
  registerHotkeys();
  setupTray();

  // Start clipboard monitoring
  clipboardMonitor.start((text) => {
    if (mainWindow) {
      mainWindow.webContents.send('clipboard:change', text);
    }
  });

  // Pre-initialize OCR worker in background
  ocrService.initialize().catch(err => {
    console.warn('OCR pre-init failed (will retry on first use):', err.message);
  });
});

// ─── Cleanup ───────────────────────────────────────────────────
app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  clipboardMonitor.stop();
  ocrService.terminate();
});

app.on('window-all-closed', () => {
  // On macOS, keep app running in tray
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
