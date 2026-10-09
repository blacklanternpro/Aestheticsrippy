let PACKS = {
  'studio-neue': {
    name: 'Studio Neue Invoice',
    path: '/design-packs/studio-neue/template.html',
    format: 'A4',
    widthMm: 210,
    heightMm: 297,
    icon: '📄'
  },
  'manifesto-red': {
    name: 'Manifesto Red Poster',
    path: '/design-packs/manifesto-red/template.html',
    format: 'A4',
    widthMm: 210,
    heightMm: 297,
    icon: '🟥'
  },
  'buum-industrial': {
    name: 'Buum Industrial Slip',
    path: '/design-packs/buum-industrial/template.html',
    format: 'A5',
    widthMm: 148,
    heightMm: 210,
    icon: '🎬'
  },
  'thermal-artifact': {
    name: 'Thermal Artifact Receipt',
    path: '/design-packs/thermal-artifact/template.html',
    format: 'Thermal 80mm',
    widthMm: 80,
    heightMm: 205,
    icon: '🧾'
  }
};

let currentPackId = 'studio-neue';
let currentMode = 'text'; // 'text' (default inline edit) | 'move' (freeform canvas spatial manipulation)
let activeVisualObject = null;

const frame = document.getElementById('pack-frame');
const hudIndicator = document.getElementById('hud-indicator');
const hudStatus = document.getElementById('hud-status');
const hudFormat = document.getElementById('hud-format');
const textModeBtn = document.getElementById('text-mode-btn');
const moveModeBtn = document.getElementById('move-mode-btn');
const tabsContainer = document.querySelector('.pack-tabs');

// Hidden File Upload Input for transparent PNG/SVG replacement
const uploadInput = document.createElement('input');
uploadInput.type = 'file';
uploadInput.accept = 'image/png, image/svg+xml, image/webp, image/jpeg';
uploadInput.style.display = 'none';
document.body.appendChild(uploadInput);

function getPackIcon(pack) {
  if (pack.icon) return pack.icon;
  const cat = (pack.category || '').toLowerCase();
  const id = (pack.id || '').toLowerCase();
  if (cat.includes('poster') || id.includes('poster') || cat.includes('editorial')) return '🟥';
  if (cat.includes('receipt') || id.includes('receipt') || id.includes('thermal')) return '🧾';
  if (cat.includes('invoice') || cat.includes('ledger') || id.includes('invoice')) return '📄';
  if (cat.includes('industrial') || id.includes('slip') || id.includes('spec')) return '🎬';
  if (cat.includes('identity') || id.includes('resume') || id.includes('card')) return '👤';
  return '✨';
}

function renderTabs() {
  if (!tabsContainer) return;
  tabsContainer.innerHTML = '';

  Object.keys(PACKS).forEach(packId => {
    const pack = PACKS[packId];
    const btn = document.createElement('button');
    btn.className = `pack-tab-btn ${packId === currentPackId ? 'active' : ''}`;
    btn.setAttribute('data-pack', packId);

    const icon = getPackIcon(pack);
    const badge = pack.isHarvested ? '<span class="harvest-badge">NEW</span>' : '';
    btn.innerHTML = `<span>${icon}</span> ${pack.name} ${badge}`;

    btn.addEventListener('click', () => switchPack(packId));
    tabsContainer.appendChild(btn);
  });
}

async function fetchPacksFromApi() {
  try {
    const res = await fetch('/api/packs');
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === 'success' && Array.isArray(data.packs)) {
      const dynamicPacks = {};
      data.packs.forEach(p => {
        dynamicPacks[p.id] = {
          ...(PACKS[p.id] || {}),
          ...p,
          isHarvested: !['studio-neue', 'manifesto-red', 'buum-industrial', 'thermal-artifact'].includes(p.id)
        };
      });
      PACKS = dynamicPacks;
      renderTabs();
    }
  } catch (err) {
    console.warn('[Studio] Could not fetch dynamic packs, using local baseline:', err);
  }
}

function injectStudioStyles(doc) {
  if (!doc || doc.getElementById('ac-studio-injected-styles')) return;
  const style = doc.createElement('style');
  style.id = 'ac-studio-injected-styles';
  style.textContent = `
    /* Universal Studio Interaction Styles */
    .vo-selected {
      outline: 1.5px solid #3b82f6 !important;
      outline-offset: 2px !important;
    }
    .ac-editable {
      outline: 1px dashed transparent;
      transition: outline 0.1s ease;
      cursor: text;
    }
    .ac-editable:hover {
      outline: 1px dashed rgba(59, 130, 246, 0.4);
    }
    .ac-editable:focus {
      outline: 1.5px solid #3b82f6 !important;
      outline-offset: 2px;
      background: rgba(59, 130, 246, 0.04);
    }
    body.mode-move {
      cursor: default;
    }
    body.mode-move .visual-object,
    body.mode-move [data-field],
    body.mode-move h1, body.mode-move h2, body.mode-move h3, body.mode-move h4,
    body.mode-move p, body.mode-move span, body.mode-move .glyph-circle,
    body.mode-move .dots, body.mode-move .left-diag, body.mode-move .right-diag,
    body.mode-move .pyramid-block, body.mode-move .step-01, body.mode-move .prototype-row {
      cursor: move !important;
    }
    body.mode-move .visual-object:hover,
    body.mode-move [data-field]:hover {
      outline: 1px dashed rgba(168, 85, 247, 0.6) !important;
      outline-offset: 2px;
    }
    .vo-gizmo {
      position: absolute;
      border: 1.5px solid #3b82f6;
      pointer-events: none;
      z-index: 10000;
      box-sizing: border-box;
      transform-origin: center center;
      user-select: none;
      -webkit-user-select: none;
    }
    .vo-gizmo .vo-toolbar {
      position: absolute;
      top: -44px;
      left: 50%;
      transform: translateX(-50%) rotate(calc(-1 * var(--gizmo-rot, 0deg)));
      transform-origin: center bottom;
      background: #0f172a;
      border: 1px solid #3b82f6;
      border-radius: 20px;
      padding: 3px 8px;
      display: flex;
      gap: 6px;
      pointer-events: auto;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
      white-space: nowrap;
      z-index: 10005;
    }
    .vo-gizmo.vo-toolbar-bottom .vo-toolbar {
      top: calc(100% + 16px);
      transform-origin: center top;
    }
    .vo-gizmo .vo-btn {
      background: transparent;
      border: none;
      color: #e2e8f0;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 6px;
      border-radius: 4px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 3px;
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
      transition: all 0.15s ease;
    }
    .vo-gizmo .vo-btn:hover {
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
    }
    .vo-gizmo .vo-btn.vo-delete:hover {
      background: rgba(239, 68, 68, 0.25);
      color: #fca5a5;
    }
    .vo-gizmo .vo-rotate-stem {
      position: absolute;
      top: -18px;
      left: 50%;
      width: 1px;
      height: 18px;
      background: #3b82f6;
      pointer-events: none;
    }
    .vo-gizmo .vo-rotate-handle {
      position: absolute;
      top: -28px;
      left: 50%;
      transform: translateX(-50%);
      width: 18px;
      height: 18px;
      background: #ffffff;
      border: 2px solid #3b82f6;
      border-radius: 50%;
      cursor: grab;
      pointer-events: auto;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #3b82f6;
      font-size: 10px;
      font-weight: 700;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
      z-index: 10002;
    }
    .vo-gizmo .vo-rotate-handle:hover {
      transform: translateX(-50%) scale(1.15);
      background: #3b82f6;
      color: #ffffff;
    }
    .vo-gizmo .vo-resize-handle {
      position: absolute;
      bottom: -6px;
      right: -6px;
      width: 12px;
      height: 12px;
      background: #ffffff;
      border: 2px solid #3b82f6;
      border-radius: 2px;
      cursor: nwse-resize;
      pointer-events: auto;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
      z-index: 10002;
    }
    .vo-gizmo .vo-resize-handle:hover {
      transform: scale(1.2);
      background: #3b82f6;
    }
    .vo-gizmo .vo-drag-surface {
      position: absolute;
      inset: 0;
      cursor: move;
      pointer-events: auto;
      background: transparent;
    }
    .vo-layout-placeholder {
      pointer-events: none;
      visibility: hidden;
    }
    @media print {
      .vo-gizmo, .vo-selected {
        display: none !important;
        outline: none !important;
      }
      .ac-editable {
        outline: none !important;
      }
    }
    /* Non-destructive styled element caret stability */
    [class*="typo-"], .date-hero, .idx, .artist-title, .header-text, .trip-col, .main-glyph, .inner-chars span {
      min-width: 1ch;
      display: inline-block;
    }
    [class*="typo-"]:empty::before,
    .date-hero:empty::before,
    .idx:empty::before,
    .artist-title:empty::before {
      content: "\\200b";
      pointer-events: none;
    }
  `;
  doc.head.appendChild(style);
}

