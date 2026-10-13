const REDIRECT_ORIGIN = "https://redirect.invalid";
const AUTH_PATHS = new Set([
  "/login", "/register", "/forgot-password", "/reset-password",
]);
// eslint-disable-next-line no-control-regex -- URL normalization must not conceal control characters.
const UNSAFE_PATH_CHARACTERS = /[\\\u0000-\u001f\u007f]/;

// Only accept local destinations, and never send authentication back to itself.
export function safeRedirectPath(value) {
  if (typeof value !== "string" || !value.startsWith("/") ||
      value.startsWith("//") || UNSAFE_PATH_CHARACTERS.test(value)) return "/";

  try {
    const url = new URL(value, REDIRECT_ORIGIN);
    const decodedPath = decodeURIComponent(url.pathname);
    if (url.origin !== REDIRECT_ORIGIN || decodedPath.startsWith("//") ||
        UNSAFE_PATH_CHARACTERS.test(decodedPath)) return "/";

    const path = new URL(decodedPath, REDIRECT_ORIGIN).pathname
      .replace(/\/+$/, "").toLowerCase();
    if (AUTH_PATHS.has(path)) return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}

export function getAuthRedirect(search) {
  return safeRedirectPath(new URLSearchParams(search).get("redirect"));
}

export function buildAuthLink(authPath, returnTo) {
  const redirect = safeRedirectPath(returnTo);
  return redirect === "/" ? authPath :
    `${authPath}?${new URLSearchParams({ redirect })}`;
}

export function getLocationPath(location) {
  return `${location.pathname}${location.search}${location.hash}`;
}
