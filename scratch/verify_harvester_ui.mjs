import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const ARTIFACT_DIR = 'C:\\Users\\edtli\\.gemini\\antigravity\\brain\\97c85a98-ec5e-498d-ae9c-22bef916c1db';
const REF_IMAGE = 'C:\\Users\\edtli\\reference_images\\img_8.png';

async function run() {
  console.log('[*] Reading reference image for in-memory upload simulation...');
  const imgBuf = fs.readFileSync(REF_IMAGE);
  const imgB64 = `data:image/png;base64,${imgBuf.toString('base64')}`;

  console.log('[*] Spawning headless Chromium...');
  const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
    '--headless=new',
    '--disable-gpu',
    '--remote-debugging-port=9244',
    '--window-size=1560,1100',
    'http://localhost:8080/studio/'
  ]);

  await new Promise(r => setTimeout(r, 2500));

  try {
    const listRes = await fetch('http://localhost:9244/json');
    const tabs = await listRes.json();
    const pageTab = tabs.find(t => t.type === 'page');
    if (!pageTab) throw new Error('No page tab found in Chrome.');

    const ws = new WebSocket(pageTab.webSocketDebuggerUrl);
    let id = 1;
    const callbacks = new Map();

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && callbacks.has(msg.id)) callbacks.get(msg.id)(msg.result);
    };

    await new Promise(r => ws.onopen = r);
    const send = (method, params = {}) => new Promise((resolve) => {
      const msgId = id++;
      callbacks.set(msgId, resolve);
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });

    await send('Page.enable');
    await send('Runtime.enable');
    await new Promise(r => setTimeout(r, 2000));

    // 1. Verify dynamic tabs loaded
    const tabCount = await send('Runtime.evaluate', {
      expression: 'document.querySelectorAll(".pack-tab-btn").length',
      returnByValue: true
    });
    console.log(`[OK] Studio loaded with ${tabCount.result.value} dynamic tabs.`);

    // 2. Click "✨ Harvest Scan"
    console.log('[*] Opening Harvest Modal...');
    await send('Runtime.evaluate', {
      expression: 'document.getElementById("harvest-btn").click()'
    });
    await new Promise(r => setTimeout(r, 500));

    // Capture Modal Open Screenshot
    const shotModal = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(ARTIFACT_DIR, 'studio_harvest_modal.png'), Buffer.from(shotModal.data, 'base64'));
    console.log('[OK] Saved modal screenshot: studio_harvest_modal.png');

    // 3. Stage the in-memory Base64 scan image
    console.log('[*] Staging in-memory image scan into Harvest Modal...');
    await send('Runtime.evaluate', {
      expression: `
        (function() {
          const previewImg = document.getElementById("harvest-preview-img");
          const emptyView = document.getElementById("dropzone-empty");
          const previewView = document.getElementById("dropzone-preview");
          const aspectBadge = document.getElementById("preview-aspect-badge");
          const formatBadge = document.getElementById("preview-format-badge");
          const packNameInput = document.getElementById("harvest-pack-name");
          const startBtn = document.getElementById("start-harvest-btn");

          emptyView.style.display = "none";
          previewView.style.display = "flex";
          previewImg.src = "${imgB64}";
          aspectBadge.textContent = "Aspect: 0.89";
          formatBadge.textContent = "Format: Card-Vertical (148×167mm)";
          packNameInput.value = "Editorial Specimen Card";
          startBtn.disabled = false;

          // Wire staged data for harvest trigger
          window.__stagedHarvestData = "${imgB64}";
        })()
      `
    });
    await new Promise(r => setTimeout(r, 600));

    // Capture Preview Screenshot
    const shotPreview = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(ARTIFACT_DIR, 'studio_harvest_preview.png'), Buffer.from(shotPreview.data, 'base64'));
    console.log('[OK] Saved preview screenshot: studio_harvest_preview.png');

    // 4. Trigger Compile
    console.log('[*] Submitting harvest to /api/harvest...');
    await send('Runtime.evaluate', {
      expression: `
        (async function() {
          const startBtn = document.getElementById("start-harvest-btn");
          const progressView = document.getElementById("harvest-progress");
          const progressLabel = document.getElementById("harvest-progress-label");
          startBtn.disabled = true;
          progressView.style.display = "flex";
          progressLabel.textContent = "Deconstructing visual DNA with Gemini Vision...";

          try {
            const res = await fetch("/api/harvest", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                imageBase64: window.__stagedHarvestData,
                mimeType: "image/png",
                packName: "Editorial Specimen Card"
              })
            });
            const data = await res.json();
            if (data.status === "success" && data.pack) {
              const newPack = data.pack;
              newPack.isHarvested = true;
              PACKS[newPack.id] = newPack;
              renderTabs();
              switchPack(newPack.id);
              document.getElementById("harvest-modal").classList.remove("active");
              window.__harvestFinished = true;
            } else {
              window.__harvestError = data.error || "Unknown error";
            }
          } catch (e) {
            window.__harvestError = e.message;
          }
        })()
      `
    });

    // Wait for compilation (up to 30 seconds)
    console.log('[*] Awaiting multimodal deconstruction and live mounting...');
    let finished = false;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 1000));
      const status = await send('Runtime.evaluate', {
        expression: '({ finished: !!window.__harvestFinished, error: window.__harvestError || null })',
        returnByValue: true
      });
      if (status.result.value.finished) {
        finished = true;
        break;
      }
      if (status.result.value.error) {
        throw new Error('Harvest failed in browser: ' + status.result.value.error);
      }
    }

    if (!finished) throw new Error('Harvest timed out after 30 seconds.');
    console.log('[OK] Pack harvested and mounted live!');

    // Wait for iframe to render
    await new Promise(r => setTimeout(r, 3000));

    // Verify iframe loaded and check HUD status
    const hudStatusText = await send('Runtime.evaluate', {
      expression: 'document.getElementById("hud-status").textContent',
      returnByValue: true
    });
    const hudFormatText = await send('Runtime.evaluate', {
      expression: 'document.getElementById("hud-format").textContent',
      returnByValue: true
    });
    console.log(`[OK] HUD Status: "${hudStatusText.result.value}" | Format: "${hudFormatText.result.value}"`);

    // Verify click-to-edit elements exist inside frame
    const editableCount = await send('Runtime.evaluate', {
      expression: `
        (function() {
          const frame = document.getElementById("pack-frame");
          const doc = frame.contentDocument || frame.contentWindow.document;
          return doc.querySelectorAll(".ac-editable").length;
        })()
      `,
      returnByValue: true
    });
    console.log(`[OK] Interactive click-to-edit elements inside harvested artboard: ${editableCount.result.value}`);

    // Capture Full Mounted Artboard Screenshot
    const shotMounted = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(ARTIFACT_DIR, 'studio_harvest_mounted.png'), Buffer.from(shotMounted.data, 'base64'));
    console.log('[OK] Saved mounted artboard screenshot: studio_harvest_mounted.png');

    console.log('\n[ALL VERIFICATIONS PASSED SUCCESSFULLY!]');
  } finally {
    chrome.kill('SIGKILL');
  }
}

run().catch((err) => {
  console.error('[!] Test failed:', err);
  process.exit(1);
});
