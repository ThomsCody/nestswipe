import "@testing-library/jest-dom/vitest";

beforeEach(() => {
  // AuthProvider sends same-origin presence heartbeats; tests never contact a VM.
  vi.stubGlobal("fetch", async () => new Response(null, { status: 204 }));
});

afterEach(() => vi.unstubAllGlobals());
