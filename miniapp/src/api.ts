import { API_BASE_URL } from "./config";
import type {
  AppConfig,
  MatchAiAnalysisErrorResponse,
  MatchAiAnalysisResponse,
  MatchContextResponse,
  MatchListType,
  MatchResponse,
  MiniAppPaymentPackageCode,
  PaymentReceiptErrorResponse,
  PaymentReceiptResponse,
  SubscriptionData,
  TeamMatchesResponse,
  TeamProfileResponse,
  TeamSearchResponse,
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

export class PaymentReceiptError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "PaymentReceiptError";
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

export function getMatchContext(
  matchId: string,
): Promise<MatchContextResponse> {
  return apiRequest<MatchContextResponse>(
    `/api/matches/${encodeURIComponent(matchId)}/context`,
  );
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

export function searchTeams(query: string): Promise<TeamSearchResponse> {
  return apiRequest<TeamSearchResponse>(
    `/api/teams/search?q=${encodeURIComponent(query.trim())}`,
  );
}

export function getTeamProfile(
  teamId: number,
): Promise<TeamProfileResponse> {
  return apiRequest<TeamProfileResponse>(
    `/api/teams/${encodeURIComponent(teamId)}`,
  );
}

export function getTeamMatches(
  teamId: number,
): Promise<TeamMatchesResponse> {
  return apiRequest<TeamMatchesResponse>(
    `/api/teams/${encodeURIComponent(teamId)}/matches`,
  );
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

export async function submitPaymentReceipt(
  telegramUserId: number,
  packageCode: MiniAppPaymentPackageCode,
  receiptFile: File,
): Promise<PaymentReceiptResponse> {
  const formData = new FormData();
  formData.append("telegram_user_id", String(telegramUserId));
  formData.append("package_code", packageCode);
  formData.append("receipt_file", receiptFile);

  const response = await fetch(`${API_BASE_URL}/api/payments/request`, {
    method: "POST",
    headers: {
      "X-Telegram-Init-Data":
        window.Telegram?.WebApp?.initData || "",
    },
    body: formData,
  });
  const responseData: unknown = await response.json();

  if (!response.ok) {
    const errorData = responseData as PaymentReceiptErrorResponse;
    throw new PaymentReceiptError(
      response.status,
      errorData.error || "unknown_error",
      errorData.message || "Не удалось отправить чек. Попробуйте позже.",
    );
  }

  return responseData as PaymentReceiptResponse;
}
