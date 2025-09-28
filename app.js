// =====================
// S Y L L A B A I — app.js
// =====================

// ------- Theme boot (default to light, remember choice) -------
(() => {
    const KEY = "theme";
    const root = document.documentElement;
    const saved = localStorage.getItem(KEY);
    root.setAttribute("data-theme", saved || "light");
  
    const btn = document.querySelector(".theme-toggle");
    if (btn) {
      const syncPressed = () =>
        btn.setAttribute("aria-pressed", String(root.getAttribute("data-theme") === "light"));
      syncPressed();
  
      btn.addEventListener("click", () => {
        const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        root.setAttribute("data-theme", next);
        localStorage.setItem(KEY, next);
        syncPressed();
      });
    }
  })();
  
  // ------- Chat wiring -------
  const API_URL = "http://127.0.0.1:8000/api/chat"; // FastAPI proxy
  const SYSTEM  = "You are a Virginia Tech Course Advisor. Be concise.";
  
  const form     = document.getElementById("searchForm");
  const input    = document.getElementById("q");
  const messages = document.getElementById("messages");   // chat container
  const output   = document.getElementById("answer");     // optional fallback
  
  // Start in pre-query state; keep transitions OFF until the first submit
  document.body.classList.remove("query-mode");
  document.body.classList.add("jump-bar");
  
  // Move layout into "query mode" and let CSS animate the search bar
  function enterQueryMode(){
    const b = document.body;
    b.classList.remove("jump-bar");  // enable transitions
    void b.offsetHeight;             // force reflow so the browser commits the pre-state
    b.classList.add("query-mode");   // triggers your CSS animation
  }
  
  function scrollToBottom(){
    if (messages) messages.scrollTop = messages.scrollHeight;
  }
  
  // Add a message node
  function addMsg(text, who){
    if (messages) {
      const div = document.createElement("div");
      div.className = `msg ${who}`;
      div.textContent = text;
      messages.appendChild(div);
      scrollToBottom();
      return div;
    } else if (output) {
      output.textContent = text;
      return output;
    }
    return null;
  }
  
  // Typewriter for bot replies (uses your .msg.bot.typing caret)
  async function typeBotReply(text, speed = 14){
    const node = addMsg("", "bot");
    if (!node) return;
    node.classList.add("typing");
  
    // Stream characters
    for (let i = 0; i < text.length; i++){
      node.textContent += text[i];
      scrollToBottom();
      await new Promise(r => setTimeout(r, speed));
    }
  
    node.classList.remove("typing");
  }
  
  // Call your FastAPI → Databricks endpoint
  async function askLLM(prompt){
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, system: SYSTEM, temperature: 0.2 })
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`API ${resp.status}: ${text.slice(0,200)}`);
    }
    const data = await resp.json();
    return data.reply || "(No reply)";
  }
  
  // Submit handler
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const prompt = (input?.value || "").trim();
      if (!prompt) return;
  
      // Animate layout on first submit
      enterQueryMode();
      
      // User bubble
      addMsg(prompt, "user");
      if (input) input.value = "";
  
      // Disable send while we wait
      const sendBtn = form.querySelector(".send");
      if (sendBtn) sendBtn.disabled = true;
  
      try {
        const reply = await askLLM(prompt);
        await typeBotReply(reply); // typed-out bot response
      } catch (err) {
        console.error(err);
        addMsg("Error: " + err.message, "bot");
      } finally {
        if (sendBtn) sendBtn.disabled = false;
        if (input) input.focus();
      }
    });
  }
  