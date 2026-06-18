import { TEST_TELEGRAM_USER_ID } from "./config";

export type TelegramUserMode = "telegram" | "fallback";

export interface TelegramUserIdentity {
  id: number;
  mode: TelegramUserMode;
}

export function getTelegramUserIdentity(): TelegramUserIdentity {
  const telegramUserId =
    window.Telegram?.WebApp?.initDataUnsafe?.user?.id;

  if (
    typeof telegramUserId === "number" &&
    Number.isSafeInteger(telegramUserId) &&
    telegramUserId > 0
  ) {
    return {
      id: telegramUserId,
      mode: "telegram",
    };
  }

  return {
    id: TEST_TELEGRAM_USER_ID,
    mode: "fallback",
  };
}
