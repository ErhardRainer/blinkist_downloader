(function () {
  function collectAudioBlobs() {
    const audios = Array.from(document.querySelectorAll("audio[src]"));
    const blobs = audios
      .map(a => a.getAttribute("src"))
      .filter(src => src && src.startsWith("blob:"));

    // Duplizierte Einträge entfernen
    const uniqueBlobs = Array.from(new Set(blobs));
    // In der Page-Context global ablegen, damit der Popup-Script zugreifen kann
    window.__audioBlobUrls = uniqueBlobs;
  }

  // Beim Laden und wenn sich der DOM ändert
  collectAudioBlobs();
  const observer = new MutationObserver(() => collectAudioBlobs());
  observer.observe(document.documentElement || document.body, {
    childList: true,
    subtree: true
  });
  
  // Listener für Download-Befehle vom Popup (chrome.tabs.sendMessage)
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || message.type !== "DOWNLOAD_AUDIO_BLOB" || !message.url) {
      return;
    }

    (async () => {
      try {
        const url = message.url;
        // fetch the blob URL available in the page context
        const response = await fetch(url);
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = objectUrl;

        // Determine extension from mime type
        let ext = 'mp3';
        if (blob.type) {
          const mime = blob.type.toLowerCase();
          if (mime.includes('mpeg') || mime.includes('mp3')) ext = 'mp3';
          else if (mime.includes('mp4') || mime.includes('x-m4a') || mime.includes('aac')) ext = 'm4a';
          else if (mime.includes('webm')) ext = 'webm';
          else if (mime.includes('ogg')) ext = 'ogg';
          else if (mime.includes('wav')) ext = 'wav';
        }

        // Format the document title into a nicer filename.
        // Transform patterns like "Title by Author - Blinkist" -> "Author - Title"
        function formatFilenameFromTitle(name) {
          if (!name) return 'blinkist-audio';
          // remove illegal chars first
          let s = name.replace(/[\\/:*?"<>|]/g, '')
                      .replace(/\s+/g, ' ')
                      .trim();
          s = s.replace(/\.+$/g, '');
          // remove common site suffix like "- Blinkist" or "| Blinkist"
          s = s.replace(/\s*[-|]\s*Blinkist$/i, '').trim();

          // If title contains " by ", assume format "Title by Author" and swap
          const byMatch = s.match(/^(.*)\s+by\s+(.*)$/i);
          if (byMatch) {
            const titlePart = byMatch[1].trim();
            const authorPart = byMatch[2].trim();
            // remove any trailing site markers from author (e.g. "- Blinkist")
            const author = authorPart.replace(/\s*[-|].*$/,'').trim();
            s = `${author} - ${titlePart}`;
          }

          // fallback limits and cleanup
          if (!s) s = 'blinkist-audio';
          if (s.length > 180) s = s.slice(0, 180).trim();
          // keep spaces (user prefers spaces), but collapse multiple spaces
          s = s.replace(/\s+/g, ' ');
          return s;
        }

        const title = formatFilenameFromTitle(document.title || 'blinkist-audio');
        const filename = `${title}.${ext}`;

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // cleanup
        setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
        sendResponse && sendResponse({ success: true, filename });
      } catch (err) {
        console.error('Download fehlgeschlagen', err);
        sendResponse && sendResponse({ success: false, error: err && err.message });
      }
    })();

    // indicate async response
    return true;
  });
})();