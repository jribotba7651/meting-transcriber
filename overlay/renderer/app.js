// ═══ State ══════════════════════════════════════════════════
let chatHistory = [];          // {role, content}[] for Ollama
let currentStreamText = '';    // Accumulator for streaming response
let isStreaming = false;
let clipboardContext = null;   // Pending clipboard/OCR context
let config = null;
let opacityLevels = [0.95, 0.70, 0.40, 0.20];
let currentOpacityIdx = 0;

// ═══ DOM Elements ══════════════════════════════════════════
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const btnSend = document.getElementById('btn-send');
const btnOCR = document.getElementById('btn-ocr');
const btnPaste = document.getElementById('btn-paste');
const btnClear = document.getElementById('btn-clear');
const btnOpacity = document.getElementById('btn-opacity');
const btnClickThrough = document.getElementById('btn-clickthrough');
const btnMinimize = document.getElementById('btn-minimize');
const ollamaStatus = document.getElementById('ollama-status');
const clipboardIndicator = document.getElementById('clipboard-indicator');
const contextPreview = document.getElementById('context-preview');
const contextText = document.getElementById('context-text');
const btnClearContext = document.getElementById('btn-clear-context');
const modelLabel = document.getElementById('model-label');
const welcomeMsg = document.getElementById('welcome-msg');

// ═══ Init ══════════════════════════════════════════════════
async function init() {
  config = await window.api.getConfig();
  modelLabel.textContent = config.ollama.model;

  // Load chat history
  const saved = await window.api.loadHistory();
  if (saved && saved.length > 0) {
    chatHistory = saved;
    welcomeMsg.style.display = 'none';
    chatHistory.forEach(msg => {
      if (msg.role === 'user') renderUserMessage(msg.content);
      else if (msg.role === 'assistant') renderAssistantMessage(msg.content);
    });
    scrollToBottom(true);
  }

  // Check Ollama
  checkOllamaHealth();
  setInterval(checkOllamaHealth, 15000);

  // Setup listeners
  setupEventListeners();
  setupIPCListeners();
}

// ═══ Ollama Health ═════════════════════════════════════════
async function checkOllamaHealth() {
  const result = await window.api.checkOllama();
  if (result.connected) {
    ollamaStatus.textContent = '● Connected';
    ollamaStatus.className = 'status-connected';
    if (result.models && result.models.length > 0) {
      ollamaStatus.title = 'Models: ' + result.models.join(', ');
    }
  } else {
    ollamaStatus.textContent = '● Disconnected';
    ollamaStatus.className = 'status-disconnected';
    ollamaStatus.title = result.error || 'Cannot connect to Ollama';
  }
}

// ═══ Event Listeners ═══════════════════════════════════════
function setupEventListeners() {
  // Send message
  btnSend.addEventListener('click', sendMessage);
  messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    if (e.key === 'Escape' && isStreaming) {
      window.api.stopGeneration();
    }
  });

  // Auto-resize textarea
  messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
  });

  // OCR button
  btnOCR.addEventListener('click', async () => {
    btnOCR.disabled = true;
    btnOCR.textContent = '⏳ Capturing...';
    const result = await window.api.captureOCR();
    if (result.success) {
      setContext('[OCR] ' + result.text);
    } else {
      showSystemMessage('OCR Error: ' + result.error);
    }
    btnOCR.textContent = '📷 OCR';
    btnOCR.disabled = false;
  });

  // Paste clipboard button
  btnPaste.addEventListener('click', async () => {
    const text = await window.api.readClipboard();
    if (text) {
      setContext('[Clipboard] ' + text);
    } else {
      showSystemMessage('Clipboard is empty.');
    }
  });

  // Clear chat
  btnClear.addEventListener('click', () => {
    chatHistory = [];
    chatContainer.innerHTML = '';
    welcomeMsg.style.display = 'block';
    chatContainer.appendChild(welcomeMsg);
    window.api.saveHistory([]);
    clearContext();
  });

  // Opacity cycle
  btnOpacity.addEventListener('click', () => {
    currentOpacityIdx = (currentOpacityIdx + 1) % opacityLevels.length;
    const opacity = opacityLevels[currentOpacityIdx];
    window.api.setOpacity(opacity);
    btnOpacity.title = `Opacity: ${Math.round(opacity * 100)}%`;
  });

  // Click-through toggle
  let clickThrough = false;
  btnClickThrough.addEventListener('click', () => {
    clickThrough = !clickThrough;
    window.api.setClickThrough(clickThrough);
    btnClickThrough.style.color = clickThrough ? '#4ade80' : '';
  });

  // Minimize
  btnMinimize.addEventListener('click', () => {
    window.api.hideWindow();
  });

  // Clear context
  btnClearContext.addEventListener('click', clearContext);
}

