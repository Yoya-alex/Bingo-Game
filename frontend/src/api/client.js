import { getAuthToken } from "../utils/auth.js";

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

  const response = await fetch(url, {
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
