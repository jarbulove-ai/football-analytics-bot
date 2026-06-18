import { TEST_TELEGRAM_USER_ID } from "./config";

export type TelegramUserMode = "telegram" | "fallback";

export interface TelegramUserIdentity {
  id: number;
  mode: TelegramUserMode;
  sdkAvailable: boolean;
  initDataAvailable: boolean;
}

type TelegramInitDataUser = {
  id?: unknown;
};

function isValidTelegramUserId(value: unknown): value is number {
  if (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value > 0
  ) {
    return true;
  }

  return false;
}

function getTelegramUserIdFromInitData(initData: string): number | null {
  try {
    const params = new URLSearchParams(initData);
    const rawUser = params.get("user");
    if (!rawUser) {
      return null;
    }

    const parsedUser: unknown = JSON.parse(rawUser);
    if (
      typeof parsedUser === "object" &&
      parsedUser !== null &&
      "id" in parsedUser
    ) {
      const telegramUser = parsedUser as TelegramInitDataUser;
      return isValidTelegramUserId(telegramUser.id)
        ? telegramUser.id
        : null;
    }
  } catch {
    return null;
  }

  return null;
}

export function getTelegramUserIdentity(): TelegramUserIdentity {
  const telegramWebApp = window.Telegram?.WebApp;
  const initData = telegramWebApp?.initData?.trim() || "";
  const unsafeUserId = telegramWebApp?.initDataUnsafe?.user?.id;
  const telegramUserId = isValidTelegramUserId(unsafeUserId)
    ? unsafeUserId
    : getTelegramUserIdFromInitData(initData);
  const diagnostics = {
    sdkAvailable: Boolean(telegramWebApp),
    initDataAvailable: Boolean(initData),
  };

  if (telegramUserId !== null) {
    return {
      id: telegramUserId,
      mode: "telegram",
      ...diagnostics,
    };
  }

  return {
    id: TEST_TELEGRAM_USER_ID,
    mode: "fallback",
    ...diagnostics,
  };
}
