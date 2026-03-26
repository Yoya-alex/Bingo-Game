export function getCallLetter(number, maxNumber = 400) {
  const value = Number(number);
  const safeMax = Math.max(5, Number(maxNumber) || 400);
  const step = Math.max(1, Math.floor(safeMax / 5));
  const letters = ["B", "I", "N", "G", "O"];
  const index = Math.min(4, Math.max(0, Math.floor((value - 1) / step)));
  return letters[index];
}

function numberToAmharicWords(number) {
  const value = Number(number);
  if (!Number.isFinite(value) || value <= 0) {
    return String(number);
  }

  const units = [
    "",
    "አንድ",
    "ሁለት",
    "ሶስት",
    "አራት",
    "አምስት",
    "ስድስት",
    "ሰባት",
    "ስምንት",
    "ዘጠኝ",
  ];
  const tens = {
    10: "አስር",
    20: "ሃያ",
    30: "ሰላሳ",
    40: "አርባ",
    50: "ሃምሳ",
    60: "ስልሳ",
    70: "ሰባ",
    80: "ሰማንያ",
    90: "ዘጠና",
  };

  const toUnderHundred = (n) => {
    if (n < 10) {
      return units[n];
    }
    if (n === 10) {
      return tens[10];
    }
    if (n < 20) {
      return `አስራ ${units[n - 10]}`;
    }

    const tensValue = Math.floor(n / 10) * 10;
    const remainder = n % 10;
    if (!remainder) {
      return tens[tensValue] || String(n);
    }
    return `${tens[tensValue]} ${units[remainder]}`;
  };

  const intValue = Math.floor(value);
  if (intValue < 100) {
    return toUnderHundred(intValue);
  }

  const hundreds = Math.floor(intValue / 100);
  const remainder = intValue % 100;
  const hundredPart = hundreds === 1 ? "መቶ" : `${units[hundreds]} መቶ`;
  if (!remainder) {
    return hundredPart;
  }
  return `${hundredPart} ${toUnderHundred(remainder)}`;
}

function buildAnnouncementText({ letter, number, voiceLang }) {
  const lang = String(voiceLang || "").toLowerCase();
  if (lang.startsWith("am-ET") || lang.startsWith("am-")||lang.startsWith("am-et")||lang.startsWith("ET") || lang.includes("amharic")){
    return `${letter} - ${numberToAmharicWords(number)}`;
  }
  return `${letter}-${number}`;
}

export default class VoiceSyncManager {
  constructor() {
    this.enabled = false;
    this.lastSpokenNumber = null;
    this.pendingTimeout = null;
    this.pendingNumber = null;
    this.clientServerOffsetMs = 0;
    this.supported = typeof window !== "undefined" && "speechSynthesis" in window;
    this.selectedVoice = null;
    this.selectedVoiceURI = null;
    this.onVoicesChanged = null;
    this.customAudioEnabled = String(import.meta.env.VITE_ENABLE_CUSTOM_AUDIO || "").toLowerCase() === "true";
    this.useCustomAudio = false; // Flag for custom audio files
    this.audioCache = {}; // Cache for loaded audio files

    if (this.supported) {
      this.initializeVoiceSelection();
    }
    
    // Check for custom audio only when explicitly enabled.
    if (this.customAudioEnabled) {
      this.checkCustomAudio();
    }
  }

  async checkCustomAudio() {
    try {
      // Try to load a test audio file to see if custom audio is available
      const response = await fetch('/audio/calls/B-1.mp3', { method: 'HEAD' });
      if (response.ok) {
        this.useCustomAudio = true;
        console.log('✅ Custom audio files detected - using your voice!');
      }
    } catch (error) {
      console.log('ℹ️ Custom audio not found - using text-to-speech');
      this.useCustomAudio = false;
    }
  }

  playCustomAudio(letter, number) {
    const audioKey = `${letter}-${number}`;
    const audioPath = `/audio/calls/${audioKey}.mp3`;
    
    // Check if audio is already cached
    if (this.audioCache[audioKey]) {
      const audio = this.audioCache[audioKey];
      audio.currentTime = 0; // Reset to start
      audio.play().catch(err => {
        console.error('Error playing cached audio:', err);
        this.fallbackToTTS(letter, number);
      });
      return;
    }
    
    // Load and play new audio
    const audio = new Audio(audioPath);
    audio.addEventListener('canplaythrough', () => {
      this.audioCache[audioKey] = audio; // Cache for future use
      audio.play().catch(err => {
        console.error('Error playing audio:', err);
        this.fallbackToTTS(letter, number);
      });
    }, { once: true });
    
    audio.addEventListener('error', () => {
      console.warn(`Audio file not found: ${audioPath}, falling back to TTS`);
      this.fallbackToTTS(letter, number);
    }, { once: true });
    
    audio.load();
  }

