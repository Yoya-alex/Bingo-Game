const ACCESS_TOKEN_KEY = "bingo-access-token";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
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
  if (!token) {
    return path;
  }

  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(token)}`;
}