function setStudioMode(mode) {
  currentMode = mode;
  if (textModeBtn) textModeBtn.classList.toggle('active', mode === 'text');
  if (moveModeBtn) moveModeBtn.classList.toggle('active', mode === 'move');

  const doc = frame.contentDocument || frame.contentWindow.document;
  if (doc) {
    if (doc.body) {
      doc.body.classList.toggle('mode-move', mode === 'move');
    }
    applyEditState(doc);
  }
}

async function init() {
  if (window.AIClient) {
    await window.AIClient.init();
  }

  // Initial render of tabs
  renderTabs();

  // Dynamic discovery from server
  await fetchPacksFromApi();

  // Mode Switch Buttons
  if (textModeBtn) textModeBtn.addEventListener('click', () => setStudioMode('text'));
  if (moveModeBtn) moveModeBtn.addEventListener('click', () => setStudioMode('move'));

  // Reset Button
  document.getElementById('reset-btn').addEventListener('click', resetCurrentPack);

  // Print PDF Button
  document.getElementById('print-btn').addEventListener('click', printCurrentPack);

  // Setup Modals & Typo Toolbar
  setupSettingsModal();
  setupHarvestModal();
  setupTypoToolbar();

  // Hidden Upload Listener
  uploadInput.addEventListener('change', handleImageUpload);

  // Frame Load Listener
  frame.addEventListener('load', onFrameLoaded);

  // Load initial pack
  switchPack(currentPackId);
}

function switchPack(packId) {
  if (!PACKS[packId]) return;
  currentPackId = packId;
  activeVisualObject = null;

  document.querySelectorAll('.pack-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-pack') === packId);
  });

  const pack = PACKS[packId];
  hudFormat.textContent = `${pack.format} (${pack.widthMm} × ${pack.heightMm}mm)`;

  frame.style.width = `${pack.widthMm}mm`;
  frame.style.height = `${pack.heightMm}mm`;
  frame.src = pack.path;
}

function onFrameLoaded() {
  try {
    const doc = frame.contentDocument || frame.contentWindow.document;
    if (!doc) return;

    injectStudioStyles(doc);

    // Restore LocalStorage Data if available
    const savedHtml = localStorage.getItem(`ac_pack_${currentPackId}`);
    if (savedHtml) {
      const sheet = doc.querySelector('.page-sheet') || doc.body;
      sheet.innerHTML = savedHtml;
    }

    setStudioMode(currentMode);
    bindVisualObjects(doc);
    checkSpatialBudget(doc);
  } catch (err) {
    console.warn('Frame access error:', err);
  }
}

/**
 * Universal Omni-Text Parser
 * Guarantees 100% of text nodes are directly editable in text mode.
 */
function applyEditState(doc) {
  const sheet = doc.querySelector('.page-sheet') || doc.body;
  if (!sheet) return;

  const candidateTags = 'h1, h2, h3, h4, h5, h6, p, span, div, footer, header, section, td, th, label, small, b, strong, i, em, li, [data-field]';
  const elements = sheet.querySelectorAll(candidateTags);

  elements.forEach(el => {
    if (el.closest('.vo-gizmo')) return;

    if (currentMode === 'move') {
      el.contentEditable = 'false';
      el.classList.remove('ac-editable');
      return;
    }

    // Skip canvas objects with pure graphics
    if (el.classList.contains('visual-object-canvas') && !el.innerText.trim()) return;

    const hasDirectText = Array.from(el.childNodes).some(
      n => n.nodeType === Node.TEXT_NODE && n.nodeValue.trim().length > 0
    );

    const hasOnlyInline = Array.from(el.children).every(c => 
      ['BR', 'B', 'STRONG', 'SPAN', 'SUP', 'SUB', 'EM', 'I', 'SMALL', 'KBD'].includes(c.tagName)
    );

    if (hasDirectText || hasOnlyInline || el.hasAttribute('data-field')) {
      if (el.querySelector('svg, img') && !el.innerText.trim()) return;

      el.contentEditable = 'true';
      el.setAttribute('spellcheck', 'false');
      el.classList.add('ac-editable');
      el.oninput = () => saveAndCheck(doc);

      // Track focused element for Typo Toolbar
      el.onfocus = () => {
        activeTypoElement = el;
        updateTypoToolbarState(el);
      };

      // Non-destructive keyboard shortcuts and span protection
      el.onkeydown = (e) => {
        // Typographic Quick Hotkeys: Ctrl + Shift + Key
        if (e.ctrlKey && e.shiftKey) {
          if (e.key === 'ArrowUp') { e.preventDefault(); adjustTypoScaleY(el, 0.05); return; }
          if (e.key === 'ArrowDown') { e.preventDefault(); adjustTypoScaleY(el, -0.05); return; }
          if (e.key === 'ArrowLeft') { e.preventDefault(); adjustTypoTracking(el, -0.5); return; }
          if (e.key === 'ArrowRight') { e.preventDefault(); adjustTypoTracking(el, 0.5); return; }
          if (e.key.toLowerCase() === 'w') { e.preventDefault(); toggleTypoWide(el); return; }
          if (e.key.toLowerCase() === 's') { e.preventDefault(); toggleTypoShadow(el); return; }
          if (e.key.toLowerCase() === 'u') { e.preventDefault(); toggleTypoRule(el); return; }
          if (e.key === '+' || e.key === '=') { e.preventDefault(); adjustTypoFontSize(el, 1); return; }
          if (e.key === '-' || e.key === '_') { e.preventDefault(); adjustTypoFontSize(el, -1); return; }
        }

        // Prevent empty backspace/delete from destroying styled element wrapper
        if (e.key === 'Backspace' || e.key === 'Delete') {
          const raw = el.innerText.replace(/\u200B/g, '');
          if (raw.length <= 1) {
            setTimeout(() => {
              if (!el.innerText || el.innerText.length === 0) {
                el.innerHTML = '&#8203;';
                const range = doc.createRange();
                const sel = doc.defaultView.getSelection();
                range.selectNodeContents(el);
                range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
              }
            }, 0);
          }
        }
      };
    }
  });
}

