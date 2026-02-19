const authTokenStorageKey = "aemet.api_access_token";
const authTokenExpiryStorageKey = "aemet.api_access_token_expires_at";
const authLastActivityStorageKey = "aemet.api_last_activity_ms";
const inputTimezoneStorageKey = "aemet.input_timezone";
const authInactivityLimitMs = 60 * 60 * 1000;
const authRefreshThresholdSeconds = 15 * 60;
const authRefreshCooldownMs = 2 * 60 * 1000;
const authRecentActivityForRefreshMs = 5 * 60 * 1000;
const activityWriteThrottleMs = 15 * 1000;

let refreshInFlight: Promise<boolean> | null = null;
let lastRefreshAttemptMs = 0;
let lastActivityWriteMs = 0;
let sessionManagerStarted = false;

function nowEpochSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function tokenExpiryFromStorage(): number | null {
  const rawExpiry = localStorage.getItem(authTokenExpiryStorageKey);
  if (!rawExpiry) return null;
  const expiry = Number(rawExpiry);
  return Number.isFinite(expiry) ? expiry : null;
}

function authTokenFromStorage(): string | null {
  const token = localStorage.getItem(authTokenStorageKey);
  const expiry = tokenExpiryFromStorage();
  if (!token || expiry == null) return null;
  if (expiry <= nowEpochSeconds()) {
    clearAuthToken();
    return null;
  }
  return token;
}

function requestWithAuth(options?: RequestInit): RequestInit {
  const request = { ...(options ?? {}) };
  const headers = new Headers(request.headers ?? {});
  const token = authTokenFromStorage();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  request.headers = headers;
  return request;
}

function notifyAuthRequired(): void {
  window.dispatchEvent(new CustomEvent("auth:required"));
}

function readLastActivityMs(): number | null {
  const raw = localStorage.getItem(authLastActivityStorageKey);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function writeLastActivityMs(nowMs: number): void {
  localStorage.setItem(authLastActivityStorageKey, String(nowMs));
}

function isInactivityExpired(nowMs: number): boolean {
  const lastActivityMs = readLastActivityMs();
  if (lastActivityMs == null) return false;
  return nowMs - lastActivityMs > authInactivityLimitMs;
}

export function recordAuthActivity(force = false): void {
  if (!authTokenFromStorage()) return;
  const nowMs = Date.now();
  if (!force && nowMs - lastActivityWriteMs < activityWriteThrottleMs) return;
  lastActivityWriteMs = nowMs;
  writeLastActivityMs(nowMs);
}

async function refreshAuthTokenIfNeeded(): Promise<boolean> {
  const token = authTokenFromStorage();
  if (!token) return false;

  const nowMs = Date.now();
  if (isInactivityExpired(nowMs)) {
    clearAuthToken();
    notifyAuthRequired();
    return false;
  }

  const expiry = tokenExpiryFromStorage();
  if (expiry == null) return false;
  const lastActivityMs = readLastActivityMs();
  if (lastActivityMs == null) return false;
  if (nowMs - lastActivityMs > authRecentActivityForRefreshMs) return false;
  const remainingSeconds = expiry - nowEpochSeconds();
  if (remainingSeconds > authRefreshThresholdSeconds) return false;
  if (nowMs - lastRefreshAttemptMs < authRefreshCooldownMs) return false;
  if (refreshInFlight) return refreshInFlight;

  lastRefreshAttemptMs = nowMs;
  refreshInFlight = (async () => {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      if (response.status === 401) {
        clearAuthToken();
        notifyAuthRequired();
      }
      return false;
    }
    const payload = await response.json().catch(() => null);
    if (!payload || typeof payload !== "object") return false;
    const nextToken = (payload as { accessToken?: unknown }).accessToken;
    const expiresIn = (payload as { expiresInSeconds?: unknown }).expiresInSeconds;
    if (typeof nextToken !== "string" || typeof expiresIn !== "number") return false;
    saveAuthToken(nextToken, expiresIn, false);
    return true;
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

function parseErrorDetail(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return "Request failed";
}

export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  if (!url.includes("/api/auth/token") && !url.includes("/api/auth/refresh")) {
    await refreshAuthTokenIfNeeded();
    recordAuthActivity();
  }
  const response = await fetch(url, requestWithAuth(options));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !url.includes("/api/auth/token")) {
      clearAuthToken();
      notifyAuthRequired();
    }
    throw new Error(parseErrorDetail(payload));
  }
  return payload as T;
}

