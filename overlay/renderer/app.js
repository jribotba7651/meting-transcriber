// State
let chatHistory = [];
let currentModel = 'llama3.2';
let isStreaming = false;
let clipboardMonitoring = false;
let currentContext = '';

// DOM elements
const messagesEl = document.getElementById('messages');
const chatContainer = document.getElementById('chat-container');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnClipboard = document.getElementById('btn-clipboard');
const btnOCR = document.getElementById('btn-ocr');
const btnClear = document.getElementById('btn-clear');
const btnMinimize = document.getElementById('btn-minimize');
const btnClose = document.getElementById('btn-close');
const btnPassthrough = document.getElementById('btn-passthrough');
const btnOpacity = document.getElementById('btn-opacity');
const modelBadge = document.getElementById('model-badge');
const modelSelector = document.getElementById('model-selector');
const modelList = document.getElementById('model-list');
const statusText = document.getElementById('status-text');
const clipboardIndicator = document.getElementById('clipboard-indicator');
const ollamaIndicator = document.getElementById('ollama-indicator');
const contextPreview = document.getElementById('context-preview');
const contextText = document.getElementById('context-text');
const clearContext = document.getElementById('clear-context');

// ====== Chat Functions ======

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = role === 'user' ? 'You' : role === 'assistant' ? 'AI' : 'System';

  const msg = document.createElement('div');
  msg.className = 'message-content';
  msg.innerHTML = formatMessage(content);

  div.appendChild(label);
  div.appendChild(msg);
  messagesEl.appendChild(div);
  scrollToBottom();

  return msg;
}

function addStreamingMessage() {
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.id = 'streaming-message';

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = 'AI';

  const msg = document.createElement('div');
  msg.className = 'message-content';
  msg.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

  div.appendChild(label);
  div.appendChild(msg);
  messagesEl.appendChild(div);
  scrollToBottom();

  return msg;
}

function formatMessage(text) {
  // Simple markdown-like formatting
  let html = text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Line breaks
    .replace(/\n/g, '<br>');

  return html;
}

function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  // Build the user message with optional context
  let fullMessage = text;
  if (currentContext) {
    fullMessage = `Context:\n${currentContext}\n\nQuestion: ${text}`;
    clearCurrentContext();
  }

  addMessage('user', text);
  userInput.value = '';
  autoResizeInput();

  chatHistory.push({ role: 'user', content: fullMessage });

  isStreaming = true;
  btnSend.disabled = true;
  statusText.textContent = 'Thinking...';

  const streamMsg = addStreamingMessage();
  let fullResponse = '';

  try {
    // Use streaming
    window.api.chatStream(chatHistory, currentModel);

    // The response comes via events
    streamMsg.innerHTML = '';

  } catch (err) {
    streamMsg.innerHTML = `<span class="error-text">Error: ${err.message}</span>`;
    isStreaming = false;
    btnSend.disabled = false;
    statusText.textContent = 'Error';
  }
}

// Stream event handlers
window.api.onStreamChunk((chunk) => {
  const streamMsg = document.querySelector('#streaming-message .message-content');
  if (streamMsg) {
    // Remove typing indicator if present
    const typingIndicator = streamMsg.querySelector('.typing-indicator');
    if (typingIndicator) typingIndicator.remove();

    // Accumulate raw text
    if (!streamMsg._rawText) streamMsg._rawText = '';
    streamMsg._rawText += chunk;
    streamMsg.innerHTML = formatMessage(streamMsg._rawText);
    scrollToBottom();
  }
});

window.api.onStreamDone(() => {
  const streamMsg = document.querySelector('#streaming-message .message-content');
  if (streamMsg && streamMsg._rawText) {
    chatHistory.push({ role: 'assistant', content: streamMsg._rawText });
  }

  // Remove streaming ID
  const streamEl = document.getElementById('streaming-message');
  if (streamEl) streamEl.removeAttribute('id');

  isStreaming = false;
  btnSend.disabled = false;
  statusText.textContent = 'Ready';
});

// ====== Context Management ======

function setContext(text) {
  currentContext = text;
  const truncated = text.length > 80 ? text.substring(0, 80) + '...' : text;
  contextText.textContent = truncated;
  contextPreview.classList.remove('hidden');
}

function clearCurrentContext() {
  currentContext = '';
  contextPreview.classList.add('hidden');
  contextText.textContent = '';
}

// ====== Clipboard ======

function toggleClipboardMonitoring() {
  clipboardMonitoring = !clipboardMonitoring;

  if (clipboardMonitoring) {
    window.api.startClipboardMonitoring();
    btnClipboard.classList.add('active');
    clipboardIndicator.textContent = 'CB: ON';
    clipboardIndicator.classList.add('active');
  } else {
    window.api.stopClipboardMonitoring();
    btnClipboard.classList.remove('active');
    clipboardIndicator.textContent = 'CB: OFF';
    clipboardIndicator.classList.remove('active');
  }
}