/**
 * Identify top-level visual entity from a click target.
 * In Move mode or with Alt/Meta/Ctrl held: ANY element or block can be targeted.
 * In Text mode: only explicit visual objects/graphics are targeted.
 */
function findVisualObject(target, e) {
  if (!target || target === target.ownerDocument.body || target.classList?.contains('page-sheet')) return null;
  if (target.closest('.vo-gizmo')) return null;

  const isMoveIntent = (currentMode === 'move') || (e && (e.altKey || e.metaKey || e.ctrlKey));

  // 1. If element is already promoted to canvas, return it
  const promoted = target.closest('[data-canvas-object="true"]');
  if (promoted) return promoted;

  // 2. Explicit visual objects, stamps, graphics, or photos
  const explicitVO = target.closest(
    '.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap, .bm-script-svg, .glyph-circle, .dots, .silhouette-container, .visual-object, img, svg:not(.vo-icon)'
  );
  if (explicitVO && !explicitVO.closest('.vo-gizmo')) return explicitVO;

  // 3. In Move mode or with modifier key: grab the nearest logical block
  if (isMoveIntent) {
    const block = target.closest(
      '[data-field], h1, h2, h3, h4, h5, h6, p, .tour-grid, .pyramid-block, .left-diag, .right-diag, .center-block, table, tr, header, footer, section, div'
    );
    if (block && block !== target.ownerDocument.body && !block.classList.contains('page-sheet')) {
      return block;
    }
    return target;
  }

  return null;
}

/**
 * Visual Object Layer
 * Enables: Select, Move, Rotate, Resize, Z-Index Layering, and Delete.
 */
function bindVisualObjects(doc) {
  const visualSelectors = '.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap, .bm-script-svg, img, svg:not(.vo-icon)';
  const visualElements = doc.querySelectorAll(visualSelectors);

  visualElements.forEach(el => {
    if (el.parentElement && el.parentElement.closest('.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap')) {
      return;
    }
    el.classList.add('visual-object');
    el.style.pointerEvents = 'auto';
  });

  // Single document-level mousedown dispatcher
  doc.removeEventListener('mousedown', doc._voMouseDownHandler);
  doc._voMouseDownHandler = (e) => {
    if (e.target.closest('.vo-gizmo')) return;

    const clickedVO = findVisualObject(e.target, e);
    if (clickedVO) {
      // In text mode without Alt: if clicking inside an editable text node, let native text focus happen
      if (currentMode === 'text' && !e.altKey && !e.metaKey && !e.ctrlKey) {
        if (clickedVO.isContentEditable || e.target.isContentEditable) {
          deselectVisualObject(doc);
          return;
        }
      }

      e.stopPropagation();
      e.preventDefault();
      selectVisualObject(clickedVO, doc);
      startDragObject(clickedVO, e, doc);
    } else {
      deselectVisualObject(doc);
    }
  };
  doc.addEventListener('mousedown', doc._voMouseDownHandler);

  // Keyboard Shortcuts (Delete, Layering, Arrow Nudge)
  doc.removeEventListener('keydown', doc._voKeyDownHandler);
  doc._voKeyDownHandler = (e) => {
    // Never intercept typing inside contentEditable
    if (e.target && e.target.isContentEditable) return;

    if (activeVisualObject) {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        deleteActiveObject(doc);
        return;
      }
      if (e.key === '[') {
        e.preventDefault();
        adjustZIndex(activeVisualObject, -10, doc);
        return;
      }
      if (e.key === ']') {
        e.preventDefault();
        adjustZIndex(activeVisualObject, 10, doc);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        deselectVisualObject(doc);
        return;
      }

      // Arrow Nudge (1px normal, 10px with Shift)
      const step = e.shiftKey ? 10 : 1;
      let handled = false;
      if (e.key === 'ArrowLeft') {
        activeVisualObject.style.left = `${activeVisualObject.offsetLeft - step}px`;
        handled = true;
      } else if (e.key === 'ArrowRight') {
        activeVisualObject.style.left = `${activeVisualObject.offsetLeft + step}px`;
        handled = true;
      } else if (e.key === 'ArrowUp') {
        activeVisualObject.style.top = `${activeVisualObject.offsetTop - step}px`;
        handled = true;
      } else if (e.key === 'ArrowDown') {
        activeVisualObject.style.top = `${activeVisualObject.offsetTop + step}px`;
        handled = true;
      }

      if (handled) {
        e.preventDefault();
        const gizmo = doc.querySelector('.vo-gizmo');
        if (gizmo) syncGizmo(activeVisualObject, gizmo, doc);
        saveAndCheck(doc);
      }
    }
  };
  doc.addEventListener('keydown', doc._voKeyDownHandler);

  // Drag & Drop Image Replacement directly from OS file explorer
  doc.removeEventListener('dragover', doc._voDragOverHandler);
  doc._voDragOverHandler = (e) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  };
  doc.addEventListener('dragover', doc._voDragOverHandler);

  doc.removeEventListener('drop', doc._voDropHandler);
  doc._voDropHandler = (e) => {
    e.preventDefault();
    const files = e.dataTransfer ? e.dataTransfer.files : null;
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!file.type.startsWith('image/')) return;

    const targetVO = findVisualObject(e.target, e) || activeVisualObject;
    if (!targetVO) return;

    selectVisualObject(targetVO, doc);
    const reader = new FileReader();
    reader.onload = (evt) => {
      const dataUrl = evt.target.result;
      let img = targetVO.querySelector('img');
      if (!img && targetVO.tagName === 'IMG') img = targetVO;
      if (img) {
        img.src = dataUrl;
      } else {
        targetVO.innerHTML = `<img src="${dataUrl}" style="width:100%;height:100%;object-fit:contain;pointer-events:none;display:block;">`;
      }
      const gizmo = doc.querySelector('.vo-gizmo');
      if (gizmo) syncGizmo(targetVO, gizmo, doc);
      saveAndCheck(doc);
    };
    reader.readAsDataURL(file);
  };
  doc.addEventListener('drop', doc._voDropHandler);
}

