(() => {
  "use strict";

  const CERT_BASE = "https://cot-v2-final-certification.vercel.app/snapshot/";
  const FILES = Object.freeze({
    active: { path: "cot-active-edges-build-time-v2.json", bytes: 77741, sha256: "e205bd07ac6e35c8abc120264e013b73656e60ba6d8d5918b6ab1e1480e923d2" },
    registry: { path: "cot-edge-registry-v2.json", bytes: 492041, sha256: "73d82c7d1ec0fb40a90346fd01c5e7f3ed06edf79689a6e4bb19a1441e39e67c" },
    "detail:sp500": { path: "cot-edge-details-v2/sp500.json", bytes: 2865540, sha256: "991cfefcea5863745aa000a1b23aed69885767d19880448eb1c46fa4b1e8f8ce" },
    "detail:nq": { path: "cot-edge-details-v2/nq.json", bytes: 2814076, sha256: "bb526a2daf12f441e7dda032915a82c1b1e68157b20be63c1033f0702e851bc2" },
    "detail:vix": { path: "cot-edge-details-v2/vix.json", bytes: 2817335, sha256: "3f0a381dd2587d954b6ae5825c27795eac434c0f06615d346e8edecf6ddf6308" },
    "detail:rty": { path: "cot-edge-details-v2/rty.json", bytes: 2173055, sha256: "4d7507e396e36f9f78bd2fcfe5fd9d6ff5601d8cb765f1377d2f12cdb8837263" },
    "detail:dow": { path: "cot-edge-details-v2/dow.json", bytes: 2837046, sha256: "35a6a980e1bb1c01e1b98b9644d4a96d7e36f3cc57e908e24f60cf7a46011ff7" },
    "detail:gold": { path: "cot-edge-details-v2/gold.json", bytes: 2847750, sha256: "ab7e134cae9a54ec962b79a029c02f4d337aa01e423ccd1dcc5319325b317453" },
    "detail:silver": { path: "cot-edge-details-v2/silver.json", bytes: 1616837, sha256: "921d523af015254a3cf5d6cb91b90807b47e6fd6a89f12fbd8120fc4b703e424" }
  });

  const nativeFetch = window.fetch.bind(window);
  const cache = new Map();
  const hex = buffer => Array.from(new Uint8Array(buffer), b => b.toString(16).padStart(2, "0")).join("");
  const state = window.__COT_V2_RUNTIME__ = {
    generation: "release-corrected-v2",
    certification: "independent_replay_certified",
    source: CERT_BASE,
    status: "loading",
    ready: false,
    error: null
  };

  function keyFor(input) {
    try {
      const raw = typeof input === "string" || input instanceof URL ? String(input) : input?.url;
      if (!raw) return null;
      const url = new URL(raw, window.location.href);
      if (url.origin !== window.location.origin) return null;
      const marker = "/worldclass/";
      const index = url.pathname.lastIndexOf(marker);
      if (index < 0) return null;
      const rel = url.pathname.slice(index + marker.length).replace(/^\/+/, "");
      if (rel === "cot-active-edges.json" || rel === "cot-active-edges-v2.json") return "active";
      if (rel === "cot-edge-registry.json" || rel === "cot-edge-registry-v2.json") return "registry";
      const match = rel.match(/^cot-edge-details(?:-v2)?\/(sp500|nq|vix|rty|dow|gold|silver)\.json$/);
      return match ? `detail:${match[1]}` : null;
    } catch (_) {
      return null;
    }
  }

  async function verifiedBytes(key) {
    if (cache.has(key)) return cache.get(key);
    const spec = FILES[key];
    if (!spec) throw new Error(`Unknown certified COT payload: ${key}`);
    const task = (async () => {
      const response = await nativeFetch(`${CERT_BASE}${spec.path}`, { mode: "cors", cache: "no-store" });
      if (!response.ok) throw new Error(`${spec.path} HTTP ${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.byteLength !== spec.bytes) throw new Error(`${spec.path} byte-size mismatch: ${bytes.byteLength}`);
      const digest = hex(await crypto.subtle.digest("SHA-256", bytes));
      if (digest !== spec.sha256) throw new Error(`${spec.path} SHA-256 mismatch: ${digest}`);
      return bytes;
    })();
    cache.set(key, task);
    try { return await task; }
    catch (error) { cache.delete(key); throw error; }
  }

  window.fetch = async function certifiedCotFetch(input, init) {
    const key = keyFor(input);
    if (!key) return nativeFetch(input, init);
    try {
      const bytes = await verifiedBytes(key);
      return new Response(bytes.slice(), {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
          "X-COT-Research-Generation": "release-corrected-v2",
          "X-COT-Certified": "true"
        }
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      state.status = "failed";
      state.ready = false;
      state.error = message;
      console.error("Certified COT v2 payload rejected; stale fallback is disabled.", error);
      return new Response(JSON.stringify({
        error: "certified_cot_v2_unavailable",
        research_generation: "release-corrected-v2",
        message
      }), { status: 503, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
    }
  };

  state.promise = Promise.all([verifiedBytes("active"), verifiedBytes("registry")])
    .then(() => {
      state.status = "ready";
      state.ready = true;
      return state;
    })
    .catch(error => {
      state.status = "failed";
      state.ready = false;
      state.error = error instanceof Error ? error.message : String(error);
      throw error;
    });
})();