import { renderHook, act } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";

const TOKEN_KEY = "nestswipe_token";

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

beforeEach(() => {
  localStorage.clear();
});

describe("AuthContext", () => {
  it("reads token from localStorage on mount", () => {
    localStorage.setItem(TOKEN_KEY, "saved-token");
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.token).toBe("saved-token");
  });

  it("starts with null token when localStorage is empty", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.token).toBeNull();
  });

  it("login stores token in state and localStorage", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => result.current.login("new-token"));
    expect(result.current.token).toBe("new-token");
    expect(localStorage.getItem(TOKEN_KEY)).toBe("new-token");
  });

  it("logout clears token from state and localStorage", () => {
    localStorage.setItem(TOKEN_KEY, "existing-token");
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => result.current.logout());
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("useAuth throws when used outside AuthProvider", () => {
    // Suppress console.error for the expected error
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within AuthProvider",
    );
    spy.mockRestore();
  });
});