/**
 * Promote in-flow elements to absolute canvas objects on .page-sheet.
 * Leaves an invisible placeholder in layout so surrounding typography/tables never shift or collapse.
 * Uses center-invariant unrotated geometry to guarantee ZERO visual shift or jump.
 */
function promoteToSheetCanvas(el, doc) {
  const sheet = doc.querySelector('.page-sheet') || doc.body;
  if (!sheet) return;

  if (el.dataset.canvasObject === 'true' && el.parentElement === sheet) {
    return;
  }

  const sheetRect = sheet.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();

  const width = Math.round(el.offsetWidth || elRect.width);
  const height = Math.round(el.offsetHeight || elRect.height);

  // Rotation-invariant center coordinate in sheet space
  const cx = (elRect.left + elRect.right) / 2 - sheetRect.left;
  const cy = (elRect.top + elRect.bottom) / 2 - sheetRect.top;

  // Unrotated CSS left and top
  const left = Math.round(cx - width / 2);
  const top = Math.round(cy - height / 2);

  if (el.parentElement !== sheet || window.getComputedStyle(el).position !== 'absolute') {
    if (el.parentElement && el.parentElement !== sheet && window.getComputedStyle(el).position !== 'absolute') {
      const placeholder = doc.createElement('div');
      placeholder.className = 'vo-layout-placeholder';
      placeholder.style.width = `${width}px`;
      placeholder.style.height = `${height}px`;
      placeholder.style.flexShrink = '0';
      placeholder.style.pointerEvents = 'none';
      placeholder.style.visibility = 'hidden';
      placeholder.style.display = window.getComputedStyle(el).display === 'inline' ? 'inline-block' : 'block';
      el.parentElement.insertBefore(placeholder, el);
      el._placeholder = placeholder;
    }
    sheet.appendChild(el);
  }

  el.style.position = 'absolute';
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  el.style.right = 'auto';
  el.style.bottom = 'auto';
  el.style.width = `${width}px`;
  el.style.height = `${height}px`;
  el.style.margin = '0';
  if (!el.style.zIndex) el.style.zIndex = '50';
  el.dataset.canvasObject = 'true';
  el.classList.add('visual-object-canvas');

  const innerGraphic = el.querySelector('img, svg');
  if (innerGraphic) {
    innerGraphic.style.width = '100%';
    innerGraphic.style.height = '100%';
    innerGraphic.style.display = 'block';
    innerGraphic.style.pointerEvents = 'none';
  }
}

function adjustZIndex(el, delta, doc) {
  if (!el) return;
  promoteToSheetCanvas(el, doc);
  const curZ = parseInt(window.getComputedStyle(el).zIndex || el.style.zIndex || '50', 10);
  const newZ = Math.max(1, Math.min(9999, curZ + delta));
  el.style.zIndex = `${newZ}`;
  saveAndCheck(doc);
}

function selectVisualObject(el, doc) {
  if (activeVisualObject === el) return;
  deselectVisualObject(doc);

  promoteToSheetCanvas(el, doc);

  activeVisualObject = el;
  el.classList.add('vo-selected');

  createOrUpdateGizmo(el, doc);
}

function deselectVisualObject(doc) {
  if (!doc) return;
  const prev = doc.querySelector('.vo-selected');
  if (prev) prev.classList.remove('vo-selected');

  const oldGizmo = doc.querySelector('.vo-gizmo');
  if (oldGizmo) oldGizmo.remove();

  activeVisualObject = null;
}

/**
 * Get current rotation of element in degrees (-180 to 180)
 */
function getRotationDegrees(el) {
  if (el.dataset.rotation !== undefined) {
    return parseFloat(el.dataset.rotation) || 0;
  }

  const st = window.getComputedStyle(el, null);
  const tr = st.getPropertyValue('transform');
  if (tr && tr !== 'none') {
    const values = tr.split('(')[1].split(')')[0].split(',');
    const a = parseFloat(values[0]);
    const b = parseFloat(values[1]);
    const deg = Math.round(Math.atan2(b, a) * (180 / Math.PI));
    el.dataset.rotation = deg;
    return deg;
  }

  return 0;
}

/**
 * Create or sync the .vo-gizmo overlay positioned over the target element
 */
function createOrUpdateGizmo(targetEl, doc) {
  const sheet = doc.querySelector('.page-sheet') || doc.body;
  let gizmo = doc.querySelector('.vo-gizmo');

  if (!gizmo) {
    gizmo = doc.createElement('div');
    gizmo.className = 'vo-gizmo';
    gizmo.innerHTML = `
      <div class="vo-toolbar">
        <button class="vo-btn vo-delete" title="Delete Object (Delete/Backspace)">🗑️ Delete</button>
        <button class="vo-btn vo-front" title="Bring to Front (])">⬆️ Front</button>
        <button class="vo-btn vo-back" title="Send to Back ([)">⬇️ Back</button>
        <button class="vo-btn vo-upload" title="Replace Image">📁 Replace</button>
      </div>
      <div class="vo-rotate-stem"></div>
      <div class="vo-rotate-handle" title="Drag to Rotate (45° Snap)">⟳</div>
      <div class="vo-resize-handle" title="Drag to Resize (Proportional by default, hold Shift for freeform)"></div>
      <div class="vo-drag-surface" title="Drag to Move"></div>
    `;

    sheet.appendChild(gizmo);

    gizmo.querySelector('.vo-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteActiveObject(doc);
    });

    gizmo.querySelector('.vo-front').addEventListener('click', (e) => {
      e.stopPropagation();
      adjustZIndex(targetEl, 10, doc);
    });

    gizmo.querySelector('.vo-back').addEventListener('click', (e) => {
      e.stopPropagation();
      adjustZIndex(targetEl, -10, doc);
    });

    gizmo.querySelector('.vo-upload').addEventListener('click', (e) => {
      e.stopPropagation();
      uploadInput.click();
    });

    gizmo.querySelector('.vo-drag-surface').addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      startDragObject(targetEl, e, doc);
    });

    gizmo.querySelector('.vo-rotate-handle').addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      startRotateObject(targetEl, gizmo, e, doc);
    });

    gizmo.querySelector('.vo-resize-handle').addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      startResizeObject(targetEl, gizmo, e, doc);
    });
  }

  syncGizmo(targetEl, gizmo, doc);
}

