import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { AuthProvider } from "./app/auth-context";
import { CaseProvider } from "./app/case-context";
import { router } from "./app/router";
import "./styles/index.css";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <CaseProvider>
          <RouterProvider router={router} />
        </CaseProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
