document.addEventListener("DOMContentLoaded", () => {
  const messagesStream = document.getElementById("messages-stream");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const typingIndicator = document.getElementById("typing-indicator");
  const userIdentity = document.getElementById("user-identity");
  const clearBtn = document.getElementById("clear-btn");
  
  // Telemetry elements
  const telemetryIntent = document.getElementById("telemetry-intent");
  const telemetryPriority = document.getElementById("telemetry-priority");
  const telemetryLatency = document.getElementById("telemetry-latency");
  const telemetryTools = document.getElementById("telemetry-tools");
  const inspectorToolsList = document.getElementById("inspector-tools-list");
  const inspectorChunksList = document.getElementById("inspector-chunks-list");
  const rawJsonPre = document.getElementById("raw-json-pre");

  // Tabs
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  // Channel
  let currentChannel = "web";
  const channelWebBtn = document.getElementById("channel-web");
  const channelWaBtn = document.getElementById("channel-wa");

  channelWebBtn.addEventListener("click", () => {
    currentChannel = "web";
    channelWebBtn.classList.add("active");
    channelWaBtn.classList.remove("active");
    showToast("Channel switched to Web Widget API (/chat)");
  });

  channelWaBtn.addEventListener("click", () => {
    currentChannel = "whatsapp";
    channelWaBtn.classList.add("active");
    channelWebBtn.classList.remove("active");
    showToast("Channel switched to WhatsApp Cloud Simulator");
  });

  // Tab switching
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");

      if (btn.dataset.tab === "tab-leads") {
        fetchLeads();
      }
    });
  });

  // Format message text with simple markdown
  function formatMarkdown(text) {
    if (!text) return "";
    let formatted = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Bold *text*
    formatted = formatted.replace(/\*([^\*]+)\*/g, "<strong>$1</strong>");

    // Links: https://...
    formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');

    return formatted;
  }

  function appendMessage(role, text, metadata = {}) {
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${role}`;

    if (metadata.intent === "guardrails") {
      bubble.classList.add("guardrail-trigger");
    } else if (metadata.intent === "quote") {
      bubble.classList.add("quote-trigger");
    }

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let metaHtml = `<div class="bubble-meta">
      <span>${role === "user" ? (userIdentity.value || "Customer") : "Citizen CX-02 AI"}</span>
      <span>•</span>
      <span>${timeStr}</span>
    </div>`;

    let contentHtml = `<div class="bubble-content">${formatMarkdown(text)}</div>`;
    bubble.innerHTML = metaHtml + contentHtml;

    messagesStream.appendChild(bubble);
    messagesStream.scrollTop = messagesStream.scrollHeight;
  }

  function showTyping() {
    typingIndicator.style.display = "flex";
    messagesStream.scrollTop = messagesStream.scrollHeight;
  }

  function hideTyping() {
    typingIndicator.style.display = "none";
  }

  function showToast(msg) {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `<span>ℹ️</span><span>${msg}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // Send message
  async function sendMessage(textToSend) {
    const text = (textToSend || chatInput.value).trim();
    if (!text) return;

    chatInput.value = "";
    sendBtn.disabled = true;

    appendMessage("user", text);
    showTyping();

    const senderId = userIdentity.value.trim() || "+971501234567";

    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonPayload(text, senderId)
      });

      const data = await res.json();
      hideTyping();

      if (res.ok) {
        appendMessage("assistant", data.reply, { intent: data.intent });
        updateInspector(data);
      } else {
        appendMessage("assistant", "⚠️ Server Error: " + (data.error || "Failed to process request."));
      }
    } catch (err) {
      hideTyping();
      appendMessage("assistant", "⚠️ Network Error: Unable to reach /chat API.");
      console.error(err);
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  function jsonPayload(message, senderId) {
    return JSON.stringify({
      message: message,
      sender_id: senderId,
      phone: senderId.startsWith("+") ? senderId : "+971500000000"
    });
  }

  function updateInspector(data) {
    telemetryIntent.textContent = data.intent || "—";
    telemetryPriority.textContent = data.priority ? `P${data.priority}` : "—";
    telemetryLatency.textContent = data.latency_ms ? `${data.latency_ms} ms` : "—";

    const tools = data.tools_called || [];
    telemetryTools.textContent = `${tools.length} called`;

    // Render tools
    if (tools.length === 0) {
      inspectorToolsList.innerHTML = '<span style="color:var(--text-muted)">No tools invoked.</span>';
    } else {
      inspectorToolsList.innerHTML = tools.map(t => `
        <div class="inspector-detail-box">
          <div class="inspector-detail-title">
            <span>⚙️ ${t.tool}</span>
            <span style="font-size:0.65rem; color:var(--emerald);">SUCCESS</span>
          </div>
          <pre style="font-size:0.72rem; color:var(--text-secondary); overflow-x:auto;">${JSON.stringify(t.args || t.result || {}, null, 2)}</pre>
        </div>
      `).join("");
    }

    // Render raw json
    rawJsonPre.textContent = JSON.stringify(data, null, 2);
  }

  // Preset chips click
  document.querySelectorAll(".test-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const prompt = chip.dataset.prompt;
      if (prompt) {
        sendMessage(prompt);
      }
    });
  });

  // Event listeners
  sendBtn.addEventListener("click", () => sendMessage());
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  clearBtn.addEventListener("click", () => {
    messagesStream.innerHTML = "";
    showToast("Chat session cleared");
  });

  // Direct Quote Form
  const directQuoteBtn = document.getElementById("direct-quote-btn");
  if (directQuoteBtn) {
    directQuoteBtn.addEventListener("click", async () => {
      const sku = document.getElementById("quote-sku-select").value;
      const qty = parseInt(document.getElementById("quote-qty-input").value) || 1;
      const customerName = document.getElementById("quote-customer-input").value || "Valued Customer";

      try {
        const res = await fetch("/quote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            items: [{ sku: sku, qty: qty }],
            customer_name: customerName,
            phone: userIdentity.value || "+971501234567"
          })
        });
        const data = await res.json();
        const quoteResultBox = document.getElementById("quote-result-box");
        quoteResultBox.style.display = "block";
        quoteResultBox.innerHTML = `
          <div style="font-weight:700; color:var(--emerald); margin-bottom:4px;">Quote ${data.quote_id || "Calculated"}</div>
          <div style="font-size:0.75rem; white-space:pre-wrap;">${data.text_summary || JSON.stringify(data, null, 2)}</div>
        `;
        showToast("Quote generated successfully!");
      } catch (err) {
        showToast("Failed to generate quote");
      }
    });
  }

  // Fetch leads
  async function fetchLeads() {
    const tbody = document.getElementById("leads-tbody");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted); text-align:center;">Loading leads...</td></tr>';

    try {
      const res = await fetch("/leads");
      const data = await res.json();
      const leads = data.leads || [];

      if (leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted); text-align:center;">No leads registered yet.</td></tr>';
        return;
      }

      tbody.innerHTML = leads.map(l => `
        <tr>
          <td style="font-weight:600;">${l.name || "Anonymous"}</td>
          <td style="color:var(--cyan);">${l.phone || "—"}</td>
          <td><span style="background:rgba(16,185,129,0.15); color:var(--emerald); padding:2px 6px; border-radius:4px; font-size:0.68rem;">${l.status || "new"}</span></td>
          <td style="color:var(--text-muted); font-size:0.68rem;">${l.created_at ? l.created_at.substring(0, 16) : "—"}</td>
        </tr>
      `).join("");
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--rose); text-align:center;">Failed to load leads</td></tr>';
    }
  }

  // Initial greeting
  appendMessage("assistant", "Hello! Welcome to the **Kepler Tech LLC Citizen CX-02 Sales AI Test Console**.\n\nYou can send custom inquiries or use the test chips below to verify all 14 priority categories, guardrails, pricing, quotes, and technical specs.");

  // Check health on load
  fetch("/health")
    .then(r => r.json())
    .then(data => {
      document.getElementById("catalog-count-badge").textContent = `${data.whitelisted_skus_count} SKUs Active (as of ${data.as_of})`;
    })
    .catch(() => {});
});