// ═══ IPC Listeners ═════════════════════════════════════════
function setupIPCListeners() {
  // Streaming tokens
  window.api.onChatToken((token) => {
    currentStreamText += token;
    updateStreamingMessage(currentStreamText);
  });

  // Stream done
  window.api.onChatDone((stats) => {
    isStreaming = false;
    btnSend.disabled = false;
    btnSend.textContent = '▶';
    messageInput.disabled = false;
    messageInput.focus();

    // Remove streaming cursor
    const streamingEl = chatContainer.querySelector('.streaming-cursor');
    if (streamingEl) streamingEl.classList.remove('streaming-cursor');

    // Save to history
    if (currentStreamText) {
      chatHistory.push({ role: 'assistant', content: currentStreamText });
      window.api.saveHistory(chatHistory);
    }
    currentStreamText = '';
  });

  // Stream error
  window.api.onChatError((error) => {
    isStreaming = false;
    btnSend.disabled = false;
    btnSend.textContent = '▶';
    messageInput.disabled = false;

    // Remove streaming message if empty
    const streamingEl = chatContainer.querySelector('.streaming-cursor');
    if (streamingEl && !currentStreamText) {
      streamingEl.parentElement.remove();
    } else if (streamingEl) {
      streamingEl.classList.remove('streaming-cursor');
    }

    showSystemMessage('Error: ' + error);
    currentStreamText = '';
  });

  // Clipboard change from monitor
  window.api.onClipboardChange((text) => {
    clipboardIndicator.classList.remove('hidden');
    clipboardIndicator.textContent = `📋 ${text.length} chars`;
    setTimeout(() => clipboardIndicator.classList.add('hidden'), 3000);
  });

  // OCR result from global hotkey
  window.api.onOCRResult((text) => {
    if (text.startsWith('[OCR Error]')) {
      showSystemMessage(text);
    } else {
      setContext('[OCR] ' + text);
    }
  });
}

// ═══ Send Message ══════════════════════════════════════════
function sendMessage() {
  let text = messageInput.value.trim();
  if (!text || isStreaming) return;

  // Attach context if present
  let fullMessage = text;
  if (clipboardContext) {
    fullMessage = `Context:\n${clipboardContext}\n\nQuestion: ${text}`;
    renderContextMessage(clipboardContext);
    clearContext();
  }

  // Clear input
  messageInput.value = '';
  messageInput.style.height = 'auto';
  welcomeMsg.style.display = 'none';

  // Render user message
  renderUserMessage(text);

  // Add to history
  chatHistory.push({ role: 'user', content: fullMessage });

  // Start streaming
  isStreaming = true;
  currentStreamText = '';
  btnSend.disabled = true;
  btnSend.textContent = '⏹';
  messageInput.disabled = true;

  // Create empty assistant message
  createStreamingMessage();

  // Send to Ollama
  window.api.sendMessage(chatHistory, config.ollama.model);
}

// ═══ Context Management ════════════════════════════════════
function setContext(text) {
  clipboardContext = text;
  contextText.textContent = text.length > 100 ? text.substring(0, 100) + '...' : text;
  contextPreview.classList.remove('hidden');
  messageInput.focus();
}

