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
    env: "production",
    sessionSampleRate: 100,
    sessionReplaySampleRate: 20,
    trackUserInteractions: true,
    trackResources: true,
    trackLongTasks: true,
    defaultPrivacyLevel: "mask-user-input",
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
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
