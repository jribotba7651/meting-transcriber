const { app, BrowserWindow, globalShortcut, ipcMain, screen, clipboard, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const { ClipboardService } = require('./services/clipboard');
const { AIService } = require('./services/ai');
const { OCRService } = require('./services/ocr');

let mainWindow = null;
let tray = null;
let clipboardService = null;
let aiService = null;
let ocrService = null;
let isVisible = true;

function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize;

  // Overlay window: 380px wide, 500px tall, positioned bottom-right
  const winWidth = 380;
  const winHeight = 500;

  mainWindow = new BrowserWindow({
    width: winWidth,
    height: winHeight,
    x: screenWidth - winWidth - 20,
    y: screenHeight - winHeight - 20,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    hasShadow: false,
    // Make it click-through when not focused (optional, can toggle)
    // focusable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Prevent the window from appearing in screenshots/screen sharing on supported platforms
  mainWindow.setContentProtection(true);

  // Make window ignore mouse events when holding Ctrl+Alt (pass-through mode)
  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  // Create a simple 16x16 tray icon
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show/Hide (Ctrl+Shift+Space)', click: () => toggleVisibility() },
    { label: 'Reset Position', click: () => resetPosition() },
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
  mainWindow.setPosition(screenWidth - 400, screenHeight - 520);
}

function registerShortcuts() {
  // Toggle overlay visibility
  globalShortcut.register('CommandOrControl+Shift+Space', toggleVisibility);

  // Capture screen region for OCR
  globalShortcut.register('CommandOrControl+Shift+O', async () => {
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

  // Quick ask: send clipboard content to AI
  globalShortcut.register('CommandOrControl+Shift+A', () => {
    if (mainWindow) {
      const text = clipboard.readText();
      if (text) {
        mainWindow.webContents.send('clipboard-quick-ask', text);
      }
    }
  });
}

function setupIPC() {
  // AI chat
  ipcMain.handle('ai:chat', async (event, { messages, model }) => {
    return await aiService.chat(messages, model);
  });

  ipcMain.handle('ai:chat-stream', async (event, { messages, model }) => {
    const stream = await aiService.chatStream(messages, model);
    let fullResponse = '';

    for await (const chunk of stream) {
      fullResponse += chunk;
      mainWindow.webContents.send('ai:stream-chunk', chunk);
    }

    mainWindow.webContents.send('ai:stream-done');
    return fullResponse;
  });

  // List available models
  ipcMain.handle('ai:models', async () => {
    return await aiService.listModels();
  });

  // OCR
  ipcMain.handle('ocr:capture', async () => {
    return await ocrService.captureAndRecognize();
  });

  // Clipboard
  ipcMain.handle('clipboard:read', () => {
    return clipboard.readText();
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
  // Initialize services
  aiService = new AIService();
  ocrService = new OCRService();
  clipboardService = new ClipboardService((text) => {
    if (mainWindow) {
      mainWindow.webContents.send('clipboard-change', text);
    }
  });

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
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
