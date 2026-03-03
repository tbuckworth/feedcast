document.addEventListener("DOMContentLoaded", async () => {
  const urlEl = document.getElementById("url");
  const modeEl = document.getElementById("mode");
  const sendBtn = document.getElementById("send");
  const statusEl = document.getElementById("status");
  const contentEl = document.getElementById("content");
  const setupEl = document.getElementById("setup");

  // Load settings
  const settings = await chrome.storage.sync.get(["workerUrl", "token"]);
  if (!settings.workerUrl || !settings.token) {
    contentEl.style.display = "none";
    setupEl.style.display = "block";
    document.getElementById("openOptions").addEventListener("click", () => {
      chrome.runtime.openOptionsPage();
    });
    return;
  }

  // Get current tab URL
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const pageUrl = tab?.url || "";
  urlEl.textContent = pageUrl;

  sendBtn.addEventListener("click", async () => {
    sendBtn.disabled = true;
    sendBtn.textContent = "Sending...";
    statusEl.className = "status";
    statusEl.style.display = "none";

    try {
      const resp = await fetch(settings.workerUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${settings.token}`,
        },
        body: JSON.stringify({
          url: pageUrl,
          mode: modeEl.value,
        }),
      });

      const data = await resp.json();

      if (resp.ok) {
        statusEl.className = "status success";
        statusEl.textContent = "Queued! You'll get a notification when it's ready.";
      } else {
        statusEl.className = "status error";
        statusEl.textContent = data.error || `Error: ${resp.status}`;
      }
    } catch (err) {
      statusEl.className = "status error";
      statusEl.textContent = `Network error: ${err.message}`;
    }

    statusEl.style.display = "block";
    sendBtn.disabled = false;
    sendBtn.textContent = "Send to Podcast";
  });
});