window.api.onClipboardChange((text) => {
  setContext(text);
  statusText.textContent = 'Clipboard captured';
  setTimeout(() => { statusText.textContent = 'Ready'; }, 2000);
});

window.api.onClipboardQuickAsk((text) => {
  setContext(text);
  userInput.focus();
});

// ====== OCR ======

async function triggerOCR() {
  statusText.textContent = 'Capturing screen...';
  btnOCR.disabled = true;

  try {
    const text = await window.api.captureOCR();
    if (text) {
      setContext(text);
      statusText.textContent = 'OCR captured';
      userInput.focus();
    } else {
      statusText.textContent = 'OCR: no text found';
    }
  } catch (err) {
    statusText.textContent = 'OCR failed';
    addMessage('system', `OCR Error: ${err.message}`);
  }

  btnOCR.disabled = false;
  setTimeout(() => { statusText.textContent = 'Ready'; }, 3000);
}

window.api.onOCRResult((text) => {
  if (text) {
    setContext(text);
    statusText.textContent = 'OCR captured (hotkey)';
    userInput.focus();
  }
});

window.api.onOCRError((err) => {
  addMessage('system', `OCR Error: ${err}`);
  statusText.textContent = 'OCR failed';
});

// ====== Model Selection ======

let modelSelectorOpen = false;

async function toggleModelSelector() {
  modelSelectorOpen = !modelSelectorOpen;

  if (modelSelectorOpen) {
    modelSelector.classList.remove('hidden');
    await loadModels();
  } else {
    modelSelector.classList.add('hidden');
  }
}

async function loadModels() {
  modelList.innerHTML = '<div class="model-option">Loading...</div>';

  try {
    const models = await window.api.listModels();

    if (models.length === 0) {
      modelList.innerHTML = '<div class="model-option">No models found. Is Ollama running?</div>';
      ollamaIndicator.textContent = 'AI: OFF';
      ollamaIndicator.classList.add('error');
      ollamaIndicator.classList.remove('active');
      return;
    }

    ollamaIndicator.textContent = 'AI: ON';
    ollamaIndicator.classList.add('active');
    ollamaIndicator.classList.remove('error');

    modelList.innerHTML = '';
    models.forEach(m => {
      const div = document.createElement('div');
      div.className = `model-option ${m.name === currentModel ? 'active' : ''}`;
      div.textContent = m.name;
      div.addEventListener('click', () => {
        currentModel = m.name;
        modelBadge.textContent = m.name;
        modelSelector.classList.add('hidden');
        modelSelectorOpen = false;
      });
      modelList.appendChild(div);
    });
  } catch (err) {
    modelList.innerHTML = '<div class="model-option error-text">Failed to load models</div>';
  }
}

// ====== Window Controls ======

let passthroughMode = false;
const opacityLevels = [0.95, 0.7, 0.4, 0.2];
let opacityIndex = 0;

function togglePassthrough() {
  passthroughMode = !passthroughMode;
  window.api.setIgnoreMouse(passthroughMode);
  btnPassthrough.style.color = passthroughMode ? '#22c55e' : '';
}

function cycleOpacity() {
  opacityIndex = (opacityIndex + 1) % opacityLevels.length;
  window.api.setOpacity(opacityLevels[opacityIndex]);
  btnOpacity.title = `Opacity: ${Math.round(opacityLevels[opacityIndex] * 100)}%`;
}

function clearChat() {
  chatHistory = [];
  messagesEl.innerHTML = '';
  addMessage('system', 'Chat cleared. Start a new conversation.');
}

// ====== Auto-resize textarea ======

function autoResizeInput() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 80) + 'px';
}

// ====== Event Listeners ======

// Send message
btnSend.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
userInput.addEventListener('input', autoResizeInput);

// Actions
btnClipboard.addEventListener('click', toggleClipboardMonitoring);
btnOCR.addEventListener('click', triggerOCR);
btnClear.addEventListener('click', clearChat);

// Window controls
btnMinimize.addEventListener('click', () => window.api.minimizeWindow());
btnClose.addEventListener('click', () => window.api.closeWindow());
btnPassthrough.addEventListener('click', togglePassthrough);
btnOpacity.addEventListener('click', cycleOpacity);

// Model selector
modelBadge.addEventListener('click', toggleModelSelector);

// Context
clearContext.addEventListener('click', clearCurrentContext);

// ====== Init ======

async function checkOllama() {
  try {
    const models = await window.api.listModels();
    if (models.length > 0) {
      ollamaIndicator.textContent = 'AI: ON';
      ollamaIndicator.classList.add('active');

      // Auto-select first model if current not found
      const found = models.find(m => m.name === currentModel);
      if (!found && models.length > 0) {
        currentModel = models[0].name;
        modelBadge.textContent = currentModel;
      }
    } else {
      ollamaIndicator.textContent = 'AI: OFF';
      ollamaIndicator.classList.add('error');
    }
  } catch (e) {
    ollamaIndicator.textContent = 'AI: OFF';
    ollamaIndicator.classList.add('error');
  }
}

// Check Ollama on startup
checkOllama();

// Focus input
userInput.focus();
