const { app, BrowserWindow, globalShortcut, ipcMain, screen, clipboard, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const { ClipboardService } = require('./services/clipboard');
const { AIService } = require('./services/ai');
const { OCRService } = require('./services/ocr');

// Load configuration
const configPath = path.join(__dirname, 'config.json');
let config = {};
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
} catch (e) {
  console.error('Failed to load config.json, using defaults');
}

const ollamaConfig = config.ollama || {};
const windowConfig = config.window || {};
const shortcutConfig = config.shortcuts || {};
const clipboardConfig = config.clipboard || {};
const ocrConfig = config.ocr || {};
const systemPrompt = config.systemPrompt || '';

let mainWindow = null;
let tray = null;
let clipboardService = null;
let aiService = null;
let ocrService = null;
let isVisible = true;

// Chat history persistence
const historyPath = path.join(app.getPath('userData'), 'chat_history.json');

function loadChatHistory() {
  try {
    if (fs.existsSync(historyPath)) {
      return JSON.parse(fs.readFileSync(historyPath, 'utf-8'));
    }
  } catch (e) {
    // Corrupted file, start fresh
  }
  return [];
}

function saveChatHistory(history) {
  try {
    fs.writeFileSync(historyPath, JSON.stringify(history, null, 2));
  } catch (e) {
    console.error('Failed to save chat history:', e.message);
  }
}

function createTrayIcon() {
  // Generate a 16x16 PNG tray icon programmatically (blue circle with "AI" text)
  // Use a simple canvas-less approach: create from a data URL via nativeImage
  // 16x16 blue square icon as raw RGBA buffer
  const size = 16;
  const buffer = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      // Create a rounded blue square
      const cx = x - size / 2 + 0.5;
      const cy = y - size / 2 + 0.5;
      const dist = Math.sqrt(cx * cx + cy * cy);
      if (dist < size / 2 - 1) {
        buffer[idx] = 59;     // R
        buffer[idx + 1] = 130; // G
        buffer[idx + 2] = 246; // B
        buffer[idx + 3] = 255; // A
      } else if (dist < size / 2) {
        // Anti-aliased edge
        buffer[idx] = 59;
        buffer[idx + 1] = 130;
        buffer[idx + 2] = 246;
        buffer[idx + 3] = 128;
      } else {
        buffer[idx + 3] = 0;  // Transparent
      }
    }
  }
  return nativeImage.createFromBuffer(buffer, { width: size, height: size });
}

function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize;

  const winWidth = windowConfig.width || 380;
  const winHeight = windowConfig.height || 500;
  const margin = windowConfig.margin || 20;

  // Calculate position based on config
  let x, y;
  const pos = windowConfig.position || 'bottom-right';
  switch (pos) {
    case 'top-left':
      x = margin; y = margin; break;
    case 'top-right':
      x = screenWidth - winWidth - margin; y = margin; break;
    case 'bottom-left':
      x = margin; y = screenHeight - winHeight - margin; break;
    default: // bottom-right
      x = screenWidth - winWidth - margin;
      y = screenHeight - winHeight - margin;
  }

  mainWindow = new BrowserWindow({
    width: winWidth,
    height: winHeight,
    x,
    y,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  mainWindow.setOpacity(windowConfig.opacity || 0.95);
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Prevent the window from appearing in screenshots/screen sharing
  mainWindow.setContentProtection(true);
  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const icon = createTrayIcon();
  tray = new Tray(icon);

  const shortcutLabel = shortcutConfig.toggleOverlay || 'Ctrl+Shift+Space';
  const contextMenu = Menu.buildFromTemplate([
    { label: `Show/Hide (${shortcutLabel})`, click: () => toggleVisibility() },
    { label: 'Reset Position', click: () => resetPosition() },
    { type: 'separator' },
    { label: 'Clear Chat History', click: () => clearPersistedHistory() },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() }
  ]);

  tray.setToolTip('Local AI Assistant');
  tray.setContextMenu(contextMenu);
}

function toggleVisibility() {
  if (!mainWindow) return;

  if (isVisible) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
  isVisible = !isVisible;
}

function resetPosition() {
  if (!mainWindow) return;
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize;
  const margin = windowConfig.margin || 20;
  mainWindow.setPosition(
    screenWidth - (windowConfig.width || 380) - margin,
    screenHeight - (windowConfig.height || 500) - margin
  );
}

