import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { datadogRum } from "@datadog/browser-rum";
import { AuthProvider } from "@/context/AuthContext";
import App from "./App";
import "./index.css";

if (import.meta.env.VITE_DD_APPLICATION_ID && import.meta.env.VITE_DD_CLIENT_TOKEN) {
  datadogRum.init({
    applicationId: import.meta.env.VITE_DD_APPLICATION_ID,
    clientToken: import.meta.env.VITE_DD_CLIENT_TOKEN,
    site: import.meta.env.VITE_DD_SITE || "datadoghq.com",
    service: "nestswipe-frontend",
    env: import.meta.env.VITE_DD_ENV || "prod",
    sessionSampleRate: 100,
    sessionReplaySampleRate: 20,
    trackResources: true,
    trackUserInteractions: true,
    trackLongTasks: true,
    allowedTracingUrls: import.meta.env.VITE_DD_ALLOWED_TRACING_URL ? [import.meta.env.VITE_DD_ALLOWED_TRACING_URL] : [],
    defaultPrivacyLevel: "mask-user-input",
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: (failureCount, error) => {
        // Don't retry 4xx (client errors) except 408/429
        const status = (error as any)?.response?.status;
        if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) {
          return false;
        }
        // Retry 5xx / network errors up to 3 times
        return failureCount < 3;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
