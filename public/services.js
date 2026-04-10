const isLocalFile = window.location.protocol === "file:";
const isLocalFrontendOnly =
  ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
  window.location.port !== "" &&
  window.location.port !== "8000";

const API_BASE = isLocalFile || isLocalFrontendOnly ? "http://127.0.0.1:8000" : "";

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData
      ? { ...(options.headers || {}) }
      : {
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

export const api = {
  health() {
    return request("/api/health");
  },
  getDemoData() {
    return request("/api/demo-data");
  },
  loadData(body) {
    return request("/api/data/load", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  uploadExcel(formData) {
    return request("/api/data/upload-excel", {
      method: "POST",
      body: formData,
    });
  },
  uploadWorkbook(formData) {
    return request("/api/data/upload-workbook", {
      method: "POST",
      body: formData,
    });
  },
  buildGraph(body) {
    return request("/api/graph/build", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  runDijkstra(body) {
    return request("/api/dijkstra/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  getAlternatives(body) {
    return request("/api/routes/alternatives", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  evaluateMcdm(body) {
    return request("/api/mcdm/evaluate", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  runHybrid(body) {
    return request("/api/hybrid/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