/**
 * Synchronize .vo-gizmo size, position, and rotation directly from canvas element.
 */
function syncGizmo(targetEl, gizmo, doc) {
  if (!targetEl || !gizmo) return;

  const w = targetEl.offsetWidth;
  const h = targetEl.offsetHeight;
  const left = `${targetEl.offsetLeft}px`;
  const top = `${targetEl.offsetTop}px`;
  const rot = getRotationDegrees(targetEl);

  gizmo.style.position = 'absolute';
  gizmo.style.width = `${w}px`;
  gizmo.style.height = `${h}px`;
  gizmo.style.left = left;
  gizmo.style.top = top;
  gizmo.style.transform = `rotate(${rot}deg)`;
  gizmo.style.transformOrigin = 'center center';
  gizmo.style.setProperty('--gizmo-rot', `${rot}deg`);

  const hasImg = targetEl.tagName === 'IMG' || targetEl.querySelector('img, svg');
  const uploadBtn = gizmo.querySelector('.vo-upload');
  if (uploadBtn) uploadBtn.style.display = hasImg ? 'flex' : 'none';

  // Flip toolbar below object if too close to top edge of page
  if (targetEl.offsetTop < 70) {
    gizmo.classList.add('vo-toolbar-bottom');
  } else {
    gizmo.classList.remove('vo-toolbar-bottom');
  }
}

/**
 * Move Handler: 1:1 decoupled translation with text selection suppression & boundary clamping
 */
