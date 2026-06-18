export type MatchListType = "top" | "today" | "tomorrow";

export type Screen = "home" | "matches" | "subscription" | "profile";

export interface MatchItem {
  id: string;
  home: string;
  away: string;
  home_logo: string | null;
  away_logo: string | null;
  league: string;
  league_logo: string | null;
  country: string;
  kickoff: string | null;
  source: string;
}

export interface MatchResponse {
  ok: boolean;
  items: MatchItem[];
  error?: string;
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
}

export interface MatchAiAnalysisErrorResponse {
  ok: false;
  error: string;
  message: string;
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
