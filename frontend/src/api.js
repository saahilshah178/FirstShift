import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  // Media URLs are relative; the frontend prepends BACKEND_URL.
});

/** Build a full URL from a relative `/api/...` path returned by the backend. */
export function absoluteUrl(relativePath) {
  if (!relativePath) return relativePath;
  if (/^https?:\/\//i.test(relativePath)) return relativePath;
  return `${BACKEND_URL}${relativePath}`;
}
