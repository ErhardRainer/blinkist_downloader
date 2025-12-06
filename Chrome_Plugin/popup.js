let currentTabId = null;

function renderBlobs(blobs) {
  const status = document.getElementById("status");
  const list = document.getElementById("list");
  list.innerHTML = "";

  if (!blobs || blobs.length === 0) {
    status.textContent = "Keine blob: Audio-Links gefunden.";
    return;
  }

  status.textContent = blobs.length + " Audio-Blob(s) gefunden. Zum Kopieren oder Download anklicken:";
  blobs.forEach(url => {
    const div = document.createElement("div");
    div.className = "blob-item";
    div.textContent = url;
    div.addEventListener("click", async () => {
      const statusEl = document.getElementById("status");
      try {
        await navigator.clipboard.writeText(url);
        statusEl.textContent = "In Zwischenablage kopiert. Starte Download...";
      } catch (e) {
        statusEl.textContent = "Konnte nicht kopieren. Starte Download...";
      }

      if (currentTabId !== null) {
        chrome.tabs.sendMessage(
          currentTabId,
          { type: "DOWNLOAD_AUDIO_BLOB", url },
          (resp) => {
            // update status based on response and show filename when available
            if (chrome.runtime.lastError) {
              statusEl.textContent = "Fehler: Konnte Nachricht nicht senden.";
            } else if (resp && resp.success) {
              if (resp.filename) {
                statusEl.textContent = `Download gestartet: ${resp.filename}`;
              } else {
                statusEl.textContent = "Download wurde im Tab gestartet.";
              }
            } else if (resp && resp.error) {
              statusEl.textContent = `Download fehlgeschlagen: ${resp.error}`;
            } else {
              statusEl.textContent = "Download-Anfrage gesendet (möglicherweise fehlgeschlagen).";
            }
          }
        );
      } else {
        statusEl.textContent = "Kein Tab gefunden, Download nicht gestartet.";
      }
    });
    list.appendChild(div);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
    currentTabId = tabs[0].id;
    const tabId = currentTabId;

    chrome.scripting.executeScript(
      {
        target: { tabId },
        func: () => window.__audioBlobUrls || []
      },
      results => {
        if (chrome.runtime.lastError) {
          document.getElementById("status").textContent =
            "Fehler beim Zugriff auf die Seite.";
          return;
        }
        const blobs = (results && results[0] && results[0].result) || [];
        renderBlobs(blobs);
      }
    );
  });
});