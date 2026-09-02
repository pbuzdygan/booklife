"use strict";

const tableRegion = document.querySelector("[data-table-region]");
const coverRegion = document.querySelector("[data-cover-region]");

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {
      // Booklife stays fully usable online if a browser declines PWA support.
    });
  });
}

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-filter-panel][open]").forEach((panel) => {
    if (!panel.contains(event.target)) panel.open = false;
  });

  const layoutButton = event.target.closest("[data-layout]");
  if (layoutButton && tableRegion && coverRegion) {
    const layout = layoutButton.dataset.layout;
    tableRegion.hidden = layout !== "table";
    coverRegion.hidden = layout !== "covers";
    document.querySelectorAll("[data-layout]").forEach((button) => {
      const active = button.dataset.layout === layout;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  const dismissButton = event.target.closest("[data-dismiss-message]");
  if (dismissButton) dismissMessage(dismissButton.closest(".message"));
});

const dismissMessage = (message) => {
  if (!message || message.dataset.dismissing) return;
  message.dataset.dismissing = "true";
  message.classList.add("is-dismissing");
  window.setTimeout(() => message.remove(), 180);
};

document.querySelectorAll(".message").forEach((message) => {
  window.setTimeout(() => dismissMessage(message), 5000);
});

document.addEventListener("submit", (event) => {
  const confirmation = event.submitter?.dataset.confirm || event.target.dataset.confirm;
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }
  const submitButton = event.submitter;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.setAttribute("aria-busy", "true");
  }
});

document.addEventListener("keydown", (event) => {
  const tag = event.target.tagName;
  const isTyping = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  if (event.key === "/" && !isTyping) {
    const search = document.querySelector("#library-search");
    if (search) {
      event.preventDefault();
      search.focus();
    }
  }
  if (event.key === "Escape") {
    document.querySelectorAll("[data-filter-panel][open]").forEach((panel) => {
      panel.open = false;
    });
  }
});

const isbnFetch = document.querySelector("[data-isbn-fetch]");

