document.addEventListener("DOMContentLoaded", async () => {
  const workerUrlEl = document.getElementById("workerUrl");
  const tokenEl = document.getElementById("token");
  const saveBtn = document.getElementById("save");
  const savedEl = document.getElementById("saved");

  // Load existing settings
  const settings = await chrome.storage.sync.get(["workerUrl", "token"]);
  if (settings.workerUrl) workerUrlEl.value = settings.workerUrl;
  if (settings.token) tokenEl.value = settings.token;

  saveBtn.addEventListener("click", async () => {
    await chrome.storage.sync.set({
      workerUrl: workerUrlEl.value.trim(),
      token: tokenEl.value.trim(),
    });
    savedEl.style.display = "inline";
    setTimeout(() => { savedEl.style.display = "none"; }, 2000);
  });
});
