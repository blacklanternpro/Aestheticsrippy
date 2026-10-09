const PACKS = {
  'studio-neue': {
    name: 'Studio Neue Invoice',
    path: '../design-packs/studio-neue/template.html',
    format: 'A4',
    widthMm: 210,
    heightMm: 297
  },
  'manifesto-red': {
    name: 'Manifesto Red Poster',
    path: '../design-packs/manifesto-red/template.html',
    format: 'A4',
    widthMm: 210,
    heightMm: 297
  },
  'buum-industrial': {
    name: 'Buum Industrial Slip',
    path: '../design-packs/buum-industrial/template.html',
    format: 'A5',
    widthMm: 148,
    heightMm: 210
  },
  'thermal-artifact': {
    name: 'Thermal Artifact Receipt',
    path: '../design-packs/thermal-artifact/template.html',
    format: 'Thermal 80mm',
    widthMm: 80,
    heightMm: 205
  }
};

let currentPackId = 'studio-neue';
let isEditMode = true; // Enabled by default for immediate click-to-edit
let activeVisualObject = null;

const frame = document.getElementById('pack-frame');
const hudIndicator = document.getElementById('hud-indicator');
const hudStatus = document.getElementById('hud-status');
const hudFormat = document.getElementById('hud-format');
const editBtn = document.getElementById('edit-btn');
const tabButtons = document.querySelectorAll('.pack-tab-btn');

// Hidden File Upload Input for transparent PNG/SVG replacement
const uploadInput = document.createElement('input');
uploadInput.type = 'file';
uploadInput.accept = 'image/png, image/svg+xml, image/webp, image/jpeg';
uploadInput.style.display = 'none';
document.body.appendChild(uploadInput);

async function init() {
  if (window.AIClient) {
    await window.AIClient.init();
  }

  // Tab Switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const packId = btn.getAttribute('data-pack');
      switchPack(packId);
    });
  });

  // Edit Button Toggle
  editBtn.innerHTML = isEditMode ? '✓ Done Editing' : '✏️ Edit Mode';
  editBtn.classList.toggle('active', isEditMode);
  editBtn.addEventListener('click', toggleEditMode);

  // Reset Button
  document.getElementById('reset-btn').addEventListener('click', resetCurrentPack);

  // Print PDF Button
  document.getElementById('print-btn').addEventListener('click', printCurrentPack);

  // Settings Modal
  setupSettingsModal();

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

  tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-pack') === packId);
  });

  const pack = PACKS[packId];
  hudFormat.textContent = `${pack.format} (${pack.widthMm} × ${pack.heightMm}mm)`;

  frame.style.width = `${pack.widthMm}mm`;
  frame.style.height = `${pack.heightMm}mm`;

function onFrameLoaded() {
  try {
    const doc = frame.contentDocument || frame.contentWindow.document;
    if (!doc) return;

    // Restore LocalStorage Data if available
    const savedHtml = localStorage.getItem(`ac_pack_${currentPackId}`);
    if (savedHtml) {
      const sheet = doc.querySelector('.page-sheet') || doc.body;
      sheet.innerHTML = savedHtml;
    }

    applyEditState(doc);
    bindVisualObjects(doc);
    checkSpatialBudget(doc);
  } catch (err) {
    console.warn('Frame access error:', err);
  }
}

function toggleEditMode() {
  isEditMode = !isEditMode;
  editBtn.classList.toggle('active', isEditMode);
  editBtn.innerHTML = isEditMode ? '✓ Done Editing' : '✏️ Edit Mode';

  const doc = frame.contentDocument || frame.contentWindow.document;
  if (doc) {
    applyEditState(doc);
  }
}

/**
 * Universal Omni-Text Parser
 * Guarantees 100% of text nodes (including footer legal, metadata timestamps, tables, headlines)
 * are directly editable without breaking structural grid containers.
 */
function applyEditState(doc) {
  const sheet = doc.querySelector('.page-sheet') || doc.body;
  const candidateTags = 'h1, h2, h3, h4, h5, h6, p, span, div, footer, header, section, td, th, label, small, b, strong, i, em, li, [data-field]';
  const elements = sheet.querySelectorAll(candidateTags);

  elements.forEach(el => {
    // Skip gizmo, visual objects, and major structural wrappers
    if (
      el.closest('.vo-gizmo') ||
      el.closest('.visual-object') ||
      el.classList.contains('sn-meta-grid') || 
      el.classList.contains('sn-table') || 
      el.classList.contains('sn-table-body') ||
      el.classList.contains('mr-meta-grid') ||
      el.classList.contains('th-tracklist') ||
      el.classList.contains('page-sheet')
    ) {
      return;
    }

    // Direct text node check
    const hasDirectText = Array.from(el.childNodes).some(
      n => n.nodeType === Node.TEXT_NODE && n.nodeValue.trim().length > 0
    );

    const hasOnlyInline = Array.from(el.children).every(c => 
      ['BR', 'B', 'STRONG', 'SPAN', 'SUP', 'SUB', 'EM', 'I', 'SMALL'].includes(c.tagName)
    );

    if (hasDirectText || hasOnlyInline || el.hasAttribute('data-field')) {
      if (el.querySelector('svg, img') && !el.innerText.trim()) return;

      el.contentEditable = isEditMode ? 'true' : 'false';
      el.setAttribute('spellcheck', 'false');

      if (isEditMode) {
        el.classList.add('ac-editable');
        el.oninput = () => saveAndCheck(doc);
      } else {
        el.classList.remove('ac-editable');
      }
    }
  });
}