if (isbnFetch) {
  const isbnInput = isbnFetch.querySelector("[data-isbn-input]");
  const lookupButton = isbnFetch.querySelector("[data-isbn-lookup]");
  const scanButton = isbnFetch.querySelector("[data-isbn-scan]");
  const status = isbnFetch.querySelector("[data-isbn-status]");
  const result = isbnFetch.querySelector("[data-isbn-result]");
  const resultTitle = isbnFetch.querySelector("[data-isbn-result-title]");
  const resultAuthor = isbnFetch.querySelector("[data-isbn-result-author]");
  const resultSource = isbnFetch.querySelector("[data-isbn-result-source]");
  const resultCover = isbnFetch.querySelector("[data-isbn-result-cover]");
  const scanner = isbnFetch.querySelector("[data-isbn-scanner]");
  const video = isbnFetch.querySelector("[data-isbn-video]");
  const titleInput = document.querySelector("#id_title");
  const authorInput = document.querySelector("#id_author");
  const coverInput = document.querySelector("#id_cover");
  const coverDataInput = document.querySelector("#id_isbn_cover_data");
  let cameraStream = null;
  let scanFrame = null;
  let detector = null;
  let zxingControls = null;
  let zxingReader = null;
  let scannerActive = false;

  const compactISBN = (value) => String(value || "").toUpperCase().replace(/[^0-9X]/g, "");

  const validISBN = (value) => {
    if (/^[0-9]{13}$/.test(value) && (value.startsWith("978") || value.startsWith("979"))) {
      const sum = [...value].reduce((total, character, index) => total + Number(character) * (index % 2 ? 3 : 1), 0);
      return sum % 10 === 0;
    }
    if (/^[0-9]{9}[0-9X]$/.test(value)) {
      const sum = [...value].reduce((total, character, index) => {
        const digit = character === "X" ? 10 : Number(character);
        return total + digit * (10 - index);
      }, 0);
      return sum % 11 === 0;
    }
    return false;
  };

  const setStatus = (message, tone = "") => {
    status.textContent = message;
    status.dataset.tone = tone;
  };

  const stopScanner = () => {
    scannerActive = false;
    if (scanFrame) window.cancelAnimationFrame(scanFrame);
    scanFrame = null;
    if (zxingControls) zxingControls.stop();
    zxingControls = null;
    zxingReader = null;
    if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    video.srcObject = null;
    if (scanner.open) scanner.close();
  };

  const fetchDetails = async () => {
    const isbn = compactISBN(isbnInput.value);
    isbnInput.value = isbn;
    if (!validISBN(isbn)) {
      setStatus("Enter a valid ISBN-10 or a book ISBN-13 beginning with 978 or 979.", "error");
      isbnInput.focus();
      return;
    }

    lookupButton.disabled = true;
    lookupButton.setAttribute("aria-busy", "true");
    setStatus("Looking up this edition…");
    try {
      const url = new URL(isbnFetch.dataset.lookupUrl, window.location.href);
      url.searchParams.set("isbn", isbn);
      const response = await window.fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The lookup could not be completed.");

      isbnInput.value = payload.isbn;
      titleInput.value = payload.title;
      authorInput.value = payload.author || "";
      coverDataInput.value = payload.cover_data_url || "";
      resultTitle.textContent = payload.title;
      resultAuthor.textContent = payload.author || "Author not available";
      resultSource.textContent = payload.source;
      if (payload.cover_data_url) {
        resultCover.src = payload.cover_data_url;
        resultCover.hidden = false;
      } else {
        resultCover.removeAttribute("src");
        resultCover.hidden = true;
      }
      result.hidden = false;
      setStatus(payload.cover_data_url ? "Title, author, and cover are ready. Review them below." : "Title and author are ready. No cover was available.", "success");
      titleInput.focus();
    } catch (error) {
      setStatus(error.message || "The lookup could not be completed.", "error");
    } finally {
      lookupButton.disabled = false;
      lookupButton.removeAttribute("aria-busy");
    }
  };

  const useScannedValue = async (rawValue) => {
    if (!scannerActive) return;
    const match = compactISBN(rawValue);
    if (!validISBN(match)) return;

    isbnInput.value = match;
    stopScanner();
    setStatus(`Book barcode ${match} recognised. Fetching details…`, "success");
    await fetchDetails();
  };

  const inspectVideo = async () => {
    if (!scannerActive || !cameraStream || !detector) return;
    try {
      const barcodes = await detector.detect(video);
      const match = barcodes.map((barcode) => compactISBN(barcode.rawValue)).find(validISBN);
      if (match) {
        await useScannedValue(match);
        return;
      }
    } catch (_error) {
      // Individual video frames may be unreadable while the camera is moving.
    }
    scanFrame = window.requestAnimationFrame(inspectVideo);
  };

  const startNativeScanner = async () => {
    if (!("BarcodeDetector" in window)) return false;

    try {
      const formats = await window.BarcodeDetector.getSupportedFormats();
      if (!formats.includes("ean_13")) return false;
      detector = new window.BarcodeDetector({ formats: ["ean_13"] });
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });
      if (!scannerActive) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
        return true;
      }
      video.srcObject = cameraStream;
      await video.play();
      scanFrame = window.requestAnimationFrame(inspectVideo);
      return true;
    } catch (error) {
      if (error.name === "NotAllowedError" || error.name === "NotFoundError") throw error;
      detector = null;
      if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
      video.srcObject = null;
      return false;
    }
  };

  const startFallbackScanner = async () => {
    if (!window.ZXingBrowser?.BrowserMultiFormatOneDReader) {
      throw new Error("The local barcode scanner could not be loaded. Rebuild Booklife and try again.");
    }

    zxingReader = new window.ZXingBrowser.BrowserMultiFormatOneDReader();
    const controls = await zxingReader.decodeFromConstraints(
      {
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      },
      video,
      (scanResult, _error, controlsForFrame) => {
        if (controlsForFrame) zxingControls = controlsForFrame;
        if (scanResult) useScannedValue(scanResult.getText());
      },
    );
    if (scannerActive) {
      zxingControls = controls;
    } else {
      controls.stop();
    }
  };

  const startScanner = async () => {
    if (!window.isSecureContext) {
      setStatus("Camera scanning requires HTTPS or localhost. Enter the ISBN manually on this connection.", "error");
      isbnInput.focus();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("This browser cannot access a camera. Enter the ISBN manually.", "error");
      isbnInput.focus();
      return;
    }

    try {
      scannerActive = true;
      scanner.showModal();
      const nativeScannerStarted = await startNativeScanner();
      if (!nativeScannerStarted) await startFallbackScanner();
    } catch (error) {
      stopScanner();
      let message = error.message || "The camera scanner could not start.";
      if (error.name === "NotAllowedError") {
        message = "Camera permission was not granted. Enter the ISBN manually or allow camera access.";
      } else if (error.name === "NotFoundError") {
        message = "No camera was found. Enter the ISBN manually.";
      }
      setStatus(message, "error");
    }
  };

  lookupButton.addEventListener("click", fetchDetails);
  scanButton.addEventListener("click", startScanner);
  isbnInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      fetchDetails();
    }
  });
  scanner.querySelectorAll("[data-isbn-scan-close]").forEach((button) => button.addEventListener("click", stopScanner));
  scanner.addEventListener("cancel", (event) => {
    event.preventDefault();
    stopScanner();
  });
  coverInput.addEventListener("change", () => {
    if (coverInput.files.length) coverDataInput.value = "";
  });
  window.addEventListener("pagehide", stopScanner);
}
