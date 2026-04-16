import { getAuthToken } from "../utils/auth.js";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function withApiBase(url) {
  if (!API_BASE_URL) {
    return url;
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  return `${API_BASE_URL}${url.startsWith("/") ? url : `/${url}`}`;
}

export async function fetchJson(url, options = {}) {
  const token = getAuthToken();
  const baseHeaders = {
    ...(options.headers || {}),
  };
  
  if (token) {
    baseHeaders["X-User-Token"] = token;
    baseHeaders.Authorization = `Bearer ${token}`;
  }

  const mergedHeaders = {
    ...baseHeaders,
  };

  const response = await fetch(withApiBase(url), {
    ...options,
    cache: "no-store",
    headers: mergedHeaders,
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const message = data?.error || "Request failed";
    throw new Error(message);
  }
  return data;
}

export async function postJson(url, body) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
