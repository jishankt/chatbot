/**
 * Kepler Assistant — Frontend Application Logic
 * Matches Kepler Tech LLC (Dubai) Reference Interface
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const messagesStream = document.getElementById("messages-stream");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const typingIndicator = document.getElementById("typing-indicator");
  const userIdentity = document.getElementById("user-identity");

  // Header controls
  const btnLogin = document.getElementById("btn-login");
  const headerMenuBtn = document.getElementById("header-menu-btn");
  const headerDropdownMenu = document.getElementById("header-dropdown-menu");
  const headerExpandBtn = document.getElementById("header-expand-btn");
  const headerCloseBtn = document.getElementById("header-close-btn");

  const btnOpenInspector = document.getElementById("btn-open-inspector");
  const btnLoadHistory = document.getElementById("btn-load-history");
  const btnExportHistory = document.getElementById("btn-export-history");
  const btnClearChat = document.getElementById("btn-clear-chat");
  const btnCallDesk = document.getElementById("btn-call-desk");

  // Drawer
  const inspectorDrawer = document.getElementById("inspector-drawer");
  const drawerCloseBtn = document.getElementById("drawer-close-btn");
  const btnResetUser = document.getElementById("btn-reset-user");

  // Telemetry
  const telemetryIntent = document.getElementById("telemetry-intent");
  const telemetryPriority = document.getElementById("telemetry-priority");
  const telemetryLatency = document.getElementById("telemetry-latency");
  const telemetryTools = document.getElementById("telemetry-tools");
  const rawJsonPre = document.getElementById("raw-json-pre");
  const btnRefreshLeads = document.getElementById("btn-refresh-leads");
  const leadsTbody = document.getElementById("leads-tbody");

  // Channel
  let currentChannel = "web";
  const channelWebBtn = document.getElementById("channel-web");
  const channelWaBtn = document.getElementById("channel-wa");

  // Emoji
  const btnEmoji = document.getElementById("btn-emoji");
  const toastContainer = document.getElementById("toast-container");

  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    const iconSpan = document.createElement("span");
    iconSpan.textContent = "💬 ";
    const textSpan = document.createElement("span");
    textSpan.textContent = message;
    toast.appendChild(iconSpan);
    toast.appendChild(textSpan);
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 2800);
  }

  // Header Menu Toggle
  if (headerMenuBtn) {
    headerMenuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      headerDropdownMenu.classList.toggle("active");
    });
  }

  document.addEventListener("click", () => {
    if (headerDropdownMenu) headerDropdownMenu.classList.remove("active");
  });

  // Drawer Open/Close via Login button or Menu Item
  function toggleDrawer() {
    inspectorDrawer.classList.toggle("open");
    if (inspectorDrawer.classList.contains("open")) {
      fetchLeads();
    }
  }

  if (btnLogin) btnLogin.addEventListener("click", toggleDrawer);
  if (btnOpenInspector) btnOpenInspector.addEventListener("click", toggleDrawer);
  if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", () => inspectorDrawer.classList.remove("open"));

  // Fullscreen / Expand
  if (headerExpandBtn) {
    headerExpandBtn.addEventListener("click", () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        showToast("Fullscreen mode enabled");
      } else {
        document.exitFullscreen().catch(() => {});
        showToast("Fullscreen mode exited");
      }
    });
  }

  // Reset Conversation
  function resetConversation() {
    const msg1 = document.getElementById("initial-msg-1");

    messagesStream.innerHTML = "";
    if (msg1) messagesStream.appendChild(msg1);
    showToast("Conversation view reset");
  }

  if (headerCloseBtn) headerCloseBtn.addEventListener("click", resetConversation);
  if (btnClearChat) btnClearChat.addEventListener("click", resetConversation);

  // Call Desk
  if (btnCallDesk) {
    btnCallDesk.addEventListener("click", () => {
      window.open("tel:0097143231008");
    });
  }

  // Channel toggles inside drawer
  if (channelWebBtn && channelWaBtn) {
    channelWebBtn.addEventListener("click", () => {
      currentChannel = "web";
      channelWebBtn.classList.add("active");
      channelWaBtn.classList.remove("active");
      showToast("Switched to Web Widget API");
    });

    channelWaBtn.addEventListener("click", () => {
      currentChannel = "whatsapp";
      channelWaBtn.classList.add("active");
      channelWebBtn.classList.remove("active");
      showToast("Simulating WhatsApp Cloud Channel");
    });
  }

  // Reset Customer Phone
  if (btnResetUser) {
    btnResetUser.addEventListener("click", () => {
      const randomSuffix = Math.floor(1000 + Math.random() * 9000);
      userIdentity.value = `+97150${randomSuffix}89`;
      resetConversation();
      showToast(`New Customer ID: ${userIdentity.value}`);
    });
  }

  // Format Markdown
  function formatMarkdown(text) {
    if (!text) return "";
    // Normalize pre-escaped entities from backend to prevent double-escaping
    let unescaped = text
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");

    let formatted = unescaped
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Bold **text** or *text*
    formatted = formatted.replace(/\*\*([^\*]+)\*\*/g, "<strong>$1</strong>");
    formatted = formatted.replace(/\*([^\*]+)\*/g, "<strong>$1</strong>");

    // Line breaks
    formatted = formatted.replace(/\n/g, "<br>");

    // Links (sanitized to http/https only)
    formatted = formatted.replace(
      /(https?:\/\/[^\s<"']+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    return formatted;
  }

  // Append Message
  function appendMessage(role, text, metadata = {}) {
    const row = document.createElement("div");

    if (role === "user") {
      row.className = "message-row user-row";
      const bubble = document.createElement("div");
      bubble.className = "message-bubble user-bubble";
      bubble.textContent = text; // Safe textContent prevents XSS entirely
      row.appendChild(bubble);
    } else {
      row.className = "message-row bot-row";

      const isProductSpecialist = metadata.role === "specialist" || metadata.intent !== "greeting";

      let bubbleHtml = `
        <div class="bot-msg-avatar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0066FF" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
        </div>
        <div class="message-bubble bot-bubble ${isProductSpecialist ? 'product-specialist-bubble' : 'front-desk-bubble'}">
          <div class="bubble-role-tag ${isProductSpecialist ? 'product-specialist-tag' : 'front-desk-tag'}">
            <span class="badge-dot ${isProductSpecialist ? 'blue-dot' : 'green-dot'}">●</span> ${isProductSpecialist ? 'Product Specialist' : '🌿 Front Desk'}
          </div>
          <div class="bubble-text">${formatMarkdown(text)}</div>
      `;

      // Render Matched Cards if present
      if (metadata.cards && metadata.cards.length > 0) {
        const isCarousel = metadata.cards.length > 1;
        bubbleHtml += `<div class="${isCarousel ? 'cards-carousel-container' : 'single-card-wrap'}">`;
        
        metadata.cards.forEach(card => {
          bubbleHtml += `
            <div class="product-match-card">
              <div class="card-img-box">
                <img src="${card.image_url}" alt="${card.title}" onerror="this.src='/static/img/citizen_cx02_card.webp'">
              </div>
              <div class="card-badge-row">
                <span class="card-badge">${card.badge || 'Hardware'}</span>
              </div>
              <div class="card-title">${card.title}</div>
              <div class="card-price-line">${card.price_subtext || card.price_display}</div>
              <div class="card-rec-line">
                <span class="card-rec-check">✓</span>
                <span>${card.recommendation || 'Primary recommendation matching your specifications.'}</span>
              </div>
              <div class="card-divider"></div>
              <a href="${card.url}" target="_blank" rel="noopener noreferrer" class="card-btn-primary">
                View Details ↗
              </a>
              <button class="card-btn-compare" data-compare-query="${card.compare_query || ('Compare ' + card.title)}">
                <span>▢</span> Compare
              </button>
            </div>
          `;
        });
        bubbleHtml += `</div>`;
      }

      bubbleHtml += `</div>`;
      row.innerHTML = bubbleHtml;
    }

    messagesStream.appendChild(row);
    messagesStream.scrollTop = messagesStream.scrollHeight;
  }

  function showTyping() {
    typingIndicator.style.display = "inline-flex";
    messagesStream.scrollTop = messagesStream.scrollHeight;
  }

  function hideTyping() {
    typingIndicator.style.display = "none";
  }

  // Send Message Logic
  async function sendMessage(textToSend) {
    const text = textToSend || chatInput.value.trim();
    if (!text) return;

    chatInput.value = "";
    appendMessage("user", text);
    showTyping();

    const senderPhone = userIdentity ? userIdentity.value.trim() : "+971501234567";

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          sender_id: senderPhone,
          phone: senderPhone,
          channel: currentChannel
        })
      });

      const data = await response.json();
      hideTyping();

      if (response.ok) {
        appendMessage("bot", data.reply, data);
        updateTelemetry(data);
      } else {
        appendMessage("bot", `⚠️ Error (${response.status}): ${data.error || "Could not process message."}`, { role: "specialist" });
      }
    } catch (err) {
      hideTyping();
      appendMessage("bot", "⚠️ Network connection error. Please ensure server is running.", { role: "specialist" });
      console.error(err);
    }
  }

  function updateTelemetry(data) {
    if (telemetryIntent) telemetryIntent.textContent = data.intent || "—";
    if (telemetryPriority) telemetryPriority.textContent = data.priority !== undefined ? `P${data.priority}` : "—";
    if (telemetryLatency) telemetryLatency.textContent = data.latency_ms ? `${data.latency_ms} ms` : "—";
    
    if (telemetryTools) {
      const toolNames = (data.tools_called || []).map(t => t.tool || t.name || JSON.stringify(t)).join(", ");
      telemetryTools.textContent = toolNames || "None (Extractive/Rule)";
    }

    if (rawJsonPre) {
      rawJsonPre.textContent = JSON.stringify(data, null, 2);
    }
  }

  // Send Handlers
  sendBtn.addEventListener("click", () => sendMessage());

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Delegated Clicks: Quick Options, Test Chips, Compare Buttons
  document.addEventListener("click", (e) => {
    const optionPill = e.target.closest(".option-pill");
    if (optionPill) {
      const prompt = optionPill.getAttribute("data-prompt");
      if (prompt) sendMessage(prompt);
      return;
    }

    const testChip = e.target.closest(".test-chip");
    if (testChip) {
      const prompt = testChip.getAttribute("data-prompt");
      if (prompt) sendMessage(prompt);
      return;
    }

    const compareBtn = e.target.closest(".card-btn-compare");
    if (compareBtn) {
      const compareQuery = compareBtn.getAttribute("data-compare-query");
      if (compareQuery) sendMessage(compareQuery);
      return;
    }
  });

  // Emoji helper
  if (btnEmoji) {
    btnEmoji.addEventListener("click", () => {
      const emojis = ["📸", "🖨️", "💰", "⚡", "🤝", "📦", "✅"];
      const pick = emojis[Math.floor(Math.random() * emojis.length)];
      chatInput.value += pick + " ";
      chatInput.focus();
    });
  }

  // Load Past History
  async function loadChatHistory(senderPhone) {
    if (!senderPhone) return;
    try {
      const res = await fetch(`/history?sender_id=${encodeURIComponent(senderPhone)}&limit=30`);
      if (!res.ok) return;
      const data = await res.json();
      const msgs = data.messages || [];
      if (msgs.length > 0) {
        resetConversation();
        msgs.forEach(m => {
          appendMessage(m.role, m.content, { timestamp: m.timestamp });
        });
        showToast(`Loaded ${msgs.length} prior messages`);
      }
    } catch (e) {
      console.warn("Could not load history:", e);
    }
  }

  if (btnLoadHistory) {
    btnLoadHistory.addEventListener("click", () => {
      loadChatHistory(userIdentity.value.trim());
    });
  }

  // Export History
  if (btnExportHistory) {
    btnExportHistory.addEventListener("click", async () => {
      try {
        const senderPhone = userIdentity.value.trim();
        const res = await fetch(`/history/export?sender_id=${encodeURIComponent(senderPhone)}`);
        if (!res.ok) throw new Error("Export failed");
        const text = await res.text();
        const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `chat_history_${senderPhone.replace(/\+/g, "")}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast("Conversation exported (.md)");
      } catch (e) {
        showToast("Error exporting history");
      }
    });
  }

  // Fetch Leads for Drawer
  async function fetchLeads() {
    if (!leadsTbody) return;
    leadsTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">Loading leads...</td></tr>';
    try {
      const res = await fetch("/leads", {
        headers: { "Authorization": "Bearer kepler_admin_secret_key_2026" }
      });
      if (!res.ok) throw new Error("Auth failed");
      const data = await res.json();
      const leads = data.leads || [];

      if (leads.length === 0) {
        leadsTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">No registered leads yet.</td></tr>';
        return;
      }

      leadsTbody.innerHTML = leads.map(l => `
        <tr>
          <td><strong>${l.name || "Anonymous"}</strong></td>
          <td>${l.phone || "—"}</td>
          <td><span style="color:#10B981;">${l.status || "new"}</span></td>
          <td style="color:#94a3b8; font-size:0.68rem;">${(l.created_at || "").slice(0, 16)}</td>
        </tr>
      `).join("");
    } catch (err) {
      leadsTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#F43F5E;">Could not fetch leads (auth required).</td></tr>';
    }
  }

  if (btnRefreshLeads) btnRefreshLeads.addEventListener("click", fetchLeads);
});
