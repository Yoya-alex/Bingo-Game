const ACCESS_TOKEN_KEY = "bingo-access-token";
const LANGUAGE_KEY = "bingo-language";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

function getCurrentLanguage() {
  if (typeof window === "undefined") {
    return "";
  }

  const params = new URLSearchParams(window.location.search || "");
  const fromUrl = (params.get("lang") || params.get("language") || "").trim();
  if (fromUrl) {
    return fromUrl;
  }

  if (!canUseStorage()) {
    return "";
  }

  return (window.sessionStorage.getItem(LANGUAGE_KEY) || "").trim();
}

export function bootstrapAuthToken() {
  if (typeof window === "undefined") {
    return "";
  }

  const params = new URLSearchParams(window.location.search || "");
  const tokenFromUrl = (params.get("token") || "").trim();
  if (tokenFromUrl && canUseStorage()) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, tokenFromUrl);
    return tokenFromUrl;
  }

  if (!canUseStorage()) {
    return "";
  }

  return (window.sessionStorage.getItem(ACCESS_TOKEN_KEY) || "").trim();
}

export function getAuthToken() {
  return bootstrapAuthToken();
}

export function withAuthPath(path) {
  const token = getAuthToken();
  const language = getCurrentLanguage();
  const [basePath, hash = ""] = String(path || "").split("#", 2);
  const [pathname, rawQuery = ""] = basePath.split("?", 2);
  const params = new URLSearchParams(rawQuery);

  if (token && !params.has("token")) {
    params.set("token", token);
  }

  if (language && !params.has("lang") && !params.has("language")) {
    params.set("lang", language);
  }

  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}${hash ? `#${hash}` : ""}`;
}
