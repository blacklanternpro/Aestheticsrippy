import { spawn } from 'child_process';
import fs from 'fs';

async function run() {
  const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
    '--headless=new',
    '--disable-gpu',
    '--remote-debugging-port=9235',
    '--window-size=1560,1100',
    'http://localhost:8080/studio/'
  ]);

  await new Promise(r => setTimeout(r, 2000));
  try {
    const listRes = await fetch('http://localhost:9235/json');
    const tabs = await listRes.json();
    const pageTab = tabs.find(t => t.type === 'page');
    const ws = new WebSocket(pageTab.webSocketDebuggerUrl);

    let id = 1;
    const callbacks = new Map();
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && callbacks.has(msg.id)) callbacks.get(msg.id)(msg.result);
    };

    await new Promise(r => ws.onopen = r);
    const send = (method, params = {}) => new Promise(r => {
      const msgId = id++;
      callbacks.set(msgId, r);
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });

    await send('Page.enable');
    await send('Runtime.enable');
    await new Promise(r => setTimeout(r, 1500));

    // Click Thermal Artifact
    await send('Runtime.evaluate', {
      expression: 'document.querySelector(\'[data-pack="thermal-artifact"]\').click()'
    });
    await new Promise(r => setTimeout(r, 1500));

    const shot = await send('Page.captureScreenshot', { format: 'png' });
    const dest = 'C:\\Users\\edtli\\.gemini\\antigravity\\brain\\7c137a69-7b2b-4715-a243-ec0297549714\\studio_thermal_verified.png';
    fs.writeFileSync(dest, Buffer.from(shot.data, 'base64'));
    console.log('[OK] Thermal Artifact tab screenshot verified');
  } finally {
    chrome.kill('SIGKILL');
  }
}

run().catch(console.error);
