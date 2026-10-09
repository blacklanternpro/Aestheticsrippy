/**
 * AI Bridge for Aesthetic Compiler Studio.
 * Seamlessly toggles between:
 * 1. Zero-config Local Backend (when running on localhost)
 * 2. Client-side BYOK (Bring Your Own Key) for 100% portable mobile/static hosting.
 */

const AIClient = {
  localAvailable: false,
  apiKey: localStorage.getItem('ac_gemini_api_key') || '',
  model: localStorage.getItem('ac_gemini_model') || 'gemini-3.6-flash',

  async init() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        this.localAvailable = (data.status === 'ok');
        console.log('[AIClient] Local engine detected:', data);
      }
    } catch (e) {
      this.localAvailable = false;
      console.log('[AIClient] Running in standalone/static mode.');
    }
  },

  setApiKey(key) {
    this.apiKey = key.trim();
    localStorage.setItem('ac_gemini_api_key', this.apiKey);
  },

  setModel(modelName) {
    this.model = modelName.trim();
    localStorage.setItem('ac_gemini_model', this.model);
  },

  async generateReplacementImage(prompt) {
    // 1. Try local server first if available
    if (this.localAvailable) {
      try {
        const res = await fetch('/api/ai/replace-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt })
        });
        if (res.ok) {
          const data = await res.json();
          return data.imageUrl;
        }
      } catch (err) {
        console.warn('Local AI replace failed, falling back to direct API:', err);
      }
    }

    // 2. Client-side Generative Diffusion Fallback (Zero Key Required)
    const seed = Math.floor(Math.random() * 900000) + 100000;
    const cleanPrompt = encodeURIComponent(prompt);
    return `https://image.pollinations.ai/prompt/${cleanPrompt}?width=800&height=800&nologo=true&seed=${seed}`;
  }
};

window.AIClient = AIClient;
