import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireRole } from "./lib/auth";
import Login from "./routes/Login";
import Register from "./routes/Register";
import Forbidden from "./routes/Forbidden";
import NotFound from "./routes/NotFound";
import AdminLayout from "./routes/admin/AdminLayout";
import AdminProblems from "./routes/admin/AdminProblems";
import AdminProblemDetail from "./routes/admin/AdminProblemDetail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/admin/problems" replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/403" element={<Forbidden />} />
            <Route
              path="/admin"
              element={
                <RequireRole roles={["teacher", "admin"]}>
                  <AdminLayout />
                </RequireRole>
              }
            >
              <Route index element={<Navigate to="/admin/problems" replace />} />
              <Route path="problems" element={<AdminProblems />} />
              <Route path="problems/new" element={<AdminProblemDetail />} />
              <Route path="problems/:id" element={<AdminProblemDetail />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}