function startDragObject(el, e, doc) {
  promoteToSheetCanvas(el, doc);

  // Suppress text selection across iframe & parent window during drag
  doc.body.style.userSelect = 'none';
  doc.body.style.webkitUserSelect = 'none';
  document.body.style.userSelect = 'none';
  doc.getSelection()?.removeAllRanges();

  const sheet = doc.querySelector('.page-sheet') || doc.body;
  const sheetW = sheet.clientWidth || 794;
  const sheetH = sheet.clientHeight || 1123;
  const w = el.offsetWidth;
  const h = el.offsetHeight;

  const startX = e.clientX;
  const startY = e.clientY;
  const initialLeft = el.offsetLeft;
  const initialTop = el.offsetTop;
  const gizmo = doc.querySelector('.vo-gizmo');

  function onMouseMove(moveEvent) {
    moveEvent.preventDefault();

    let curX = moveEvent.clientX;
    let curY = moveEvent.clientY;

    // Normalize coordinates if mouse is dragging over outer parent window
    if (moveEvent.view !== doc.defaultView) {
      const frameEl = document.getElementById('pack-frame');
      if (frameEl) {
        const frameRect = frameEl.getBoundingClientRect();
        curX -= frameRect.left;
        curY -= frameRect.top;
      }
    }

    const dx = curX - startX;
    const dy = curY - startY;

    // Clamp coordinates so element never glitches off the canvas
    const minLeft = -w + 30;
    const maxLeft = sheetW - 30;
    const minTop = -h + 30;
    const maxTop = sheetH - 30;

    const newLeft = Math.max(minLeft, Math.min(maxLeft, Math.round(initialLeft + dx)));
    const newTop = Math.max(minTop, Math.min(maxTop, Math.round(initialTop + dy)));

    el.style.left = `${newLeft}px`;
    el.style.top = `${newTop}px`;

    syncGizmo(el, gizmo, doc);
  }

  function onMouseUp() {
    doc.removeEventListener('mousemove', onMouseMove);
    doc.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    doc.body.style.userSelect = '';
    doc.body.style.webkitUserSelect = '';
    document.body.style.userSelect = '';
    saveAndCheck(doc);
  }

  doc.addEventListener('mousemove', onMouseMove);
  doc.addEventListener('mouseup', onMouseUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
}

/**
 * Rotate Handler: delta-angle based rotation with text selection suppression & 45° snapping
 */
function startRotateObject(el, gizmo, e, doc) {
  promoteToSheetCanvas(el, doc);

  doc.body.style.userSelect = 'none';
  doc.body.style.webkitUserSelect = 'none';
  document.body.style.userSelect = 'none';
  doc.getSelection()?.removeAllRanges();

  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;

  // Compute angle delta from mousedown point to prevent any initial jump
  const startRad = Math.atan2(e.clientY - cy, e.clientX - cx);
  const startRot = getRotationDegrees(el);

  function onMouseMove(moveEvent) {
    moveEvent.preventDefault();

    let curX = moveEvent.clientX;
    let curY = moveEvent.clientY;

    if (moveEvent.view !== doc.defaultView) {
      const frameEl = document.getElementById('pack-frame');
      if (frameEl) {
        const frameRect = frameEl.getBoundingClientRect();
        curX -= frameRect.left;
        curY -= frameRect.top;
      }
    }

    const currentRad = Math.atan2(curY - cy, curX - cx);
    const deltaDeg = (currentRad - startRad) * (180 / Math.PI);
    let deg = Math.round(startRot + deltaDeg);

    while (deg > 180) deg -= 360;
    while (deg < -180) deg += 360;

    // Snap to 45 degree intervals if within 4 degrees
    if (Math.abs(deg % 45) < 4) {
      deg = Math.round(deg / 45) * 45;
    }

    el.dataset.rotation = deg;
    el.style.transform = `rotate(${deg}deg)`;
    gizmo.style.transform = `rotate(${deg}deg)`;
    gizmo.style.setProperty('--gizmo-rot', `${deg}deg`);
  }

  function onMouseUp() {
    doc.removeEventListener('mousemove', onMouseMove);
    doc.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    doc.body.style.userSelect = '';
    doc.body.style.webkitUserSelect = '';
    document.body.style.userSelect = '';
    saveAndCheck(doc);
  }

  doc.addEventListener('mousemove', onMouseMove);
  doc.addEventListener('mouseup', onMouseUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
}

/**
 * Resize Handler: Pinned top-left opposite anchor with exact rotation compensation.
 * Scales proportionally by default; hold Shift for non-uniform stretching.
 * Complete text-selection suppression and cross-window mouse capture.
 */
function startResizeObject(el, gizmo, e, doc) {
  promoteToSheetCanvas(el, doc);

  doc.body.style.userSelect = 'none';
  doc.body.style.webkitUserSelect = 'none';
  document.body.style.userSelect = 'none';
  doc.getSelection()?.removeAllRanges();

  const initW = el.offsetWidth;
  const initH = el.offsetHeight;
  const initLeft = el.offsetLeft;
  const initTop = el.offsetTop;
  const aspect = initW / Math.max(1, initH);

  const rotDeg = getRotationDegrees(el);
  const rotRad = (rotDeg * Math.PI) / 180;
  const cosRot = Math.cos(rotRad);
  const sinRot = Math.sin(rotRad);

  // Initial center in sheet coordinates
  const c0x = initLeft + initW / 2;
  const c0y = initTop + initH / 2;

  // Pinned opposite anchor (top-left corner) in sheet coordinates
  const pTLx = c0x - (initW / 2) * cosRot + (initH / 2) * sinRot;
  const pTLy = c0y - (initW / 2) * sinRot - (initH / 2) * cosRot;

  const startX = e.clientX;
  const startY = e.clientY;

  function onMouseMove(moveEvent) {
    moveEvent.preventDefault();

    let curX = moveEvent.clientX;
    let curY = moveEvent.clientY;

    if (moveEvent.view !== doc.defaultView) {
      const frameEl = document.getElementById('pack-frame');
      if (frameEl) {
        const frameRect = frameEl.getBoundingClientRect();
        curX -= frameRect.left;
        curY -= frameRect.top;
      }
    }

    const dx = curX - startX;
    const dy = curY - startY;

    // Project delta into element's local unrotated coordinate space
    const localDx = dx * Math.cos(-rotRad) - dy * Math.sin(-rotRad);
    const localDy = dx * Math.sin(-rotRad) + dy * Math.cos(-rotRad);

    let newW = Math.max(28, Math.round(initW + localDx));
    let newH;
    if (moveEvent.shiftKey) {
      newH = Math.max(28, Math.round(initH + localDy));
    } else {
      newH = Math.max(28, Math.round(newW / aspect));
    }

    // Exact pinned top-left compensation in world space
    const newLeft = Math.round(pTLx + (newW / 2) * (cosRot - 1) - (newH / 2) * sinRot);
    const newTop = Math.round(pTLy + (newW / 2) * sinRot + (newH / 2) * (cosRot - 1));

    el.style.width = `${newW}px`;
    el.style.height = `${newH}px`;
    el.style.left = `${newLeft}px`;
    el.style.top = `${newTop}px`;

    // Ensure child visual elements stretch cleanly
    const innerGraphic = el.querySelector('img, svg');
    if (innerGraphic) {
      innerGraphic.style.width = '100%';
      innerGraphic.style.height = '100%';
    }

    syncGizmo(el, gizmo, doc);
  }

  function onMouseUp() {
    doc.removeEventListener('mousemove', onMouseMove);
    doc.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    doc.body.style.userSelect = '';
    doc.body.style.webkitUserSelect = '';
    document.body.style.userSelect = '';
    saveAndCheck(doc);
  }

  doc.addEventListener('mousemove', onMouseMove);
  doc.addEventListener('mouseup', onMouseUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
}

function deleteActiveObject(doc) {
  if (!activeVisualObject) return;
  const target = activeVisualObject;
  const placeholder = target._placeholder;
  deselectVisualObject(doc);
  target.remove();
  if (placeholder && placeholder.parentElement) {
    placeholder.remove();
  }
  activeVisualObject = null;
  saveAndCheck(doc);
}

function handleImageUpload(e) {
  const file = e.target.files[0];
  if (!file || !activeVisualObject) return;

  const reader = new FileReader();
  reader.onload = (event) => {
    const dataUrl = event.target.result;
    const doc = frame.contentDocument || frame.contentWindow.document;

    let img = activeVisualObject.querySelector('img');
    if (!img && activeVisualObject.tagName === 'IMG') {
      img = activeVisualObject;
    }

    if (img) {
      img.src = dataUrl;
    } else {
      activeVisualObject.innerHTML = `<img src="${dataUrl}" style="width:100%;height:100%;object-fit:contain;pointer-events:none;display:block;">`;
    }

    const gizmo = doc.querySelector('.vo-gizmo');
    if (gizmo) syncGizmo(activeVisualObject, gizmo, doc);

    saveAndCheck(doc);
  };
  reader.readAsDataURL(file);
  e.target.value = '';
}

function saveAndCheck(doc) {
  const sheet = doc.querySelector('.page-sheet') || doc.body;

  // Clean temporary gizmo before serializing to localStorage
  const clone = sheet.cloneNode(true);
  clone.querySelectorAll('.vo-gizmo').forEach(g => g.remove());
  clone.querySelectorAll('.vo-selected').forEach(s => s.classList.remove('vo-selected'));

  localStorage.setItem(`ac_pack_${currentPackId}`, clone.innerHTML);
  checkSpatialBudget(doc);
}

function checkSpatialBudget(doc) {
  const sheet = doc.querySelector('.page-sheet');
  if (!sheet) return;

  const isOverflow = sheet.scrollHeight > sheet.clientHeight + 2;
  if (isOverflow) {
    hudIndicator.className = 'hud-indicator danger';
    hudStatus.textContent = '⚠️ Boundary Alert: Exceeds 1 Sheet';
  } else {
    hudIndicator.className = 'hud-indicator';
    hudStatus.textContent = 'Strict 1-Sheet Locked';
  }
}

function resetCurrentPack() {
  if (confirm(`Reset ${PACKS[currentPackId].name} to default?`)) {
    localStorage.removeItem(`ac_pack_${currentPackId}`);
    frame.src = PACKS[currentPackId].path;
  }
}

function printCurrentPack() {
  if (frame.contentWindow) {
    deselectVisualObject(frame.contentDocument);
    frame.contentWindow.focus();
    frame.contentWindow.print();
  }
}

function setupSettingsModal() {
  const modal = document.getElementById('settings-modal');
  const openBtn = document.getElementById('settings-btn');
  const closeBtn = document.getElementById('close-settings-btn');
  const saveKeyBtn = document.getElementById('save-key-btn');
  const keyInput = document.getElementById('gemini-key-input');
  const modelSelect = document.getElementById('model-select');
  const localBadge = document.getElementById('local-status-badge');

  if (!modal || !openBtn) return;

  openBtn.addEventListener('click', () => {
    keyInput.value = localStorage.getItem('ac_gemini_api_key') || '';
    modelSelect.value = localStorage.getItem('ac_gemini_model') || 'gemini-3.6-flash';

    if (window.AIClient && window.AIClient.localAvailable) {
      localBadge.textContent = '🟢 Local Engine Active (Zero API Key Needed)';
      localBadge.className = 'status-badge local-active';
    } else {
      localBadge.textContent = '⚪ Standalone Mode (Enter Gemini API Key for Mobile/Web)';
      localBadge.className = 'status-badge';
    }

    modal.classList.add('active');
  });

  closeBtn.addEventListener('click', () => modal.classList.remove('active'));

  saveKeyBtn.addEventListener('click', () => {
    if (window.AIClient) {
      window.AIClient.setApiKey(keyInput.value);
      window.AIClient.setModel(modelSelect.value);
    }
    modal.classList.remove('active');
    alert('Settings saved!');
  });
}

function setupHarvestModal() {
  const modal = document.getElementById('harvest-modal');
  const openBtn = document.getElementById('harvest-btn');
  const closeBtn = document.getElementById('close-harvest-btn');
  const cancelBtn = document.getElementById('cancel-harvest-btn');
  const dropzone = document.getElementById('harvest-dropzone');
  const fileInput = document.getElementById('scan-file-input');
  const browseBtn = document.getElementById('browse-scan-btn');
  const emptyView = document.getElementById('dropzone-empty');
  const previewView = document.getElementById('dropzone-preview');
  const previewImg = document.getElementById('harvest-preview-img');
  const aspectBadge = document.getElementById('preview-aspect-badge');
  const formatBadge = document.getElementById('preview-format-badge');
  const removeBtn = document.getElementById('remove-preview-btn');
  const packNameInput = document.getElementById('harvest-pack-name');
  const startBtn = document.getElementById('start-harvest-btn');
  const progressView = document.getElementById('harvest-progress');
  const progressLabel = document.getElementById('harvest-progress-label');

  if (!modal || !openBtn) return;

  let stagedFile = null;
  let stagedDataUrl = null;

  function resetHarvestForm() {
    stagedFile = null;
    stagedDataUrl = null;
    fileInput.value = '';
    emptyView.style.display = 'block';
    previewView.style.display = 'none';
    previewImg.src = '';
    startBtn.disabled = true;
    startBtn.textContent = 'Compile Design Pack';
    progressView.style.display = 'none';
    packNameInput.value = '';
  }

  function handleStagedFile(file) {
    if (!file || !file.type.startsWith('image/')) {
      alert('Please upload a valid image file (PNG, JPG, WebP).');
      fileInput.value = '';
      return;
    }
    stagedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
      stagedDataUrl = e.target.result;
      previewImg.src = stagedDataUrl;
      emptyView.style.display = 'none';
      previewView.style.display = 'flex';

      // Inspect image dimensions and aspect ratio
      const tempImg = new Image();
      tempImg.onload = () => {
        const aspect = tempImg.width / tempImg.height;
        aspectBadge.textContent = `Aspect: ${aspect.toFixed(2)}`;
        
        let formatName = 'A4 (210×297mm)';
        if (aspect < 0.55) formatName = 'Thermal-80mm';
        else if (aspect >= 0.65 && aspect <= 0.75) formatName = 'A4 / A5 Standard';
        else if (aspect > 0.75 && aspect <= 0.85) formatName = 'US-Letter';
        else if (aspect >= 0.95 && aspect <= 1.05) formatName = 'Card-Square (180mm)';
        else if (aspect > 1.2) formatName = 'A4 Landscape';
        formatBadge.textContent = `Format: ${formatName}`;

        if (!packNameInput.value.trim()) {
          const rawName = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
          packNameInput.value = rawName.charAt(0).toUpperCase() + rawName.slice(1);
        }

        startBtn.disabled = false;
      };
      tempImg.src = stagedDataUrl;
      // CRITICAL: Always reset fileInput.value to prevent file cache lockups
      fileInput.value = '';
    };
    reader.readAsDataURL(file);
  }

  openBtn.addEventListener('click', () => {
    resetHarvestForm();
    modal.classList.add('active');
  });

  closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  cancelBtn.addEventListener('click', () => modal.classList.remove('active'));

  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  dropzone.addEventListener('click', (e) => {
    if (previewView.style.display === 'none' && e.target !== browseBtn) {
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleStagedFile(e.target.files[0]);
    }
  });

  removeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    resetHarvestForm();
  });

  // Drag and Drop support
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-active');
  });
  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-active');
  });
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-active');
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleStagedFile(e.dataTransfer.files[0]);
    }
  });

  // Start Compile Action
  startBtn.addEventListener('click', async () => {
    if (!stagedDataUrl) return;

    startBtn.disabled = true;
    progressView.style.display = 'flex';
    progressLabel.textContent = 'Deconstructing visual DNA with Gemini Vision...';

    const packName = packNameInput.value.trim() || 'Harvested Design Pack';

    try {
      const res = await fetch('/api/harvest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          imageBase64: stagedDataUrl,
          mimeType: stagedFile ? stagedFile.type : 'image/png',
          packName: packName,
          apiKey: localStorage.getItem('ac_gemini_api_key') || undefined,
          model: localStorage.getItem('ac_gemini_model') || undefined
        })
      });

      const data = await res.json();
      if (data.status === 'success' && data.pack) {
        progressLabel.textContent = 'Compiling and mounting Design Pack...';
        const newPack = data.pack;
        newPack.isHarvested = true;
        PACKS[newPack.id] = newPack;

        renderTabs();
        switchPack(newPack.id);

        setTimeout(() => {
          modal.classList.remove('active');
          resetHarvestForm();
        }, 500);
      } else {
        throw new Error(data.error || 'Failed to harvest design pack.');
      }
    } catch (err) {
      console.error('Harvest failure:', err);
      alert('Harvest failed: ' + err.message);
      progressView.style.display = 'none';
      startBtn.disabled = false;
    }
  });
}

