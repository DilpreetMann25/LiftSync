/**
 * API client.
 *
 * One place that knows how to talk to the backend. Every component
 * calls these functions instead of fetch(), which means token
 * handling, error shaping, and URL construction exist once rather
 * than in twenty components that each get it slightly differently.
 *
 * Same instinct as app/analytics.py on the backend: keep the logic
 * out of the layer whose job is presentation.
 */

const TOKEN_KEY = "liftsync_token";

/**
 * NOTE ON TOKEN STORAGE
 * ---------------------
 * localStorage is readable by any JavaScript on the page, so a
 * cross-site-scripting bug would expose the token. The more secure
 * option is an httpOnly cookie, which JavaScript cannot read at all,
 * but that requires CSRF protection and backend cookie handling.
 *
 * localStorage is the standard choice for a bearer-token SPA and is
 * fine here. Worth knowing the tradeoff rather than not knowing there
 * is one.
 */
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

/** An HTTP error carrying the status code, so callers can branch on it. */
export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Turn FastAPI's error body into a single readable sentence.
 *
 * A 422 arrives as an array of per-field objects:
 *   [{loc: ["body","email"], msg: "value is not a valid email"}]
 * Showing that raw to a user is unacceptable, so it gets flattened.
 */
function describeError(status, body) {
  if (!body || !body.detail) return `Request failed (${status})`;

  if (typeof body.detail === "string") return body.detail;

  if (Array.isArray(body.detail)) {
    return body.detail
      .map((e) => {
        const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : "field";
        return `${field}: ${e.msg}`;
      })
      .join(" · ");
  }

  return `Request failed (${status})`;
}

async function request(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {};
  const token = tokenStore.get();

  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    // The login endpoint follows the OAuth2 spec, which requires
    // form encoding rather than JSON.
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const response = await fetch(path, { method, headers, body: payload });

  if (response.status === 204) return null;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    // An expired or invalid token means the session is over. Clearing
    // it here -- centrally -- is why no component has to think about
    // token expiry.
    if (response.status === 401 && auth) tokenStore.clear();
    throw new ApiError(response.status, describeError(response.status, data), data?.detail);
  }

  return data;
}

export const api = {
  register: (payload) =>
    request("/api/v1/auth/register", { method: "POST", body: payload, auth: false }),

  login: (email, password) =>
    request("/api/v1/auth/login", {
      method: "POST",
      // `username` not `email` -- fixed by the OAuth2 spec.
      form: { username: email, password },
      auth: false,
    }),

  me: () => request("/api/v1/auth/me"),

  exercises: () => request("/api/v1/exercises"),

  workouts: (limit = 30) => request(`/api/v1/workouts?limit=${limit}`),

  workout: (id) => request(`/api/v1/workouts/${id}`),

  createWorkout: (payload) =>
    request("/api/v1/workouts", { method: "POST", body: payload }),

  deleteWorkout: (id) => request(`/api/v1/workouts/${id}`, { method: "DELETE" }),

  plateaus: (stallWeeks = 3) =>
    request(`/api/v1/analytics/plateaus?stall_weeks=${stallWeeks}`),

  progression: (exerciseId, weeks = 12) =>
    request(`/api/v1/analytics/exercises/${exerciseId}/progression?weeks=${weeks}`),

  muscleVolume: (weeks = 8, muscleGroup) =>
    request(
      `/api/v1/analytics/muscle-volume?weeks=${weeks}` +
        (muscleGroup ? `&muscle_group=${encodeURIComponent(muscleGroup)}` : "")
    ),

  askCoach: (question) =>
    request("/api/v1/coach/ask", { method: "POST", body: { question } }),
};