export async function fetchBlob(url: string, options?: RequestInit): Promise<Response> {
  if (!url.includes("/api/auth/token") && !url.includes("/api/auth/refresh")) {
    await refreshAuthTokenIfNeeded();
    recordAuthActivity();
  }
  const response = await fetch(url, requestWithAuth(options));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      clearAuthToken();
      notifyAuthRequired();
    }
    throw new Error(parseErrorDetail(payload));
  }
  return response;
}

export function saveAuthToken(token: string, expiresInSeconds: number, touchActivity = true): void {
  const ttl = Math.max(30, Math.floor(expiresInSeconds));
  localStorage.setItem(authTokenStorageKey, token);
  localStorage.setItem(authTokenExpiryStorageKey, String(nowEpochSeconds() + ttl));
  if (touchActivity) writeLastActivityMs(Date.now());
}

export function clearAuthToken(): void {
  localStorage.removeItem(authTokenStorageKey);
  localStorage.removeItem(authTokenExpiryStorageKey);
  localStorage.removeItem(authLastActivityStorageKey);
}

export function hasValidAuthToken(): boolean {
  return authTokenFromStorage() != null;
}

export function startAuthSessionManager(): void {
  if (sessionManagerStarted) return;
  sessionManagerStarted = true;

  const onActivity = (): void => {
    recordAuthActivity();
    void refreshAuthTokenIfNeeded();
  };
  const activityEvents = ["pointerdown", "keydown", "wheel", "touchstart", "scroll"];
  for (const eventName of activityEvents) {
    window.addEventListener(eventName, onActivity, { passive: true });
  }

  window.setInterval(() => {
    if (!hasValidAuthToken()) return;
    const nowMs = Date.now();
    if (isInactivityExpired(nowMs)) {
      clearAuthToken();
      notifyAuthRequired();
      return;
    }
    void refreshAuthTokenIfNeeded();
  }, 30_000);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!hasValidAuthToken()) return;
    const nowMs = Date.now();
    if (isInactivityExpired(nowMs)) {
      clearAuthToken();
      notifyAuthRequired();
      return;
    }
    recordAuthActivity(true);
    void refreshAuthTokenIfNeeded();
  });
}

export function toApiDateTime(value: string): string {
  if (!value) return "";
  return value.length === 16 ? `${value}:00` : value;
}

function configuredDisplayTimeZone(fallback = "UTC"): string {
  const stored = localStorage.getItem(inputTimezoneStorageKey)?.trim();
  if (stored && isValidTimeZone(stored)) return stored;
  const browser = browserTimeZone();
  return isValidTimeZone(browser) ? browser : fallback;
}

export function formatDateTime(value: string | null, timeZone = configuredDisplayTimeZone()): string {
  if (!value) return "n/a";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(dt);
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const precision = Number.isFinite(digits) ? Math.min(6, Math.max(0, Math.trunc(digits))) : 2;
  return new Intl.NumberFormat(undefined, {
    useGrouping: true,
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value);
}

export function browserTimeZone(): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return zone && zone.trim() ? zone : "UTC";
}

export function isValidTimeZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}

export function toDateTimeLocalInZone(date: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const read = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${read("year")}-${read("month")}-${read("day")}T${read("hour")}:${read("minute")}:${read("second")}`;
}
