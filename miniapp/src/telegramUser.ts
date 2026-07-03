import { TEST_TELEGRAM_USER_ID } from "./config";

export type TelegramUserMode = "telegram" | "fallback";

export interface TelegramUserIdentity {
  id: number;
  mode: TelegramUserMode;
  sdkAvailable: boolean;
  initDataAvailable: boolean;
  displayName: string;
  username: string;
}

type TelegramInitDataUser = {
  id?: unknown;
  first_name?: unknown;
  last_name?: unknown;
  username?: unknown;
};

interface TelegramUserDetails {
  id: number;
  displayName: string;
  username: string;
}

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

function getOptionalString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function buildTelegramUserDetails(
  user: TelegramInitDataUser,
): TelegramUserDetails | null {
  if (!isValidTelegramUserId(user.id)) {
    return null;
  }

  const firstName = getOptionalString(user.first_name);
  const lastName = getOptionalString(user.last_name);

  return {
    id: user.id,
    displayName: [firstName, lastName].filter(Boolean).join(" "),
    username: getOptionalString(user.username),
  };
}

function getTelegramUserFromInitData(
  initData: string,
): TelegramUserDetails | null {
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
      return buildTelegramUserDetails(telegramUser);
    }
  } catch {
    return null;
  }

  return null;
}

export function getTelegramUserIdentity(): TelegramUserIdentity {
  const telegramWebApp = window.Telegram?.WebApp;
  const initData = telegramWebApp?.initData?.trim() || "";
  const unsafeUser = telegramWebApp?.initDataUnsafe?.user;
  const telegramUser =
    (unsafeUser ? buildTelegramUserDetails(unsafeUser) : null) ||
    getTelegramUserFromInitData(initData);
  const diagnostics = {
    sdkAvailable: Boolean(telegramWebApp),
    initDataAvailable: Boolean(initData),
  };

  if (telegramUser !== null) {
    return {
      ...telegramUser,
      mode: "telegram",
      ...diagnostics,
    };
  }

  return {
    id: TEST_TELEGRAM_USER_ID,
    mode: "fallback",
    displayName: "MatchLab User",
    username: "",
    ...diagnostics,
  };
}

export function getTelegramStartParam() {
  const telegramWebApp = window.Telegram?.WebApp;
  const unsafeStartParam =
    typeof telegramWebApp?.initDataUnsafe?.start_param === "string"
      ? telegramWebApp.initDataUnsafe.start_param.trim()
      : "";
  if (unsafeStartParam) return unsafeStartParam;

  try {
    const initData = telegramWebApp?.initData?.trim() || "";
    const initDataStartParam = new URLSearchParams(initData)
      .get("start_param")
      ?.trim();
    if (initDataStartParam) return initDataStartParam;

    return (
      new URLSearchParams(window.location.search).get("startapp")?.trim() ||
      ""
    );
  } catch {
    return "";
  }
}
