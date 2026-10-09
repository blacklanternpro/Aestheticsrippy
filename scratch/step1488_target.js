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