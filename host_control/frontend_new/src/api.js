const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://192.168.1.32:8000";

async function handleResponse(res) {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  return handleResponse(res);
}

async function postJson(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse(res);
}

export const api = {
  baseUrl: API_BASE,

  getStatus: () => getJson("/api/status"),
  getEvents: () => getJson("/api/events"),

  setMode: (mode) => postJson("/api/mode", { mode }),
  setMotor: (speed) => postJson("/api/motor", { speed }),
  setServo: (angle) => postJson("/api/servo", { angle }),
  setDrive: (speed, angle) => postJson("/api/drive", { speed, angle }),
  stop: () => postJson("/api/stop"),
  setTelem: (enabled, period_ms = 200) =>
    postJson("/api/telem", { enabled, period_ms }),

  getCameraStatus: () => getJson("/api/camera/status"),
  getPerceptionStatus: () => getJson("/api/perception/status"),

  enableAssisted: () => postJson("/api/assisted/enable"),
  disableAssisted: () => postJson("/api/assisted/disable"),
};