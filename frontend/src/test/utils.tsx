import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";

interface WrapperOptions {
  initialEntries?: string[];
  token?: string;
}

export function renderWithProviders(
  ui: React.ReactElement,
  { initialEntries = ["/"], token, ...renderOptions }: WrapperOptions & Omit<RenderOptions, "wrapper"> = {},
) {
  // Seed localStorage token before AuthProvider reads it
  if (token) {
    localStorage.setItem("nestswipe_token", token);
  } else {
    localStorage.removeItem("nestswipe_token");
  }

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <AuthProvider>{children}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper, ...renderOptions }), queryClient };
}