/**
 * Typographic Exactness & Non-Destructive In-Style Styler
 */
let activeTypoElement = null;

function updateTypoToolbarState(el) {
  const tallBtn = document.getElementById('typo-tall-btn');
  const wideBtn = document.getElementById('typo-wide-btn');
  const bunchBtn = document.getElementById('typo-bunch-btn');
  const spreadBtn = document.getElementById('typo-spread-btn');
  const shadowBtn = document.getElementById('typo-shadow-btn');
  const skewBtn = document.getElementById('typo-skew-btn');
  const ruleBtn = document.getElementById('typo-rule-btn');

  if (!el) {
    [tallBtn, wideBtn, bunchBtn, spreadBtn, shadowBtn, skewBtn, ruleBtn].forEach(b => b && b.classList.remove('active'));
    return;
  }

  const win = el.ownerDocument.defaultView || window;
  const comp = win.getComputedStyle(el);
  const tf = el.style.transform || comp.transform || '';
  const isTall = tf.includes('scaleY') || el.classList.contains('typo-condensed-tall') || el.classList.contains('date-hero');
  const isWide = tf.includes('scaleX') || el.classList.contains('typo-wide');
  const isBunched = el.classList.contains('typo-bunched') || (parseFloat(comp.letterSpacing) < -0.3);
  const isSpread = el.classList.contains('typo-spread') || (parseFloat(comp.letterSpacing) > 2);
  const isShadow = el.classList.contains('chromatic-shadow') || (comp.textShadow && comp.textShadow !== 'none');
  const isSkewed = tf.includes('skew') || el.classList.contains('typo-warped');
  const hasRule = comp.borderBottomWidth && comp.borderBottomWidth !== '0px' && comp.borderBottomStyle !== 'none';

  if (tallBtn) tallBtn.classList.toggle('active', !!isTall);
  if (wideBtn) wideBtn.classList.toggle('active', !!isWide);
  if (bunchBtn) bunchBtn.classList.toggle('active', !!isBunched);
  if (spreadBtn) spreadBtn.classList.toggle('active', !!isSpread);
  if (shadowBtn) shadowBtn.classList.toggle('active', !!isShadow);
  if (skewBtn) skewBtn.classList.toggle('active', !!isSkewed);
  if (ruleBtn) ruleBtn.classList.toggle('active', !!hasRule);
}

