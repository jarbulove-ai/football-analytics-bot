import { API_BASE_URL } from "./config";
import type {
  AppConfig,
  MatchListType,
  MatchResponse,
  SubscriptionData,
} from "./types";

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
