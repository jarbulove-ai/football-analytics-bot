import { API_BASE_URL } from "./config";
import type {
  AppConfig,
  MatchAiAnalysisErrorResponse,
  MatchAiAnalysisResponse,
  MatchListType,
  MatchResponse,
  SubscriptionData,
} from "./types";

export class MatchAiAnalysisError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "MatchAiAnalysisError";
    this.status = status;
    this.code = code;
  }
}

async function apiRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getMatches(type: MatchListType): Promise<MatchResponse> {
  return apiRequest<MatchResponse>(`/api/matches/${type}`);
}

export function getSubscription(
  telegramUserId: number,
): Promise<SubscriptionData> {
  return apiRequest<SubscriptionData>(
    `/api/subscription?telegram_user_id=${telegramUserId}`,
  );
}

export function getAppConfig(): Promise<AppConfig> {
  return apiRequest<AppConfig>("/api/config");
}

export async function requestMatchAiAnalysis(
  matchId: string,
  telegramUserId: number,
): Promise<MatchAiAnalysisResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/matches/${encodeURIComponent(matchId)}/ai`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Telegram-Init-Data":
          window.Telegram?.WebApp?.initData || "",
      },
      body: JSON.stringify({
        telegram_user_id: telegramUserId,
      }),
    },
  );

  const responseData: unknown = await response.json();
  if (!response.ok) {
    const errorData = responseData as MatchAiAnalysisErrorResponse;
    throw new MatchAiAnalysisError(
      response.status,
      errorData.error || "unknown_error",
      errorData.message || "AI-разбор временно недоступен.",
    );
  }

  return responseData as MatchAiAnalysisResponse;
}