function clearPersistedHistory() {
  saveChatHistory([]);
  if (mainWindow) {
    mainWindow.webContents.send('history-cleared');
  }
}

function registerShortcuts() {
  const toggleKey = shortcutConfig.toggleOverlay || 'CommandOrControl+Shift+Space';
  const ocrKey = shortcutConfig.screenshotOCR || 'CommandOrControl+Shift+O';
  const clipKey = shortcutConfig.clipboardAsk || 'CommandOrControl+Shift+A';

  globalShortcut.register(toggleKey, toggleVisibility);

  globalShortcut.register(ocrKey, async () => {
    if (mainWindow) {
      mainWindow.webContents.send('ocr-started');
      try {
        const text = await ocrService.captureAndRecognize();
        mainWindow.webContents.send('ocr-result', text);
      } catch (err) {
        mainWindow.webContents.send('ocr-error', err.message);
      }
    }
  });

  globalShortcut.register(clipKey, () => {
    if (mainWindow) {
      const text = clipboard.readText();
      if (text) {
        mainWindow.webContents.send('clipboard-quick-ask', text);
      }
    }
  });
}

function setupIPC() {
  // AI chat (non-streaming)
  ipcMain.handle('ai:chat', async (event, { messages, model }) => {
    return await aiService.chat(messages, model);
  });

  // AI chat (streaming)
  ipcMain.handle('ai:chat-stream', async (event, { messages, model }) => {
    try {
      const stream = await aiService.chatStream(messages, model);
      let fullResponse = '';

      for await (const chunk of stream) {
        fullResponse += chunk;
        if (mainWindow) {
          mainWindow.webContents.send('ai:stream-chunk', chunk);
        }
      }

      if (mainWindow) {
        mainWindow.webContents.send('ai:stream-done');
      }
      return fullResponse;
    } catch (err) {
      if (mainWindow) {
        mainWindow.webContents.send('ai:stream-error', err.message);
      }
      throw err;
    }
  });

  // List available models
  ipcMain.handle('ai:models', async () => {
    return await aiService.listModels();
  });

  // Check Ollama connection
  ipcMain.handle('ai:health', async () => {
    return await aiService.healthCheck();
  });

  // OCR
  ipcMain.handle('ocr:capture', async () => {
    return await ocrService.captureAndRecognize();
  });

  // Clipboard
  ipcMain.handle('clipboard:read', () => {
    return clipboard.readText();
  });

  // Config
  ipcMain.handle('config:get', () => {
    return config;
  });

  ipcMain.handle('config:get-system-prompt', () => {
    return systemPrompt;
  });

  // Chat history persistence
  ipcMain.handle('history:load', () => {
    return loadChatHistory();
  });

  ipcMain.handle('history:save', (event, history) => {
    saveChatHistory(history);
    return true;
  });

  // Window controls
  ipcMain.on('window:minimize', () => {
    mainWindow?.hide();
    isVisible = false;
  });

  ipcMain.on('window:close', () => {
    app.quit();
  });

  ipcMain.on('window:set-ignore-mouse', (event, ignore) => {
    mainWindow?.setIgnoreMouseEvents(ignore, { forward: true });
  });

  ipcMain.on('window:set-opacity', (event, opacity) => {
    mainWindow?.setOpacity(opacity);
  });

  // Clipboard monitoring toggle
  ipcMain.on('clipboard:start-monitoring', () => {
    clipboardService.start();
  });

  ipcMain.on('clipboard:stop-monitoring', () => {
    clipboardService.stop();
  });
}

app.whenReady().then(() => {
  // Initialize services with config
  aiService = new AIService(
    ollamaConfig.baseUrl || 'http://localhost:11434',
    ollamaConfig.requestTimeout || 120000
  );
  ocrService = new OCRService(ocrConfig.languages || 'eng+spa');
  clipboardService = new ClipboardService(
    (text) => {
      if (mainWindow) {
        mainWindow.webContents.send('clipboard-change', text);
      }
    },
    clipboardConfig.pollIntervalMs || 500
  );

  // Auto-start clipboard monitoring if configured
  if (clipboardConfig.autoMonitor) {
    clipboardService.start();
  }

  createWindow();
  createTray();
  registerShortcuts();
  setupIPC();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  clipboardService?.stop();
  ocrService?.cleanup();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
