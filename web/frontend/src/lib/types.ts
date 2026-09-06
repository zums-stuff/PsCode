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

export interface ClassOut {
  id: number;
  name: string;
  code: string;
  teacher_id: number;
  anticheat_threshold: number;
}

export interface ClassMemberOut {
  user_id: number;
  username: string;
  role: string;
  joined_at: string;
}

export interface AssignmentListItem {
  id: number;
  problem_id: number;
  deadline: string;
  status: string;
  best_verdict: string | null;
  best_steps: number | null;
}

export interface AssignmentSubmissionOut {
  user_id: number;
  username: string;
  best_verdict: string | null;
  steps: number | null;
  source: string;
}

export interface ContestListItem {
  id: number;
  title: string;
  start_at: string;
  end_at: string;
  status: string;
  scoring_mode: string;
  teams_enabled: boolean;
  is_registered: boolean;
}

export interface Contest {
  id: number;
  title: string;
  start_at: string;
  end_at: string;
  scoring_mode: string;
  teams_enabled: boolean;
  created_by: number;
}

export interface ContestProblem {
  contest_id: number;
  problem_id: number;
  order: number;
  title: string;
}

export interface ContestTeam {
  id: number;
  contest_id: number;
  name: string;
  created_at: string;
}

export interface ContestTeamMember {
  team_id: number;
  user_id: number;
}

export interface ContestParticipant {
  user_id: number;
  username: string;
}

export interface ContestScoreboardRow {
  participant_id: string;
  rank: number;
  solves: number;
  penalty: number;
  points: number;
  total_ac_cases: number;
  problems: Record<
    string,
    {
      solved: boolean;
      solve_time_min: number;
      wrong_attempts: number;
      points: number;
      best_ac_cases: number;
      best_steps: number;
      best_submission_id: string | null;
    }
  >;
}

export interface RunOut {
  id: number;
  user_id: number;
  problem_id: number;
  kind: string;
  status: string;
  summary_verdict: string | null;
  steps: number | null;
  wall_ms: number | null;
  assignment_id: number | null;
  contest_id: number | null;
  created_at: string;
}

export interface TestResultOut {
  id: number;
  case_index: number;
  verdict: string;
  steps: number | null;
  wall_ms: number | null;
  output: string | null;
  error: string | null;
}

export interface RunDetailOut extends RunOut {
  test_results: TestResultOut[];
}

export interface ContestScoreboard {
  mode: string;
  rows: ContestScoreboardRow[];
}