function adjustTypoScaleY(el, delta) {
  if (!el) return;
  el.style.display = 'inline-block';
  el.style.transformOrigin = 'left bottom';
  const curTf = el.style.transform || '';
  let curScale = 1.0;
  const match = curTf.match(/scaleY\(([\d\.]+)\)/);
  if (match) {
    curScale = parseFloat(match[1]);
  } else if (el.classList.contains('typo-condensed-tall') || el.classList.contains('date-hero')) {
    curScale = 1.18;
  }
  const nextScale = Math.max(0.6, Math.min(2.5, +(curScale + delta).toFixed(2)));
  if (match) {
    el.style.transform = curTf.replace(/scaleY\([\d\.]+\)/, `scaleY(${nextScale})`);
  } else {
    el.style.transform = (curTf + ` scaleY(${nextScale})`).trim();
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoTall(el) {
  if (!el) return;
  el.style.display = 'inline-block';
  el.style.transformOrigin = 'left bottom';
  const curTf = el.style.transform || '';
  if (curTf.includes('scaleY')) {
    el.style.transform = curTf.replace(/scaleY\([^)]+\)/g, '').trim();
    el.classList.remove('typo-condensed-tall', 'date-hero');
  } else {
    el.style.transform = (curTf + ' scaleY(1.22)').trim();
    if (!el.style.fontFamily) el.style.fontFamily = "'Anton', 'Bebas Neue', 'Barlow Condensed', sans-serif";
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoBunch(el) {
  if (!el) return;
  if (el.classList.contains('typo-bunched') || el.style.letterSpacing === '-0.05em') {
    el.classList.remove('typo-bunched');
    el.style.letterSpacing = '';
    el.style.lineHeight = '';
  } else {
    el.classList.add('typo-bunched');
    el.style.letterSpacing = '-0.05em';
    el.style.lineHeight = '0.88';
    el.style.fontWeight = '900';
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoSpread(el) {
  if (!el) return;
  if (el.classList.contains('typo-spread') || el.style.letterSpacing === '0.25em') {
    el.classList.remove('typo-spread');
    el.style.letterSpacing = '';
    el.style.textTransform = '';
  } else {
    el.classList.add('typo-spread');
    el.style.letterSpacing = '0.25em';
    el.style.textTransform = 'uppercase';
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoSkew(el) {
  if (!el) return;
  el.style.display = 'inline-block';
  el.style.transformOrigin = 'left bottom';
  const curTf = el.style.transform || '';
  if (curTf.includes('skewX')) {
    el.style.transform = curTf.replace(/skewX\([^)]+\)/g, '').trim();
    el.classList.remove('typo-warped');
  } else {
    el.style.transform = (curTf + ' skewX(-7deg)').trim();
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoRule(el) {
  if (!el) return;
  el.style.display = 'inline-block';
  if (el.style.borderBottom && el.style.borderBottom !== 'none') {
    el.style.borderBottom = 'none';
    el.style.paddingBottom = '';
  } else {
    el.style.borderBottom = '2.5px solid #000';
    el.style.paddingBottom = '2px';
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoWide(el) {
  if (!el) return;
  el.style.display = 'inline-block';
  el.style.transformOrigin = 'center center';
  const curTf = el.style.transform || '';
  if (curTf.includes('scaleX') || el.classList.contains('typo-wide')) {
    el.style.transform = curTf.replace(/scaleX\([^)]+\)/g, '').trim();
    el.classList.remove('typo-wide');
  } else {
    el.style.transform = (curTf + ' scaleX(1.25)').trim();
    el.classList.add('typo-wide');
    if (!el.style.fontFamily) el.style.fontFamily = "'Syne', 'Archivo Black', 'Montserrat', sans-serif";
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function toggleTypoShadow(el) {
  if (!el) return;
  if (el.classList.contains('chromatic-shadow') || (el.style.textShadow && el.style.textShadow !== 'none')) {
    el.classList.remove('chromatic-shadow');
    el.style.textShadow = 'none';
  } else {
    el.classList.add('chromatic-shadow');
    el.style.textShadow = '3.5px 3.5px 0px var(--shadow-color, #ff6600)';
  }
  updateTypoToolbarState(el);
  saveAndCheck(el.ownerDocument);
}

function adjustTypoFontSize(el, deltaPx) {
  if (!el) return;
  const win = el.ownerDocument.defaultView || window;
  const comp = win.getComputedStyle(el);
  let cur = parseFloat(comp.fontSize) || 16;
  const next = Math.max(6, Math.min(160, Math.round(cur + deltaPx)));
  el.style.fontSize = `${next}px`;
  saveAndCheck(el.ownerDocument);
}

function adjustTypoTracking(el, deltaPx) {
  if (!el) return;
  const win = el.ownerDocument.defaultView || window;
  const comp = win.getComputedStyle(el);
  let cur = parseFloat(comp.letterSpacing) || 0;
  const next = +(cur + deltaPx).toFixed(1);
  el.style.letterSpacing = `${next}px`;
  saveAndCheck(el.ownerDocument);
}

function setupTypoToolbar() {
  const getActive = () => {
    if (activeTypoElement && activeTypoElement.isConnected) return activeTypoElement;
    const doc = frame.contentDocument || frame.contentWindow.document;
    if (doc) {
      const activeInDoc = doc.activeElement;
      if (activeInDoc && activeInDoc.isContentEditable) return activeInDoc;
      const sel = doc.getSelection();
      if (sel && sel.anchorNode) {
        return sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
      }
    }
    return null;
  };

  document.getElementById('typo-tall-btn')?.addEventListener('click', () => toggleTypoTall(getActive()));
  document.getElementById('typo-wide-btn')?.addEventListener('click', () => toggleTypoWide(getActive()));
  document.getElementById('typo-bunch-btn')?.addEventListener('click', () => toggleTypoBunch(getActive()));
  document.getElementById('typo-spread-btn')?.addEventListener('click', () => toggleTypoSpread(getActive()));
  document.getElementById('typo-shadow-btn')?.addEventListener('click', () => toggleTypoShadow(getActive()));
  document.getElementById('typo-skew-btn')?.addEventListener('click', () => toggleTypoSkew(getActive()));
  document.getElementById('typo-rule-btn')?.addEventListener('click', () => toggleTypoRule(getActive()));
  document.getElementById('typo-minus-btn')?.addEventListener('click', () => adjustTypoFontSize(getActive(), -2));
  document.getElementById('typo-plus-btn')?.addEventListener('click', () => adjustTypoFontSize(getActive(), 2));
}

document.addEventListener('DOMContentLoaded', init);
