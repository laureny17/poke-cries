// Low-latency cry playback.
//
// Cries are tiny (~15 KB .ogg), so the slow part is everything around them:
// waiting on the API for the url, then downloading and decoding on click. This
// module builds the url locally, fetches + decodes ahead of time (on hover /
// press), and plays decoded buffers through Web Audio so a click starts sound
// right away. Falls back to a plain <audio> element if Web Audio can't decode.

const CRY_BASE_URL =
  "https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon";
const CRY_VOLUME = 0.75;
// Bounded caches: encoded bytes are small, decoded PCM is ~0.5 MB per cry.
const MAX_ENCODED_CRIES = 64;
const MAX_DECODED_CRIES = 12;

// Same urls the backend falls back to (backend/app.py _cry_urls_for_pokemon).
export const getCryUrl = (pokemonId, details = null) => {
  const latest =
    details?.cry_url_latest ||
    details?.cry_url ||
    `${CRY_BASE_URL}/latest/${pokemonId}.ogg`;
  const legacy =
    details?.cry_url_legacy || `${CRY_BASE_URL}/legacy/${pokemonId}.ogg`;
  // for pikachu, use the legacy cry which is better for comparison
  return pokemonId === 25 ? legacy : latest;
};

const encodedCache = new Map(); // url -> Promise<ArrayBuffer>
const decodedCache = new Map(); // url -> Promise<AudioBuffer>

const remember = (cache, key, value, maxSize) => {
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > maxSize) {
    cache.delete(cache.keys().next().value);
  }
  return value;
};

const recall = (cache, key) => {
  if (!cache.has(key)) return undefined;
  const value = cache.get(key);
  // refresh LRU position
  cache.delete(key);
  cache.set(key, value);
  return value;
};

let audioContext = null;
let webAudioUnavailable = false;
const getAudioContext = () => {
  if (audioContext || webAudioUnavailable) return audioContext;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    webAudioUnavailable = true;
    return null;
  }
  try {
    audioContext = new AudioContextClass();
  } catch (err) {
    webAudioUnavailable = true;
  }
  return audioContext;
};

const fetchEncoded = (url) => {
  const cached = recall(encodedCache, url);
  if (cached) return cached;
  const request = fetch(url).then((response) => {
    if (!response.ok) throw new Error(`Cry request failed: ${response.status}`);
    return response.arrayBuffer();
  });
  request.catch(() => encodedCache.delete(url));
  return remember(encodedCache, url, request, MAX_ENCODED_CRIES);
};

const decodeCry = (url) => {
  const cached = recall(decodedCache, url);
  if (cached) return cached;
  const context = getAudioContext();
  if (!context) return Promise.reject(new Error("Web Audio unavailable"));
  const decoded = fetchEncoded(url).then(
    // decodeAudioData detaches the buffer it's given, so hand it a copy
    (bytes) =>
      new Promise((resolve, reject) =>
        context.decodeAudioData(bytes.slice(0), resolve, reject),
      ),
  );
  decoded.catch(() => decodedCache.delete(url));
  return remember(decodedCache, url, decoded, MAX_DECODED_CRIES);
};

// Warm the caches so a later play is instant. Safe to call often.
export const prefetchCry = (url) => {
  if (!url) return;
  decodeCry(url).catch(() => {
    // Web Audio can't decode it; at least warm the HTTP cache for <audio>
    fetchEncoded(url).catch(() => {});
  });
};

let activeSource = null;
let activeElement = null;
let playToken = 0;

const stopActive = () => {
  if (activeSource) {
    try {
      activeSource.stop();
    } catch (err) {
      // already stopped
    }
    activeSource.disconnect();
    activeSource = null;
  }
  if (activeElement) {
    // Dropping src and calling load() lets the browser free the decoded audio
    // right away instead of keeping it alive until garbage collection.
    activeElement.pause();
    activeElement.removeAttribute("src");
    activeElement.load();
    activeElement = null;
  }
};

const playWithElement = async (url, token) => {
  const audio = new Audio(url);
  activeElement = audio;
  audio.volume = CRY_VOLUME;
  audio.addEventListener(
    "ended",
    () => {
      if (activeElement === audio) stopActive();
    },
    { once: true },
  );
  if (token === playToken) await audio.play();
};

export const playCry = async (url) => {
  if (!url) return;
  const token = ++playToken;
  stopActive();

  const context = getAudioContext();
  if (context) {
    // resume inside the click so browsers allow audio output
    if (context.state === "suspended") context.resume().catch(() => {});
    try {
      const buffer = await decodeCry(url);
      if (token !== playToken) return; // a newer click took over
      const source = context.createBufferSource();
      const gain = context.createGain();
      gain.gain.value = CRY_VOLUME;
      source.buffer = buffer;
      source.connect(gain);
      gain.connect(context.destination);
      source.onended = () => {
        if (activeSource === source) activeSource = null;
        source.disconnect();
        gain.disconnect();
      };
      activeSource = source;
      source.start();
      return;
    } catch (err) {
      if (token !== playToken) return;
      // fall through to <audio> (e.g. a browser that can't decode ogg here)
    }
  }

  await playWithElement(url, token);
};
