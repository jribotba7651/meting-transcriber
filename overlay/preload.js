const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // --- Chat ---
  sendMessage: (messages, model) => ipcRenderer.invoke('chat:send', { messages, model }),
  stopGeneration: () => ipcRenderer.invoke('chat:stop'),
  onChatToken: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat:token', handler);
    return () => ipcRenderer.removeListener('chat:token', handler);
  },
  onChatDone: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat:done', handler);
    return () => ipcRenderer.removeListener('chat:done', handler);
  },
  onChatError: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat:error', handler);
    return () => ipcRenderer.removeListener('chat:error', handler);
  },

  // --- Clipboard ---
  readClipboard: () => ipcRenderer.invoke('clipboard:read'),
  onClipboardChange: (callback) => {
    const handler = (_event, text) => callback(text);
    ipcRenderer.on('clipboard:change', handler);
    return () => ipcRenderer.removeListener('clipboard:change', handler);
  },

  // --- OCR ---
  captureOCR: () => ipcRenderer.invoke('ocr:capture'),
  onOCRResult: (callback) => {
    const handler = (_event, text) => callback(text);
    ipcRenderer.on('ocr:result', handler);
    return () => ipcRenderer.removeListener('ocr:result', handler);
  },

  // --- History ---
  loadHistory: () => ipcRenderer.invoke('history:load'),
  saveHistory: (messages) => ipcRenderer.invoke('history:save', messages),

  // --- Window control ---
  setOpacity: (value) => ipcRenderer.invoke('window:set-opacity', value),
  setClickThrough: (value) => ipcRenderer.invoke('window:set-click-through', value),
  hideWindow: () => ipcRenderer.invoke('window:hide'),

  // --- Config ---
  getConfig: () => ipcRenderer.invoke('config:get'),

  // --- Health check ---
  checkOllama: () => ipcRenderer.invoke('app:check-ollama'),

  // --- Live Transcript ---
  getLiveTranscript: () => ipcRenderer.invoke('transcript:get-live')
});
