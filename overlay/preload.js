const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // AI
  chat: (messages, model) => ipcRenderer.invoke('ai:chat', { messages, model }),
  chatStream: (messages, model) => ipcRenderer.invoke('ai:chat-stream', { messages, model }),
  onStreamChunk: (callback) => ipcRenderer.on('ai:stream-chunk', (_, chunk) => callback(chunk)),
  onStreamDone: (callback) => ipcRenderer.on('ai:stream-done', () => callback()),
  onStreamError: (callback) => ipcRenderer.on('ai:stream-error', (_, err) => callback(err)),
  listModels: () => ipcRenderer.invoke('ai:models'),
  healthCheck: () => ipcRenderer.invoke('ai:health'),

  // OCR
  captureOCR: () => ipcRenderer.invoke('ocr:capture'),
  onOCRStarted: (callback) => ipcRenderer.on('ocr-started', () => callback()),
  onOCRResult: (callback) => ipcRenderer.on('ocr-result', (_, text) => callback(text)),
  onOCRError: (callback) => ipcRenderer.on('ocr-error', (_, err) => callback(err)),

  // Clipboard
  readClipboard: () => ipcRenderer.invoke('clipboard:read'),
  onClipboardChange: (callback) => ipcRenderer.on('clipboard-change', (_, text) => callback(text)),
  onClipboardQuickAsk: (callback) => ipcRenderer.on('clipboard-quick-ask', (_, text) => callback(text)),
  startClipboardMonitoring: () => ipcRenderer.send('clipboard:start-monitoring'),
  stopClipboardMonitoring: () => ipcRenderer.send('clipboard:stop-monitoring'),

  // Config
  getConfig: () => ipcRenderer.invoke('config:get'),
  getSystemPrompt: () => ipcRenderer.invoke('config:get-system-prompt'),

  // Chat history persistence
  loadHistory: () => ipcRenderer.invoke('history:load'),
  saveHistory: (history) => ipcRenderer.invoke('history:save', history),
  onHistoryCleared: (callback) => ipcRenderer.on('history-cleared', () => callback()),

  // Window
  minimizeWindow: () => ipcRenderer.send('window:minimize'),
  closeWindow: () => ipcRenderer.send('window:close'),
  setIgnoreMouse: (ignore) => ipcRenderer.send('window:set-ignore-mouse', ignore),
  setOpacity: (opacity) => ipcRenderer.send('window:set-opacity', opacity),
});
