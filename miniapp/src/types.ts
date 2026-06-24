export type MatchListType = "top" | "today" | "tomorrow" | "live";

export type Screen =
  | "home"
  | "matches"
  | "favorites"
  | "subscription"
  | "profile";

export interface MatchItem {
  id: string;
  home_id: number | null;
  away_id: number | null;
  home: string;
  away: string;
  home_logo: string | null;
  away_logo: string | null;
  league: string;
  league_id: number | null;
  league_logo: string | null;
  country: string;
  season: number | null;
  round: string;
  kickoff: string | null;
  status: string;
  score: {
    home: number | null;
    away: number | null;
  };
  source: string;
}

export interface MatchResponse {
  ok: boolean;
  items: MatchItem[];
  error?: string;
}

export interface SingleMatchResponse {
  ok: true;
  match: MatchItem;
}

export interface MatchLiveStatus {
  short: string;
  long: string;
  elapsed: number | null;
}

export interface MatchLiveScore {
  home: number | null;
  away: number | null;
}

export interface MatchLiveFixture {
  home: string;
  away: string;
  home_logo: string | null;
  away_logo: string | null;
  kickoff: string | null;
  league: string;
}

export interface MatchLiveEvent {
  time: number | null;
  extra: number | null;
  team_id: number | null;
  team_name: string;
  player: string;
  assist: string;
  type: string;
  detail: string;
  comments: string | null;
}

export interface MatchLiveResponse {
  ok: true;
  match_id: string;
  status: MatchLiveStatus;
  score: MatchLiveScore;
  fixture: MatchLiveFixture;
  events: MatchLiveEvent[];
  updated_at: string;
}

export interface MatchContextMatch {
  id: string;
  date: string | null;
  league: string;
  home: string;
  away: string;
  home_score: number | null;
  away_score: number | null;
  status: string;
}

export interface MatchStandingRow {
  rank: number;
  team_id: number | null;
  team: string;
  group: string;
  played: number | null;
  wins: number | null;
  draws: number | null;
  losses: number | null;
  goals_for: number | null;
  goals_against: number | null;
  goal_diff: number | null;
  points: number | null;
  description: string;
  status: string;
}

export interface MatchStatisticTeam {
  team_id: number | null;
  team_name: string;
  team_logo: string | null;
}

export interface MatchStatisticItem {
  type: string;
  label: string;
  home: string | null;
  away: string | null;
  home_value: number | null;
  away_value: number | null;
}

export interface MatchStatisticsBlock {
  available: boolean;
  home: MatchStatisticTeam | null;
  away: MatchStatisticTeam | null;
  items: MatchStatisticItem[];
}

export interface MatchLineupPlayer {
  id: number | null;
  name: string;
  number: number | null;
  pos: string;
  grid: string | null;
}

export interface MatchLineupCoach {
  id: number | null;
  name: string;
  photo: string | null;
}

export interface MatchLineupTeam {
  team_id: number | null;
  team_name: string;
  team_logo: string | null;
  formation: string;
  coach: MatchLineupCoach | null;
  start_xi: MatchLineupPlayer[];
  substitutes: MatchLineupPlayer[];
}

export interface MatchLineupsBlock {
  available: boolean;
  teams: MatchLineupTeam[];
}

export interface MatchAbsencePlayer {
  id: number | null;
  name: string;
  photo: string | null;
  type: string;
  reason: string;
}

export interface MatchAbsenceTeam {
  team_id: number | null;
  team_name: string;
  team_logo: string | null;
  players: MatchAbsencePlayer[];
}

export interface MatchAbsencesBlock {
  available: boolean;
  teams: MatchAbsenceTeam[];
}

export interface MatchContextResponse {
  ok: true;
  match_id: string;
  home: string;
  away: string;
  league: string;
  country: string;
  kickoff: string | null;
  match_group: string;
  statistics: MatchStatisticsBlock;
  lineups: MatchLineupsBlock;
  absences: MatchAbsencesBlock;
  standings: MatchStandingRow[];
  h2h: MatchContextMatch[];
  home_recent: MatchContextMatch[];
  away_recent: MatchContextMatch[];
  upcoming: MatchContextMatch[];
}

export interface MatchAiAnalysisResponse {
  ok: true;
  match_id: string;
  home: string;
  away: string;
  analysis: string;
  limit_charged: boolean;
  remaining_ai: number | null;
  is_admin: boolean;
  analysis_mode?: "default" | "premium";
  structured?: MatchAiStructuredAnalysis | null;
}

export interface MatchAiAnalysisSignal {
  label: string;
  value: string;
  confidence: "low" | "medium" | "high";
  reason: string;
}

export interface MatchAiStructuredAnalysis {
  summary: string;
  outcome_probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  signals: MatchAiAnalysisSignal[];
  context: string;
  form: string;
  lineups_and_absences: string;
  tactical_notes: string;
  risks: string[];
  scenario: string;
  disclaimer: string;
}

export interface MatchAiAnalysisErrorResponse {
  ok: false;
  error: string;
  message: string;
}

export interface TeamSearchItem {
  id: number;
  name: string;
  country: string;
  logo: string | null;
  founded: number | null;
  national: boolean;
  venue_name: string;
  venue_city: string;
  venue_capacity: number | null;
}

export interface TeamSearchResponse {
  ok: boolean;
  items: TeamSearchItem[];
  error?: string;
}

export interface TeamProfileResponse {
  ok: true;
  team: TeamSearchItem;
}

export interface TeamMatchesResponse {
  ok: true;
  recent: MatchItem[];
  upcoming: MatchItem[];
}

export interface TeamStandingsResponse {
  ok: boolean;
  league?: {
    id: number | null;
    name: string;
    country: string;
    logo: string | null;
    season: number | null;
  };
  team_id?: number;
  team_name?: string;
  standings?: MatchStandingRow[];
  error?: string;
  message?: string;
}

export interface FavoriteTeamItem {
  team_id: number;
  team_name: string;
  team_logo: string | null;
  team_country: string;
  created_at?: string;
}

export interface FavoriteTeamsResponse {
  ok: boolean;
  items: FavoriteTeamItem[];
  error?: string;
  message?: string;
}

export interface MatchReminderItem {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  kickoff: string;
  notify_at: string;
  is_sent: boolean;
}

export interface MatchRemindersResponse {
  ok: boolean;
  items: MatchReminderItem[];
  error?: string;
  message?: string;
}

export type MiniAppPaymentPackageCode =
  | "ai_30"
  | "month_1"
  | "months_3";

export interface PaymentReceiptResponse {
  ok: true;
  message: string;
  package_title: string;
  amount: number;
}

export interface PaymentReceiptErrorResponse {
  ok: false;
  error: string;
  message: string;
}

export interface SubscriptionData {
  ok: boolean;
  telegram_user_id: number;
  plan: "free" | "premium" | "admin";
  premium_until: string | null;
  ai_used_monthly: number;
  ai_limit_monthly: number;
  extra_ai_credits: number;
  usage_period: string;
  is_admin: boolean;
  auth_mode: string;
  ai_text?: string;
}

export interface PaymentPackage {
  code: string;
  title: string;
  price_kzt: number;
  ai_credits?: number;
  days?: number;
  ai_limit?: number;
}

export interface AppConfig {
  bot_username: string;
  free_ai_limit: number;
  packages: PaymentPackage[];
}
