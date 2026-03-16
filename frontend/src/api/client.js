import { getAuthToken } from "../utils/auth.js";

export async function fetchJson(url, options = {}) {
  const token = getAuthToken();
  const mergedHeaders = {
    ...(options.headers || {}),
  };

  if (token) {
    mergedHeaders["X-User-Token"] = token;
    mergedHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    cache: "no-store",
    headers: mergedHeaders,
    ...options,
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
