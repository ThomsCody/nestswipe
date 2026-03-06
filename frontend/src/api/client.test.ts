import client from "./client";
import type { InternalAxiosRequestConfig, AxiosResponse, AxiosHeaders } from "axios";

const TOKEN_KEY = "nestswipe_token";

// Extract the registered interceptor handlers by walking the manager internals.
// Cast through `unknown` to satisfy strict TS without accessing typed `.handlers`.
function getRequestHandler() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mgr = client.interceptors.request as any;
  const entry = (mgr.handlers as { fulfilled: (cfg: InternalAxiosRequestConfig) => InternalAxiosRequestConfig }[])[0]!;
  return entry.fulfilled;
}

function getResponseRejectedHandler() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mgr = client.interceptors.response as any;
  const entry = (mgr.handlers as { rejected: (err: unknown) => Promise<never> }[])[0]!;
  return entry.rejected;
}

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "location", {
    writable: true,
    value: { href: "/" },
  });
});

describe("API client request interceptor", () => {
  it("adds Authorization header when token exists", () => {
    localStorage.setItem(TOKEN_KEY, "my-jwt");
    const handler = getRequestHandler();
    const config = handler({ headers: {} as AxiosHeaders } as InternalAxiosRequestConfig);
    expect(config.headers.Authorization).toBe("Bearer my-jwt");
  });

  it("does not add Authorization header when no token", () => {
    const handler = getRequestHandler();
    const config = handler({ headers: {} as AxiosHeaders } as InternalAxiosRequestConfig);
    expect(config.headers.Authorization).toBeUndefined();
  });
});

describe("API client response interceptor", () => {
  it("clears token and redirects to /login on 401", async () => {
    localStorage.setItem(TOKEN_KEY, "my-jwt");
    const rejected = getResponseRejectedHandler();
    const error = { response: { status: 401 } as AxiosResponse };
    await expect(rejected(error)).rejects.toBe(error);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.location.href).toBe("/login");
  });

  it("does not clear token on non-401 errors", async () => {
    localStorage.setItem(TOKEN_KEY, "my-jwt");
    const rejected = getResponseRejectedHandler();
    const error = { response: { status: 500 } as AxiosResponse };
    await expect(rejected(error)).rejects.toBe(error);
    expect(localStorage.getItem(TOKEN_KEY)).toBe("my-jwt");
  });
});