function clearContext() {
  clipboardContext = null;
  contextPreview.classList.add('hidden');
  contextText.textContent = '';
}

// ═══ Message Rendering ═════════════════════════════════════
function renderUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message message-user';
  div.textContent = text;
  chatContainer.appendChild(div);
  scrollToBottom();
}

function renderAssistantMessage(markdown) {
  const div = document.createElement('div');
  div.className = 'message message-assistant';
  const content = document.createElement('div');
  content.className = 'message-content';
  content.innerHTML = renderMarkdown(markdown);
  div.appendChild(content);
  chatContainer.appendChild(div);
  attachCopyButtons(div);
  scrollToBottom();
}

function renderContextMessage(text) {
  const div = document.createElement('div');
  div.className = 'message message-context';
  div.textContent = '📎 ' + (text.length > 200 ? text.substring(0, 200) + '...' : text);
  chatContainer.appendChild(div);
}

function showSystemMessage(text) {
  const div = document.createElement('div');
  div.className = 'system-message';
  div.textContent = text;
  chatContainer.appendChild(div);
  scrollToBottom();
}

function createStreamingMessage() {
  const div = document.createElement('div');
  div.className = 'message message-assistant';
  div.id = 'streaming-msg';
  const content = document.createElement('div');
  content.className = 'message-content streaming-cursor';
  div.appendChild(content);
  chatContainer.appendChild(div);
  scrollToBottom();
}

// Debounced streaming update
let renderTimeout = null;
function updateStreamingMessage(text) {
  clearTimeout(renderTimeout);
  renderTimeout = setTimeout(() => {
    const msg = document.getElementById('streaming-msg');
    if (!msg) return;
    const content = msg.querySelector('.message-content');
    content.innerHTML = renderMarkdown(text);
    content.classList.add('streaming-cursor');
    attachCopyButtons(msg);
    scrollToBottom();
  }, 40);
}

// ═══ Auto-scroll ═══════════════════════════════════════════
function scrollToBottom(force = false) {
  const el = chatContainer;
  const isNearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 60;
  if (force || isNearBottom) {
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }
}

// ═══ Markdown Renderer ═════════════════════════════════════
function renderMarkdown(text) {
  if (!text) return '';

  // Escape HTML
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks with language
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang ? `<div class="code-header"><span class="code-lang">${lang}</span><button class="code-copy-btn" onclick="copyCode(this)">Copy</button></div>` : '';
    const preClass = lang ? ' class="has-header"' : '';
    return `${langLabel}<pre${preClass}><code>${code.trimEnd()}</code></pre>`;
  });

  // Inline code (avoid matching inside code blocks)
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Blockquote
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // Unordered lists
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, '</p><p>');

  // Single newlines to <br>
  html = html.replace(/\n/g, '<br>');

  // Wrap in paragraph if not starting with a block element
  if (!html.startsWith('<h') && !html.startsWith('<ul') && !html.startsWith('<ol') && !html.startsWith('<pre') && !html.startsWith('<blockquote')) {
    html = '<p>' + html + '</p>';
  }

  return html;
}

// ═══ Code Copy ═════════════════════════════════════════════
function copyCode(btn) {
  const pre = btn.closest('.code-header')
    ? btn.closest('.code-header').nextElementSibling
    : btn.closest('pre');
  const code = pre ? pre.querySelector('code') : null;
  if (code) {
    navigator.clipboard.writeText(code.textContent).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 2000);
    });
  }
}

// Make copyCode available globally for inline onclick
window.copyCode = copyCode;

function attachCopyButtons(container) {
  // Add copy buttons to code blocks that don't have headers
  container.querySelectorAll('pre:not(.has-header)').forEach(pre => {
    if (pre.querySelector('.code-copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'code-copy-btn';
    btn.textContent = 'Copy';
    btn.style.position = 'absolute';
    btn.style.top = '4px';
    btn.style.right = '4px';
    btn.addEventListener('click', () => copyCode(btn));
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
}

// ═══ Start App ═════════════════════════════════════════════
init();
