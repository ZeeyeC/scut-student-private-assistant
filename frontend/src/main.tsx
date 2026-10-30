import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import {SchoolImportBridge} from "./SchoolImportBridge";
import "./style.css";
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {location.pathname.startsWith('/school-import/')?<SchoolImportBridge/>:<App />}
    </QueryClientProvider>
  </React.StrictMode>,
);
