// State
let chatHistory = [];
let currentModel = 'llama3.2';
let isStreaming = false;
let clipboardMonitoring = false;
let currentContext = '';
let systemPrompt = '';
let saveDebounce = null;

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

// ====== Markdown Rendering ======

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMessage(text) {
  // Process code blocks first (protect them from other replacements)
  const codeBlocks = [];
  let processed = text.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang, code: code.trimEnd() });
    return `%%CODEBLOCK_${idx}%%`;
  });

  // Inline code (protect from other replacements)
  const inlineCodes = [];
  processed = processed.replace(/`([^`]+)`/g, (match, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(code);
    return `%%INLINE_${idx}%%`;
  });

  // Bold
  processed = processed.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  processed = processed.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Strikethrough
  processed = processed.replace(/~~(.+?)~~/g, '<del>$1</del>');
  // Headers (## Header)
  processed = processed.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  processed = processed.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  processed = processed.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  // Bullet lists
  processed = processed.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
  processed = processed.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Numbered lists
  processed = processed.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Links
  processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  // Line breaks (but not inside block elements)
  processed = processed.replace(/\n/g, '<br>');

  // Restore inline code
  inlineCodes.forEach((code, idx) => {
    processed = processed.replace(`%%INLINE_${idx}%%`, `<code>${escapeHtml(code)}</code>`);
  });

  // Restore code blocks with copy button
  codeBlocks.forEach((block, idx) => {
    const langLabel = block.lang ? `<span class="code-lang">${block.lang}</span>` : '';
    const copyBtn = `<button class="copy-btn" onclick="copyCode(this)" title="Copy code">Copy</button>`;
    const html = `<div class="code-block">${langLabel}${copyBtn}<pre><code>${escapeHtml(block.code)}</code></pre></div>`;
    processed = processed.replace(`%%CODEBLOCK_${idx}%%`, html);
  });

  return processed;
}

// Global function for copy button onclick
window.copyCode = function(btn) {
  const code = btn.parentElement.querySelector('code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 1500);
  });
};

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

function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ====== Persistence ======

function debounceSaveHistory() {
  if (saveDebounce) clearTimeout(saveDebounce);
  saveDebounce = setTimeout(() => {
    window.api.saveHistory(chatHistory);
  }, 1000);
}

async function loadPersistedHistory() {
  try {
    const history = await window.api.loadHistory();
    if (history && history.length > 0) {
      chatHistory = history;
      // Render persisted messages (skip system prompt)
      for (const msg of history) {
        if (msg.role === 'system') continue;
        addMessage(msg.role, msg.content);
      }
    }
  } catch (e) {
    // No history, start fresh
  }
}

// ====== Send Message ======

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

  // Add system prompt at the start of conversation if configured
  const messagesForAI = [];
  if (systemPrompt && chatHistory.length === 0) {
    messagesForAI.push({ role: 'system', content: systemPrompt });
  }

  chatHistory.push({ role: 'user', content: fullMessage });
  messagesForAI.push(...chatHistory);

  isStreaming = true;
  btnSend.disabled = true;
  statusText.textContent = 'Thinking...';

  const streamMsg = addStreamingMessage();

  try {
    // Use streaming - the handler in main.js sends chunks via events
    window.api.chatStream(
      systemPrompt
        ? [{ role: 'system', content: systemPrompt }, ...chatHistory]
        : chatHistory,
      currentModel
    );
    streamMsg.innerHTML = '';
  } catch (err) {
    streamMsg.innerHTML = `<span class="error-text">Error: ${err.message}</span>`;
    finishStreaming();
  }
}

function finishStreaming() {
  isStreaming = false;
  btnSend.disabled = false;
  statusText.textContent = 'Ready';
}

// ====== Stream Event Handlers ======

window.api.onStreamChunk((chunk) => {
  const streamMsg = document.querySelector('#streaming-message .message-content');
  if (streamMsg) {
    const typingIndicator = streamMsg.querySelector('.typing-indicator');
    if (typingIndicator) typingIndicator.remove();

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
    debounceSaveHistory();
  }

  const streamEl = document.getElementById('streaming-message');
  if (streamEl) streamEl.removeAttribute('id');

  finishStreaming();
});

window.api.onStreamError((err) => {
  const streamMsg = document.querySelector('#streaming-message .message-content');
  if (streamMsg) {
    streamMsg.innerHTML = `<span class="error-text">Error: ${err}</span>`;
  }

  const streamEl = document.getElementById('streaming-message');
  if (streamEl) streamEl.removeAttribute('id');

  // Remove the failed user message from history so they can retry
  if (chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === 'user') {
    chatHistory.pop();
  }

  finishStreaming();
  statusText.textContent = 'Error - check Ollama';
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

      const sizeMB = m.size ? `${(m.size / 1024 / 1024 / 1024).toFixed(1)}GB` : '';
      div.innerHTML = `<span>${m.name}</span>${sizeMB ? `<span class="model-size">${sizeMB}</span>` : ''}`;

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
  window.api.saveHistory([]);
  messagesEl.innerHTML = '';
  addMessage('system', 'Chat cleared. Start a new conversation.');
}

// History cleared from tray menu
window.api.onHistoryCleared(() => {
  chatHistory = [];
  messagesEl.innerHTML = '';
  addMessage('system', 'Chat history cleared from system tray.');
});

// ====== Auto-resize textarea ======

function autoResizeInput() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 80) + 'px';
}

// ====== Event Listeners ======

btnSend.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
userInput.addEventListener('input', autoResizeInput);

btnClipboard.addEventListener('click', toggleClipboardMonitoring);
btnOCR.addEventListener('click', triggerOCR);
btnClear.addEventListener('click', clearChat);

btnMinimize.addEventListener('click', () => window.api.minimizeWindow());
btnClose.addEventListener('click', () => window.api.closeWindow());
btnPassthrough.addEventListener('click', togglePassthrough);
btnOpacity.addEventListener('click', cycleOpacity);

modelBadge.addEventListener('click', toggleModelSelector);
clearContext.addEventListener('click', clearCurrentContext);

// ====== Init ======

async function init() {
  // Load config
  try {
    const config = await window.api.getConfig();
    if (config.ollama?.defaultModel) {
      currentModel = config.ollama.defaultModel;
      modelBadge.textContent = currentModel;
    }
    if (config.clipboard?.autoMonitor) {
      toggleClipboardMonitoring();
    }
  } catch (e) {
    // Use defaults
  }

  // Load system prompt
  try {
    systemPrompt = await window.api.getSystemPrompt() || '';
  } catch (e) {
    // No system prompt
  }

  // Load persisted history
  await loadPersistedHistory();

  // Check Ollama connection
  await checkOllama();

  userInput.focus();
}

async function checkOllama() {
  try {
    const models = await window.api.listModels();
    if (models.length > 0) {
      ollamaIndicator.textContent = 'AI: ON';
      ollamaIndicator.classList.add('active');
      ollamaIndicator.classList.remove('error');

      const found = models.find(m => m.name === currentModel);
      if (!found && models.length > 0) {
        currentModel = models[0].name;
        modelBadge.textContent = currentModel;
      }
    } else {
      ollamaIndicator.textContent = 'AI: OFF';
      ollamaIndicator.classList.add('error');
      ollamaIndicator.classList.remove('active');

      addMessage('system', 'Ollama not detected. Install from ollama.ai, then run:\n```\nollama serve\nollama pull llama3.2\n```');
    }
  } catch (e) {
    ollamaIndicator.textContent = 'AI: OFF';
    ollamaIndicator.classList.add('error');
  }
}

init();
