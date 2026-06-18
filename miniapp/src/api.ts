import { API_BASE_URL, TEST_TELEGRAM_USER_ID } from "./config";
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

export function getSubscription(): Promise<SubscriptionData> {
  return apiRequest<SubscriptionData>(
    `/api/subscription?telegram_user_id=${TEST_TELEGRAM_USER_ID}`,
  );
}

export function getAppConfig(): Promise<AppConfig> {
  return apiRequest<AppConfig>("/api/config");
}
