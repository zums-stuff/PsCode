import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireAuth, RequireRole } from "./lib/auth";
import Login from "./routes/Login";
import Register from "./routes/Register";
import Forbidden from "./routes/Forbidden";
import NotFound from "./routes/NotFound";
import StudentLayout from "./routes/StudentLayout";
import Problems from "./routes/student/Problems";
import Placeholder from "./routes/student/Placeholder";
import Solve from "./routes/Solve";
import Submissions from "./routes/Submissions";
import ProblemResults from "./routes/ProblemResults";
import Contest from "./routes/Contest";
import AdminLayout from "./routes/admin/AdminLayout";
import AdminProblems from "./routes/admin/AdminProblems";
import AdminProblemDetail from "./routes/admin/AdminProblemDetail";
import AdminClasses from "./routes/admin/AdminClasses";
import AdminClassDetail from "./routes/admin/AdminClassDetail";
import AdminAssignmentNew from "./routes/admin/AdminAssignmentNew";
import AdminAssignmentDetail from "./routes/admin/AdminAssignmentDetail";
import AdminContests from "./routes/admin/AdminContests";
import AdminContestNew from "./routes/admin/AdminContestNew";
import AdminContestDetail from "./routes/admin/AdminContestDetail";

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
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/403" element={<Forbidden />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <StudentLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Problems />} />
              <Route path="problem/:id" element={<Solve />} />
              <Route path="problem/:id/results" element={<ProblemResults />} />
              <Route path="practice" element={<Placeholder i18nKey="student.practice" />} />
              <Route path="submissions" element={<Submissions />} />
              <Route path="forum" element={<Placeholder i18nKey="student.forum" />} />
              <Route path="contests" element={<Placeholder i18nKey="student.contests" />} />
              <Route path="contest/:id" element={<Contest />} />
            </Route>
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
              <Route path="classes" element={<AdminClasses />} />
              <Route path="classes/new" element={<AdminClassDetail />} />
              <Route path="classes/:id" element={<AdminClassDetail />} />
              <Route
                path="classes/:id/assignments/new"
                element={<AdminAssignmentNew />}
              />
              <Route path="assignments/:id" element={<AdminAssignmentDetail />} />
              <Route path="contests" element={<AdminContests />} />
              <Route path="contests/new" element={<AdminContestNew />} />
              <Route path="contests/:id" element={<AdminContestDetail />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}