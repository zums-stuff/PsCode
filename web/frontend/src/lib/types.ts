/** Shared API response shapes (mirrors web/api pydantic schemas). */

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
}

export interface ProblemListItem {
  id: number;
  title: string;
  expected_complexity: string;
  compare_mode: string;
  is_solved: boolean;
  best_verdict: string | null;
}

export interface ProblemOut {
  id: number;
  title: string;
  statement: string;
  expected_complexity: string;
  step_budget: number | null;
  compare_mode: string;
  author_id: number;
  created_at: string;
}

export interface TestCaseOut {
  id: number;
  problem_id: number;
  input: string;
  expected_output: string;
  seed: number;
  points: number;
  order: number;
  is_public: boolean;
  is_sample: boolean;
}

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

export interface ValidateResult {
  ok: boolean;
  errors: { code: string; message: string; line: number; col: number }[];
}