  fallbackToTTS(letter, number) {
    // Fallback to text-to-speech if audio file fails
    const selectedVoice = this.getSelectedVoice();
    const announcementText = buildAnnouncementText({
      letter,
      number,
      voiceLang: selectedVoice?.lang,
    });
    const utterance = new SpeechSynthesisUtterance(announcementText);
    if (selectedVoice) {
      utterance.voice = selectedVoice;
      utterance.lang = selectedVoice.lang || "en-US";
    } else {
      utterance.lang = "en-US";
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }

  initializeVoiceSelection() {
    this.refreshSelectedVoice();
    this.onVoicesChanged = () => this.refreshSelectedVoice();
    window.speechSynthesis.addEventListener("voiceschanged", this.onVoicesChanged);
  }

  scoreVoiceQuality(voice) {
    const name = String(voice?.name || "").toLowerCase();
    let score = 0;

    if (/neural|natural|wavenet|enhanced|premium|studio|high\s*quality/.test(name)) {
      score += 60;
    }
    if (/google|microsoft|apple|samsung/.test(name)) {
      score += 10;
    }
    if (voice?.default) {
      score += 8;
    }
    if (voice?.localService === false) {
      score += 4;
    }

    return score;
  }

  pickBestVoice(candidates) {
    if (!Array.isArray(candidates) || candidates.length === 0) {
      return null;
    }

    return candidates
      .slice()
      .sort((a, b) => this.scoreVoiceQuality(b) - this.scoreVoiceQuality(a))[0];
  }

  refreshSelectedVoice() {
    if (!this.supported) {
      return;
    }

    const voices = window.speechSynthesis.getVoices() || [];
    if (!voices.length) {
      return;
    }

    const amharicVoices = voices.filter((voice) => {
      const lang = String(voice?.lang || "").toLowerCase();
      const name = String(voice?.name || "").toLowerCase();
      return lang.startsWith("am") || name.includes("amhar");
    });

    const englishVoices = voices.filter((voice) => String(voice?.lang || "").toLowerCase().startsWith("en"));

    const selected =
      this.pickBestVoice(amharicVoices) ||
      this.pickBestVoice(englishVoices) ||
      this.pickBestVoice(voices);

    if (selected) {
      this.selectedVoice = selected;
      this.selectedVoiceURI = selected.voiceURI || selected.name || null;
    }
  }

  getSelectedVoice() {
    if (!this.supported) {
      return null;
    }

    if (!this.selectedVoice) {
      this.refreshSelectedVoice();
      return this.selectedVoice;
    }

    const voices = window.speechSynthesis.getVoices() || [];
    const matched = voices.find((voice) => (voice.voiceURI || voice.name || null) === this.selectedVoiceURI);
    if (matched) {
      this.selectedVoice = matched;
      return matched;
    }

    this.refreshSelectedVoice();
    return this.selectedVoice;
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled) {
      this.cancelPending();
      this.cancelSpeech();
    }
  }

  syncServerOffset(serverTime) {
    if (!serverTime) {
      return;
    }
    const serverMs = Date.parse(serverTime);
    if (!Number.isFinite(serverMs)) {
      return;
    }
    this.clientServerOffsetMs = Date.now() - serverMs;
  }

  cancelPending() {
    if (this.pendingTimeout) {
      clearTimeout(this.pendingTimeout);
      this.pendingTimeout = null;
      this.pendingNumber = null;
    }
  }

  cancelSpeech() {
    if (this.supported) {
      window.speechSynthesis.cancel();
    }
  }

  destroy() {
    this.cancelPending();
    this.cancelSpeech();
    if (this.supported && this.onVoicesChanged) {
      window.speechSynthesis.removeEventListener("voiceschanged", this.onVoicesChanged);
      this.onVoicesChanged = null;
    }
  }

  processUpdate({
    state,
    calledNumbers,
    serverTime,
    callIntervalSeconds,
    maxNumber,
  }) {
    if (!this.supported) {
      return { status: "unsupported" };
    }

    this.syncServerOffset(serverTime);

    if (state !== "playing") {
      this.cancelPending();
      return { status: "idle" };
    }

    if (!this.enabled) {
      return { status: "disabled" };
    }

    if (!Array.isArray(calledNumbers) || calledNumbers.length === 0) {
      return { status: "no-data" };
    }

    const latest = calledNumbers[calledNumbers.length - 1];
    const latestNumber = Number(latest?.number);
    if (!Number.isFinite(latestNumber)) {
      return { status: "invalid" };
    }

    if (this.lastSpokenNumber === latestNumber || this.pendingNumber === latestNumber) {
      return { status: "duplicate" };
    }

    this.cancelPending();

    const announce = () => {
      if (!this.enabled) {
        return;
      }
      const letter = getCallLetter(latestNumber, maxNumber);
      
      // Use custom audio if available, otherwise fallback to TTS
      if (this.useCustomAudio) {
        this.playCustomAudio(letter, latestNumber);
      } else {
        this.fallbackToTTS(letter, latestNumber);
      }
      
      this.lastSpokenNumber = latestNumber;
      this.pendingNumber = null;
      this.pendingTimeout = null;
    };

    announce();
    return { status: "spoken-now", number: latestNumber };
  }
}
