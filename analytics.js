(() => {
  "use strict";

  const config = window.LAMPGRID_ANALYTICS_CONFIG || {};
  const id = config.measurementId;
  const available = config.enabled === true && /^G-[A-Z0-9]+$/.test(id || "")
    && Array.isArray(config.allowedOrigins) && config.allowedOrigins.includes(location.origin);
  const consentKey = "lampgrid.analyticsConsent.v1";
  const cookiePrefix = "lampgrid_";
  const appPath = new URL(".", document.baseURI).pathname;
  const canonical = "https://oool727.github.io/beatmaniaIIDX-11-12-grid/";
  const contexts = ["demo", "actual"];
  const entries = ["header", "toolbar", "footer"];
  const schema = {
    demo_start: {entry: ["welcome", "toolbar"]},
    score_import_success: {method: ["csv", "paste"]},
    score_import_failure: {method: ["csv", "paste"], reason: ["invalid_input", "read_error", "empty_input"]},
    saved_data_restore: {},
    table_change: {level: ["9", "10", "11", "12"], mode: ["normal", "hard"], source: ["nask", "kosho", "wiki"], context: contexts},
    search_use: {context: contexts},
    feedback_open: {kind: ["bug", "feature", "feedback"], entry: entries},
    share_open: {entry: ["header", "footer"]}
  };
  let choice = "unknown";
  let state = available ? "idle" : "unconfigured";
  let storageWarning = false;
  let cookieWarning = false;
  let pending = [];
  let tag = null;
  const searches = new Set();
  try {
    const saved = localStorage.getItem(consentKey);
    if (saved === "granted" || saved === "denied") choice = saved;
  } catch {
    storageWarning = true;
    console.warn("LAMP GRID: analytics consent storage is unavailable.");
  }

  const banner = document.getElementById("analyticsChoice");
  const dialog = document.getElementById("privacyDialog");
  const status = document.getElementById("analyticsStatus");
  new ResizeObserver(() => {
    document.body.style.setProperty("--analytics-choice-height", (banner.getBoundingClientRect().height + 16) + "px");
  }).observe(banner);

  function updateStatus() {
    const messages = {
      unconfigured: "アクセス解析は未設定のため停止中です。Googleへの解析通信はありません。",
      idle: "アクセス解析はまだ許可されていません。",
      loading: "同意済みです。アクセス解析への接続を確認しています。",
      active: "同意済みです。個人のスコアを含まない操作情報をGoogle Analyticsへ送信します。",
      blocked: "解析に接続できません。通信制限・オフラインの可能性があります。アプリはそのまま使えます。"
    };
    status.textContent = available && choice === "denied"
      ? "アクセス解析は拒否されています。Googleへの解析通信はありません。"
      : messages[state];
    if (storageWarning) status.textContent += " 選択を保存できません。次回の解析設定の保持は保証できないため、設定を確認してください。";
    if (cookieWarning) status.textContent += " 解析用Cookieを削除できません。ブラウザのサイトデータ設定を確認してください。";
    banner.hidden = !available || choice !== "unknown";
    document.body.classList.toggle("has-analytics-choice", !banner.hidden);
    document.querySelectorAll("[data-analytics-choice='granted']").forEach(button => {
      button.disabled = !available;
    });
    document.querySelectorAll("[data-analytics-choice='denied']").forEach(button => {
      button.disabled = !available;
    });
  }

  function referrerOrigin() {
    if (!document.referrer) return "";
    try {
      const url = new URL(document.referrer);
      const knownOrigins = [
        "https://x.com", "https://t.co", "https://twitter.com", "https://github.com",
        "https://www.google.com", "https://www.google.co.jp", "https://www.bing.com"
      ];
      return knownOrigins.includes(url.origin) ? url.origin + "/" : "";
    } catch {
      console.warn("LAMP GRID: an invalid referrer was omitted.");
      return "";
    }
  }

  function campaign() {
    const params = new URLSearchParams(location.search);
    const name = params.get("utm_campaign");
    if (params.get("utm_source") !== "x" || params.get("utm_medium") !== "social"
      || !["launch", "update", "feedback", "share"].includes(name)) return {};
    return {campaign_source: "x", campaign_medium: "social", campaign_name: name};
  }

  function send(name, params) {
    if (choice !== "granted" || !available) return false;
    if (state === "active") {
      window.gtag("event", name, params);
      return true;
    }
    if (state === "loading" && pending.length < 50) {
      pending.push([name, params]);
      return true;
    }
    return false;
  }

  function track(name, params = {}) {
    const spec = Object.hasOwn(schema, name) ? schema[name] : null;
    if (!spec || !params || Object.keys(params).length !== Object.keys(spec).length
      || !Object.keys(params).every(key => Object.hasOwn(spec, key) && spec[key].includes(params[key]))) {
      console.warn("LAMP GRID: an analytics event outside the allowlist was rejected.");
      return false;
    }
    if (name === "search_use" && searches.has(params.context)) return false;
    const accepted = send(name, {...params});
    if (accepted && name === "search_use") searches.add(params.context);
    return accepted;
  }

  function start() {
    if (!available || choice !== "granted" || state === "loading" || state === "active") return;
    state = "loading";
    updateStatus();
    window["ga-disable-" + id] = false;
    window.dataLayer = [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("consent", "default", {
      analytics_storage: "denied", ad_storage: "denied",
      ad_user_data: "denied", ad_personalization: "denied"
    });
    window.gtag("consent", "update", {analytics_storage: "granted"});
    window.gtag("js", new Date());
    window.gtag("config", id, {
      send_page_view: false,
      page_location: canonical,
      page_referrer: referrerOrigin(),
      page_title: "LAMP GRID",
      cookie_prefix: "lampgrid",
      cookie_path: appPath,
      cookie_domain: "none",
      cookie_expires: 60 * 60 * 24 * 30,
      cookie_update: false,
      cookie_flags: "SameSite=Lax;Secure",
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      ...campaign()
    });
    pending = [["page_view", {page_location: canonical, page_referrer: referrerOrigin(), page_title: "LAMP GRID"}]];
    if (tag) tag.remove();
    tag = document.createElement("script");
    tag.async = true;
    tag.referrerPolicy = "no-referrer";
    tag.src = "https://www.googletagmanager.com/gtag/js?id=" + id;
    tag.onload = () => {
      if (choice !== "granted") return;
      state = "active";
      const events = pending;
      pending = [];
      events.forEach(([name, params]) => send(name, params));
      updateStatus();
    };
    tag.onerror = () => {
      state = "blocked";
      pending = [];
      console.warn("LAMP GRID: optional analytics could not connect.");
      updateStatus();
    };
    document.head.appendChild(tag);
  }

  function clearCookies() {
    try {
      document.cookie.split(";").forEach(cookie => {
        const name = cookie.split("=")[0].trim();
        if (name.startsWith(cookiePrefix)) {
          document.cookie = name + "=; Max-Age=0; path=" + appPath + "; SameSite=Lax";
        }
      });
      cookieWarning = document.cookie.split(";").some(cookie => cookie.trim().startsWith(cookiePrefix));
      if (cookieWarning) console.warn("LAMP GRID: analytics cookies remain after removal.");
    } catch {
      cookieWarning = true;
      console.warn("LAMP GRID: analytics cookies could not be removed.");
    }
  }

  function choose(value) {
    if (value !== "granted" && value !== "denied") return;
    if (value === "granted" && !available) return;
    const wasRunning = state === "active" || state === "loading" || state === "blocked";
    choice = value;
    try {
      localStorage.setItem(consentKey, value);
      storageWarning = false;
    } catch {
      storageWarning = true;
      console.warn("LAMP GRID: analytics consent could not be saved.");
    }
    if (value === "denied") {
      if (id) window["ga-disable-" + id] = true;
      pending = [];
      clearCookies();
      updateStatus();
      if (!storageWarning && !cookieWarning) {
        dialog.close();
        if (wasRunning) location.reload();
      }
      return;
    }
    start();
    updateStatus();
    if (!storageWarning) dialog.close();
  }

  document.querySelectorAll("[data-analytics-choice]").forEach(button => {
    button.addEventListener("click", () => choose(button.dataset.analyticsChoice));
  });
  window.addEventListener("storage", event => {
    if ((event.key === consentKey || event.key === null) && event.newValue !== "granted" && choice === "granted") {
      choose("denied");
    }
  });

  window.LampGridAnalytics = Object.freeze({track});
  updateStatus();
  if (choice === "granted") start();
})();