/**
 * Identify top-level visual entity from a click target
 */
function findVisualObject(target) {
  if (!target || target === target.ownerDocument.body) return null;
  if (target.closest('.vo-gizmo')) return null;

  // 1. Container elements
  const container = target.closest(
    '.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap, .bm-script-svg, .visual-object'
  );
  if (container) return container;

  // 2. Direct graphics
  const graphic = target.closest('img, svg');
  if (graphic && !graphic.classList.contains('vo-icon') && !graphic.closest('.vo-gizmo')) {
    return graphic;
  }

  return null;
}

/**
 * Visual Object Layer
 * Scans for graphics (stamps, cutout photos, signatures, logos)
 * Enables: Select, Delete, Upload Replace, Move, Resize, Rotate
 */
function bindVisualObjects(doc) {
  const visualSelectors = '.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap, .bm-script-svg, img, svg:not(.vo-icon)';
  const visualElements = doc.querySelectorAll(visualSelectors);

  visualElements.forEach(el => {
    // Avoid double tagging child svgs/imgs inside known visual containers
    if (
      el.parentElement &&
      el.parentElement.closest('.th-rubber-stamp, .mr-photo-inset, .sn-signature-wrap')
    ) {
      return;
    }

    el.classList.add('visual-object');
    el.style.cursor = 'move';
    el.style.pointerEvents = 'auto';
  });

  // Single document-level click dispatcher for rock-solid selection
  doc.removeEventListener('mousedown', doc._voMouseDownHandler);
  doc._voMouseDownHandler = (e) => {
    // If clicking on the gizmo handles or toolbar, let them handle it
    if (e.target.closest('.vo-gizmo')) return;

    const clickedVO = findVisualObject(e.target);
    if (clickedVO) {
      e.stopPropagation();
      e.preventDefault(); // prevent native browser drag ghosts
      selectVisualObject(clickedVO, doc);
      startDragObject(clickedVO, e, doc);
    } else {
      // Clicked on empty space or normal text -> deselect
      deselectVisualObject(doc);
    }
  };
  doc.addEventListener('mousedown', doc._voMouseDownHandler);

  // Keyboard Delete / Backspace
  doc.removeEventListener('keydown', doc._voKeyDownHandler);
  doc._voKeyDownHandler = (e) => {
    if ((e.key === 'Delete' || e.key === 'Backspace') && activeVisualObject && !e.target.isContentEditable) {
      e.preventDefault();
      deleteActiveObject(doc);
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

    const targetVO = findVisualObject(e.target) || activeVisualObject;
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

  // If already promoted, do not touch or re-promote
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
    // If element was inside layout flow, leave a transparent placeholder with identical size
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
  el.style.zIndex = '50';
  el.dataset.canvasObject = 'true';
  el.classList.add('visual-object-canvas');

  // Ensure child graphics scale cleanly and don't intercept events
  const innerGraphic = el.querySelector('img, svg');
  if (innerGraphic) {
    innerGraphic.style.width = '100%';
    innerGraphic.style.height = '100%';
    innerGraphic.style.display = 'block';
    innerGraphic.style.pointerEvents = 'none';
  }
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
        <button class="vo-btn vo-delete" title="Delete Object">🗑️ Delete</button>
        <button class="vo-btn vo-upload" title="Replace with Transparent PNG, SVG, or JPG">📁 Replace Image</button>
      </div>
      <div class="vo-rotate-stem"></div>
      <div class="vo-rotate-handle" title="Drag to Rotate (45° Snap)">⟳</div>
      <div class="vo-resize-handle" title="Drag to Resize (Proportional by default, hold Shift for freeform)"></div>
      <div class="vo-drag-surface" title="Drag to Move"></div>
    `;

    sheet.appendChild(gizmo);

    // Bind Toolbar Actions
    gizmo.querySelector('.vo-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteActiveObject(doc);
    });

    gizmo.querySelector('.vo-upload').addEventListener('click', (e) => {
      e.stopPropagation();
      uploadInput.click();
    });

    // Bind Gizmo Surface Move with mousedown prevention
    gizmo.querySelector('.vo-drag-surface').addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      startDragObject(targetEl, e, doc);
    });

    // Bind Rotate Handle with mousedown prevention
    gizmo.querySelector('.vo-rotate-handle').addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      startRotateObject(targetEl, gizmo, e, doc);
    });

    // Bind Resize Handle with mousedown prevention
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
 * 1:1 direct binding prevents any sub-pixel floating point drift or AABB mismatch.
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

  // Flip toolbar below object if too close to top edge of page
  if (targetEl.offsetTop < 95) {
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

document.addEventListener('DOMContentLoaded', init);
