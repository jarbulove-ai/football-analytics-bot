import {
  Activity,
  ArrowLeft,
  Bell,
  Bot,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CircleUserRound,
  Copy,
  Crown,
  FileText,
  Gift,
  Home,
  LoaderCircle,
  RefreshCw,
  Search,
  Share2,
  ShieldCheck,
  Sparkles,
  Star,
  Trophy,
  Upload,
  WalletCards,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addMatchReminder,
  addFavoriteTeam,
  getAppConfig,
  getFavoriteTeams,
  getMatch,
  getMatchContext,
  getMatchLive,
  getMatchReminders,
  getMatches,
  getReferralStatus,
  getSavedMatchAiAnalysis,
  getSubscription,
  getTeamMatches,
  getTeamProfile,
  getTeamStandings,
  MatchAiAnalysisError,
  PaymentReceiptError,
  requestMatchAiAnalysis,
  removeFavoriteTeam,
  removeMatchReminder,
  searchTeams,
  submitPaymentReceipt,
  trackMiniappEvent,
} from "./api";
import { getTelegramStartParam, getTelegramUserIdentity } from "./telegramUser";
import type {
  AppConfig,
  FavoriteTeamItem,
  MatchAbsencePlayer,
  MatchAiAnalysisSignal,
  MatchAiAnalysisSuccessResponse,
  MatchAiStructuredAnalysis,
  MatchContextMatch,
  MatchContextResponse,
  MatchItem,
  MatchLiveEvent,
  MatchLiveResponse,
  MatchLineupPlayer,
  MatchLineupTeam,
  MatchListType,
  MatchReminderItem,
  MatchStatisticItem,
  MatchStandingRow,
  MiniAppPaymentPackageCode,
  PaymentPackage,
  PaymentReceiptResponse,
  ReferralStatus,
  Screen,
  SubscriptionData,
  TeamMatchesResponse,
  TeamSearchItem,
  TeamStandingsResponse,
} from "./types";

const matchTabs: Array<{ id: MatchListType; label: string }> = [
  { id: "top", label: "Топ" },
  { id: "today", label: "Сегодня" },
  { id: "tomorrow", label: "Завтра" },
  { id: "live", label: "Live" },
];

const ONBOARDING_STORAGE_KEY = "matchlab_onboarding_seen";

type MatchDetailTab =
  | "details"
  | "live"
  | "statistics"
  | "lineups"
  | "ai"
  | "table"
  | "matches";
type MatchesView = "matches" | "leagues";
type TournamentTab = "overview" | "matches" | "standings" | "bracket";
type TeamDetailTab = "details" | "matches" | "standings";
type FavoriteTab = "teams" | "matches" | "reminders";

interface TournamentSelection {
  league: string;
  country: string;
  leagueLogo: string | null;
  matches: MatchItem[];
}

interface FavoriteTeamMatchesGroup {
  team: FavoriteTeamItem;
  matches: MatchItem[];
}

const matchDetailTabs: Array<{ id: MatchDetailTab; label: string }> = [
  { id: "details", label: "Детали" },
  { id: "live", label: "Live" },
  { id: "statistics", label: "Статистика" },
  { id: "lineups", label: "Составы" },
  { id: "ai", label: "AI-разбор" },
  { id: "table", label: "Таблица" },
  { id: "matches", label: "Матчи" },
];

const navigation = [
  { id: "home" as Screen, label: "Главная", icon: Home },
  { id: "matches" as Screen, label: "Матчи", icon: Activity },
  { id: "favorites" as Screen, label: "Избранное", icon: Star },
  { id: "subscription" as Screen, label: "Подписка", icon: Crown },
  { id: "profile" as Screen, label: "Профиль", icon: CircleUserRound },
];

function formatKickoff(value: string | null) {
  if (!value) {
    return { date: "Дата уточняется", time: "--:--" };
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { date: "Дата уточняется", time: "--:--" };
  }

  return {
    date: new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "short",
    }).format(date),
    time: new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date),
  };
}

function formatReminderKickoff(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Время уточняется";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPrice(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function canSetMatchReminder(match: MatchItem) {
  if (isFinishedMatchStatus(match.status)) return false;
  if (isLiveMatchStatus(match.status)) return true;
  if (!match.kickoff) return false;
  const kickoffTime = new Date(match.kickoff).getTime();
  return Number.isFinite(kickoffTime) && kickoffTime > Date.now();
}

function buildOptimisticMatchReminder(match: MatchItem): MatchReminderItem {
  const kickoff = match.kickoff || "";
  const kickoffTime = new Date(kickoff).getTime();

  return {
    match_id: match.id,
    home_team: match.home,
    away_team: match.away,
    league: match.league,
    kickoff,
    notify_at: new Date(kickoffTime - 60 * 60 * 1000).toISOString(),
    is_sent: false,
  };
}

function buildMiniappMatchEventData(
  match: MatchItem,
  source: string,
): Record<string, unknown> {
  return {
    match_id: match.id,
    home: match.home,
    away: match.away,
    league: match.league,
    source,
  };
}

function formatContextMatchDate(value: string | null) {
  if (!value) {
    return "Дата уточняется";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Дата уточняется";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function hasNumericMatchScore(
  homeScore: number | null,
  awayScore: number | null,
) {
  return typeof homeScore === "number" && typeof awayScore === "number";
}

function formatMatchStatus(status: string, hasScore: boolean) {
  const normalizedStatus = status.trim().toLocaleUpperCase("en-US");

  if (
    ["FT", "AET", "PEN"].includes(normalizedStatus) ||
    /FINISHED|MATCH FINISHED/.test(normalizedStatus)
  ) {
    return "Матч завершён";
  }

  if (
    ["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"].includes(
      normalizedStatus,
    ) ||
    /LIVE|IN PROGRESS/.test(normalizedStatus)
  ) {
    return "Идёт матч";
  }

  if (["PST", "POSTPONED"].includes(normalizedStatus)) {
    return "Матч перенесён";
  }

  if (["CANC", "CANCELLED"].includes(normalizedStatus)) {
    return "Матч отменён";
  }

  if (["SUSP", "SUSPENDED"].includes(normalizedStatus)) {
    return "Матч приостановлен";
  }

  if (["ABD", "ABANDONED"].includes(normalizedStatus)) {
    return "Матч прерван";
  }

  if (
    ["NS", "TBD", "SCHEDULED", "NOT STARTED"].includes(normalizedStatus)
  ) {
    return "Матч ожидается";
  }

  if (status.trim()) {
    return status.trim();
  }

  return hasScore ? "Счёт матча" : "Матч ожидается";
}

function isLiveMatchStatus(status: string) {
  const normalizedStatus = status.trim().toLocaleUpperCase("en-US");
  return (
    ["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"].includes(
      normalizedStatus,
    ) || /LIVE|IN PROGRESS/.test(normalizedStatus)
  );
}

function isFinishedMatchStatus(status: string) {
  const normalizedStatus = status.trim().toLocaleUpperCase("en-US");
  return (
    ["FT", "AET", "PEN"].includes(normalizedStatus) ||
    /FINISHED|MATCH FINISHED/.test(normalizedStatus)
  );
}

function normalizeTeamLabel(value: string) {
  return value.trim().toLocaleLowerCase("ru-RU");
}

function groupStandingsByGroup(rows: MatchStandingRow[]) {
  const groups = new Map<string, MatchStandingRow[]>();

  rows.forEach((row) => {
    const groupName = row.group.trim() || "Турнирная таблица";
    const groupRows = groups.get(groupName) || [];
    groupRows.push(row);
    groups.set(groupName, groupRows);
  });

  return Array.from(groups.entries());
}

function getStandingZoneStyle(description: string) {
  const normalizedDescription = description.trim().toLocaleLowerCase("en-US");

  if (
    /promotion|play[\s-]?offs?|qualification/.test(normalizedDescription)
  ) {
    return {
      rowClass: "border-l-2 border-l-lime bg-lime/[0.035]",
      dotClass: "bg-lime",
    };
  }

  if (/relegation/.test(normalizedDescription)) {
    return {
      rowClass: "border-l-2 border-l-red-400 bg-red-500/[0.035]",
      dotClass: "bg-red-400",
    };
  }

  return {
    rowClass: "",
    dotClass: "bg-slate-500",
  };
}

function isKnockoutLikeTournament(leagueName: string) {
  const normalizedName = leagueName.trim().toLocaleLowerCase("ru-RU");
  const knockoutTournamentTerms = [
    "world cup",
    "champions league",
    "europa league",
    "conference league",
    "cup",
    "кубок",
    "лига чемпионов",
    "лига европы",
    "лига конференций",
  ];

  return knockoutTournamentTerms.some((term) =>
    normalizedName.includes(term),
  );
}

function getRelevantMatchStandings(
  rows: MatchStandingRow[],
  matchGroup: string,
) {
  const groupNames = new Set(
    rows.map((row) => row.group.trim()).filter(Boolean),
  );
  const normalizedMatchGroup = matchGroup.trim().toLocaleLowerCase("en-US");

  if (groupNames.size <= 1 || !normalizedMatchGroup) {
    return rows;
  }

  const filteredRows = rows.filter(
    (row) =>
      row.group.trim().toLocaleLowerCase("en-US") === normalizedMatchGroup,
  );

  return filteredRows.length > 0 ? filteredRows : rows;
}

function getTeamRelevantStandingsRows(
  rows: MatchStandingRow[],
  teamId: number | undefined,
  teamName: string,
) {
  const selectedRow =
    (typeof teamId === "number"
      ? rows.find((row) => row.team_id === teamId)
      : undefined) ||
    rows.find(
      (row) =>
        normalizeTeamLabel(row.team) === normalizeTeamLabel(teamName),
    );
  const groupName = selectedRow?.group.trim() || "";

  if (!groupName) {
    return { rows, groupName: "" };
  }

  const normalizedGroupName = groupName.toLocaleLowerCase("ru-RU");
  const groupRows = rows.filter(
    (row) =>
      row.group.trim().toLocaleLowerCase("ru-RU") === normalizedGroupName,
  );

  return {
    rows: groupRows.length > 0 ? groupRows : rows,
    groupName: groupRows.length > 0 ? groupName : "",
  };
}

function TeamLogo({
  logo,
  name,
  size = "md",
}: {
  logo: string | null;
  name: string;
  size?: "xs" | "sm" | "md" | "lg";
}) {
  const sizeClass = {
    xs: "h-7 w-7 text-[10px]",
    sm: "h-8 w-8 text-xs",
    md: "h-11 w-11 text-sm",
    lg: "h-16 w-16 text-lg",
  }[size];

  if (logo) {
    return (
      <div className={`${sizeClass} relative shrink-0`}>
        <img
          src={logo}
          alt=""
          className="absolute inset-0 h-full w-full scale-125 object-contain opacity-45 blur-md"
          aria-hidden="true"
        />
        <img
          src={logo}
          alt=""
          className="relative h-full w-full object-contain drop-shadow-[0_4px_10px_rgba(0,0,0,0.55)]"
          loading="lazy"
        />
      </div>
    );
  }

  return (
    <div
      className={`${sizeClass} flex shrink-0 items-center justify-center rounded-full border border-white/10 bg-panelSoft font-bold text-white`}
      aria-hidden="true"
    >
      {(name.trim()[0] || "?").toUpperCase()}
    </div>
  );
}

function LeagueLogo({
  logo,
  name,
}: {
  logo: string | null;
  name: string;
}) {
  if (logo) {
    return (
      <img
        src={logo}
        alt=""
        className="h-6 w-6 object-contain"
        loading="lazy"
      />
    );
  }

  return (
    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-white/5">
      <Trophy className="h-3.5 w-3.5 text-white/60" />
      <span className="sr-only">{name}</span>
    </div>
  );
}

function AppHeader({ compact = false }: { compact?: boolean }) {
  return (
    <header className={compact ? "mb-5" : "mb-7"}>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white shadow-card">
          <Activity className="h-5 w-5" />
        </div>
        <div>
          <p className="text-xl font-extrabold tracking-normal text-white">
            MatchLab
          </p>
          <p className="text-xs text-slate-400">
            AI-разбор футбольных матчей
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 rounded-full border border-lime/20 bg-lime/10 px-2.5 py-1 text-[11px] font-semibold text-lime">
          <span className="h-1.5 w-1.5 rounded-full bg-lime" />
          Online
        </div>
      </div>
    </header>
  );
}

function HomeScreen({
  onNavigate,
  onOpenDailyMatches,
  favoriteTeams,
  matchReminders,
  reminderMatchIds,
  reminderLoadingIds,
  remindersLoading,
  onToggleReminder,
  onOpenMatch,
  onOpenReminder,
}: {
  onNavigate: (screen: Screen) => void;
  onOpenDailyMatches: () => void;
  favoriteTeams: FavoriteTeamItem[];
  matchReminders: MatchReminderItem[];
  reminderMatchIds: Set<string>;
  reminderLoadingIds: Set<string>;
  remindersLoading: boolean;
  onToggleReminder: (match: MatchItem) => void;
  onOpenMatch: (match: MatchItem) => void;
  onOpenReminder: (reminder: MatchReminderItem) => void;
}) {
  const [favoriteMatches, setFavoriteMatches] = useState<MatchItem[]>([]);
  const [favoriteMatchesLoading, setFavoriteMatchesLoading] = useState(false);
  const [favoriteMatchesError, setFavoriteMatchesError] = useState("");
  const favoriteTeamsToLoad = useMemo(
    () => favoriteTeams.slice(0, 3),
    [favoriteTeams],
  );
  const favoriteTeamsKey = favoriteTeamsToLoad
    .map((team) => team.team_id)
    .join(",");
  const nearestReminder = useMemo(
    () =>
      [...matchReminders]
        .filter((reminder) => {
          const kickoffTime = new Date(reminder.kickoff).getTime();
          return (
            Number.isFinite(kickoffTime) &&
            kickoffTime > Date.now()
          );
        })
        .sort(
          (left, right) =>
            new Date(left.kickoff).getTime() -
            new Date(right.kickoff).getTime(),
        )[0] || null,
    [matchReminders],
  );

  useEffect(() => {
    if (!favoriteTeamsKey) {
      setFavoriteMatches([]);
      setFavoriteMatchesError("");
      setFavoriteMatchesLoading(false);
      return;
    }

    let active = true;
    setFavoriteMatches([]);
    setFavoriteMatchesError("");
    setFavoriteMatchesLoading(true);

    Promise.allSettled(
      favoriteTeamsToLoad.map((team) => getTeamMatches(team.team_id)),
    )
      .then((results) => {
        if (!active) return;

        const successfulResponses = results.flatMap((result) =>
          result.status === "fulfilled" ? [result.value] : [],
        );
        const uniqueMatches = new Map<string, MatchItem>();

        successfulResponses.forEach((response) => {
          response.upcoming.forEach((match) => {
            uniqueMatches.set(match.id, match);
          });
        });

        const sortedMatches = sortMatchesByImportance(
          Array.from(uniqueMatches.values()),
        ).slice(0, 3);

        setFavoriteMatches(sortedMatches);
        if (successfulResponses.length === 0) {
          setFavoriteMatchesError(
            "Матчи избранных команд временно недоступны.",
          );
        }
      })
      .finally(() => {
        if (active) setFavoriteMatchesLoading(false);
      });

    return () => {
      active = false;
    };
  }, [favoriteTeamsKey]);

  const productFeatures = [
    {
      title: "Матчи",
      caption: "Сегодня, завтра и топ-игры",
      icon: Activity,
      iconClass: "bg-accent/15 text-accent",
      action: () => onNavigate("matches"),
    },
    {
      title: "Избранное",
      caption: "Команды, матчи и напоминания",
      icon: Star,
      iconClass: "bg-lime/10 text-lime",
      action: () => onNavigate("favorites"),
    },
    {
      title: "AI-разбор",
      caption: "Аналитика по матчу",
      icon: Bot,
      iconClass: "bg-violet-500/15 text-violet-300",
      action: () => onNavigate("matches"),
    },
    {
      title: "Premium",
      caption: "Больше AI-разборов",
      icon: Crown,
      iconClass: "bg-gold/10 text-gold",
      action: () => onNavigate("subscription"),
    },
  ];

  return (
    <div className="animate-rise">
      <section className="relative overflow-hidden border-b border-line pb-8 pt-2">
        <div className="flex items-center justify-between">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-white shadow-card">
            <Activity className="h-5 w-5" />
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-lime/20 bg-lime/10 px-2.5 py-1 text-[11px] font-semibold text-lime">
            <span className="h-1.5 w-1.5 rounded-full bg-lime" />
            Online
          </div>
        </div>

        <div className="mt-7 max-w-md">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-slate-500">
            <Sparkles className="h-4 w-4 text-lime" />
            Футбольная аналитика
          </div>
          <h1 className="text-4xl font-black text-white">MatchLab</h1>
          <p className="mt-2 text-lg font-bold text-slate-200">
            AI-разбор футбольных матчей
          </p>
          <p className="mt-4 max-w-sm text-sm leading-6 text-slate-400">
            Смотри матчи дня, сценарии игры, риски и краткую AI-аналитику в
            одном месте.
          </p>
        </div>

        <div className="mt-6">
          <button
            type="button"
            onClick={onOpenDailyMatches}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm font-bold text-white shadow-card transition active:scale-[0.98]"
          >
            <Activity className="h-4 w-4" />
            Открыть матчи дня
          </button>
        </div>
      </section>

      <section className="py-7">
        <div className="mb-4">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">
              Возможности
            </p>
            <h2 className="mt-1 text-xl font-extrabold text-white">
              Всё важное рядом
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {productFeatures.map(
            ({ title, caption, icon: Icon, iconClass, action }) => (
              <button
                key={title}
                type="button"
                onClick={action}
                className="group min-h-32 rounded-lg border border-line bg-panel p-4 text-left shadow-card transition duration-200 hover:border-white/15 active:scale-[0.98]"
              >
                <div className="flex items-start justify-between">
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-lg ${iconClass}`}
                  >
                    <Icon className="h-4.5 w-4.5" />
                  </span>
                  <ChevronRight className="h-4 w-4 text-slate-600 transition group-hover:text-slate-300" />
                </div>
                <span className="mt-4 block text-sm font-bold text-white">
                  {title}
                </span>
                <span className="mt-1 block text-xs leading-5 text-slate-400">
                  {caption}
                </span>
              </button>
            ),
          )}
        </div>
      </section>

      <section className="border-t border-line py-6">
        <div className="mb-3 flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">
              Персональное
            </p>
            <h2 className="mt-1 text-base font-bold text-white">
              Ближайшее напоминание
            </h2>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("favorites")}
            className="shrink-0 text-xs font-semibold text-accent"
          >
            Все
          </button>
        </div>

        {remindersLoading ? (
          <div className="flex min-h-24 items-center justify-center rounded-lg border border-line bg-panel">
            <LoaderCircle className="h-5 w-5 animate-spin text-accent" />
          </div>
        ) : nearestReminder ? (
          <button
            type="button"
            onClick={() => onOpenReminder(nearestReminder)}
            disabled={reminderLoadingIds.has(nearestReminder.match_id)}
            className="flex w-full items-center gap-3 rounded-lg border border-line bg-panel p-4 text-left shadow-card transition hover:border-white/15 active:scale-[0.99] disabled:cursor-wait disabled:opacity-60"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-lime/10 text-lime">
              {reminderLoadingIds.has(nearestReminder.match_id) ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Bell className="h-4 w-4" fill="currentColor" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold text-white">
                {nearestReminder.home_team} — {nearestReminder.away_team}
              </span>
              <span className="mt-0.5 block truncate text-xs text-slate-500">
                {nearestReminder.league || "Турнир не указан"}
              </span>
              <span className="mt-1 block text-[11px] font-semibold text-slate-300">
                {formatReminderKickoff(nearestReminder.kickoff)}
              </span>
              <span className="mt-0.5 block text-[10px] text-slate-500">
                Уведомление за 1 час до матча
              </span>
            </span>
            <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" />
          </button>
        ) : (
          <div className="rounded-lg border border-line bg-panel px-4 py-5">
            <p className="text-sm leading-6 text-slate-400">
              Включите 🔔 на будущем матче, чтобы получить напоминание.
            </p>
          </div>
        )}
      </section>

      <section className="border-t border-line py-6">
        <div className="mb-3 flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">
              Избранное
            </p>
            <h2 className="mt-1 text-base font-bold text-white">
              Матчи избранных команд
            </h2>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("favorites")}
            className="shrink-0 text-xs font-semibold text-accent"
          >
            Все избранные
          </button>
        </div>

        {favoriteMatchesLoading ? (
          <div className="space-y-3">
            <MatchSkeleton />
          </div>
        ) : favoriteMatchesError ? (
          <div className="rounded-lg border border-line bg-panel px-4 py-5">
            <p className="text-sm text-slate-400">{favoriteMatchesError}</p>
          </div>
        ) : favoriteTeams.length === 0 ? (
          <div className="rounded-lg border border-line bg-panel px-4 py-5">
            <p className="text-sm leading-6 text-slate-400">
              Добавьте команду в избранное, чтобы видеть её ближайшие матчи.
            </p>
          </div>
        ) : favoriteMatches.length === 0 ? (
          <div className="rounded-lg border border-line bg-panel px-4 py-5">
            <p className="text-sm leading-6 text-slate-400">
              Пока нет ближайших матчей избранных команд.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-line bg-panel">
            {favoriteMatches.map((match) => (
              <CompactMatchRow
                key={match.id}
                match={match}
                onOpen={onOpenMatch}
                reminderActive={reminderMatchIds.has(match.id)}
                reminderLoading={
                  remindersLoading || reminderLoadingIds.has(match.id)
                }
                onToggleReminder={onToggleReminder}
              />
            ))}
          </div>
        )}
      </section>

      <section className="border-t border-line pb-2 pt-6">
        <div className="mb-4 flex items-center gap-2">
          <Zap className="h-5 w-5 text-gold" />
          <h2 className="text-base font-bold text-white">Как пользоваться</h2>
        </div>
        <div className="space-y-4">
          {[
            "Откройте матч",
            "Посмотрите детали и таблицу",
            "Включите 🔔 или откройте AI-разбор",
          ].map((text, index) => (
            <div key={text} className="flex items-center gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-panelSoft text-xs font-bold text-lime">
                {index + 1}
              </span>
              <p className="text-sm text-slate-300">{text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function MatchSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="h-6 w-6 animate-pulseSoft rounded-full bg-white/10" />
        <div className="h-3 w-36 animate-pulseSoft rounded bg-white/10" />
      </div>
      <div className="flex items-center gap-3 px-4 py-4">
        <div className="h-8 w-10 animate-pulseSoft rounded bg-white/10" />
        <div className="flex-1 space-y-3">
          <div className="h-3 w-32 animate-pulseSoft rounded bg-white/10" />
          <div className="h-3 w-28 animate-pulseSoft rounded bg-white/10" />
        </div>
      </div>
    </div>
  );
}

function CompactMatchRow({
  match,
  onOpen,
  reminderActive,
  reminderLoading,
  onToggleReminder,
}: {
  match: MatchItem;
  onOpen: (match: MatchItem) => void;
  reminderActive: boolean;
  reminderLoading: boolean;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const kickoff = formatKickoff(match.kickoff);
  const hasScore =
    typeof match.score?.home === "number" &&
    typeof match.score?.away === "number";
  const isLive = isLiveMatchStatus(match.status);
  const reminderAvailable = canSetMatchReminder(match);

  return (
    <div className="flex items-stretch border-t border-line/80 transition hover:bg-white/[0.035]">
      <button
        type="button"
        onClick={() => onOpen(match)}
        className="grid min-w-0 flex-1 grid-cols-[3.25rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left active:bg-white/[0.06]"
      >
        <div>
          <p className="text-sm font-bold text-white">{kickoff.time}</p>
          <p className="mt-0.5 text-[10px] text-slate-500">{kickoff.date}</p>
        </div>
        <div className="min-w-0 space-y-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <TeamLogo logo={match.home_logo} name={match.home} size="xs" />
            <p className="truncate text-sm font-semibold text-white">
              {match.home || "Хозяева"}
            </p>
          </div>
          <div className="flex min-w-0 items-center gap-2.5">
            <TeamLogo logo={match.away_logo} name={match.away} size="xs" />
            <p className="truncate text-sm font-semibold text-white">
              {match.away || "Гости"}
            </p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {isLive && (
            <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[9px] font-black text-red-200">
              LIVE
            </span>
          )}
          <span className="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
            {hasScore ? `${match.score.home}:${match.score.away}` : "Детали"}
          </span>
        </div>
      </button>
      {reminderAvailable && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleReminder(match);
          }}
          disabled={reminderLoading}
          className={`mr-3 self-center flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition active:scale-95 disabled:cursor-wait disabled:opacity-60 ${
            reminderActive
              ? "bg-lime/15 text-lime"
              : "bg-white/[0.05] text-slate-500 hover:text-white"
          }`}
          aria-label={
            reminderActive
              ? "Удалить напоминание о матче"
              : "Напомнить за 1 час до матча"
          }
        >
          {reminderLoading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Bell
              className="h-4 w-4"
              fill={reminderActive ? "currentColor" : "none"}
            />
          )}
        </button>
      )}
    </div>
  );
}

function formatAlmatyKickoff(value: string | null) {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Almaty",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getMatchKickoffTime(match: MatchItem) {
  if (!match.kickoff) return Number.POSITIVE_INFINITY;
  const kickoffTime = new Date(match.kickoff).getTime();
  return Number.isFinite(kickoffTime)
    ? kickoffTime
    : Number.POSITIVE_INFINITY;
}

function matchTextIncludes(text: string, keywords: string[]) {
  return keywords.some((keyword) => text.includes(keyword));
}

function getMatchLeagueImportance(match: MatchItem): number {
  const searchableText = [
    match.league,
    match.country,
    match.round,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("ru-RU");

  if (!searchableText) return 30;

  if (
    matchTextIncludes(searchableText, [
      "fifa world cup",
      "world cup",
      "чемпионат мира",
      "кубок мира",
      "чм",
    ])
  ) {
    return 100;
  }

  if (
    matchTextIncludes(searchableText, [
      "uefa champions league",
      "champions league",
      "лига чемпионов",
    ])
  ) {
    return 90;
  }

  if (
    matchTextIncludes(searchableText, [
      "uefa euro",
      "euro",
      "copa america",
      "africa cup",
      "asian cup",
      "кубок африки",
      "кубок азии",
    ])
  ) {
    return 85;
  }

  if (
    matchTextIncludes(searchableText, [
      "kazakhstan premier league",
      "казахстанская премьер-лига",
      "премьер-лига казахстана",
      "казахстан",
      "кпл",
    ])
  ) {
    return 25;
  }

  if (
    matchTextIncludes(searchableText, [
      "premier league",
      "epl",
      "la liga",
      "serie a",
      "bundesliga",
      "ligue 1",
    ])
  ) {
    return 80;
  }

  if (
    matchTextIncludes(searchableText, [
      "europa league",
      "conference league",
      "лига европы",
      "лига конференций",
    ])
  ) {
    return 75;
  }

  if (
    matchTextIncludes(searchableText, [
      "international",
      "national teams",
      "сборные",
      "сборная",
    ])
  ) {
    return 70;
  }

  return 40;
}

function sortMatchesByImportance(matches: MatchItem[]): MatchItem[] {
  return [...matches].sort((left, right) => {
    const importanceDiff =
      getMatchLeagueImportance(right) - getMatchLeagueImportance(left);
    if (importanceDiff !== 0) return importanceDiff;

    return getMatchKickoffTime(left) - getMatchKickoffTime(right);
  });
}

function getDailyFocusReason(match: MatchItem) {
  if (isLiveMatchStatus(match.status)) {
    return "Матч уже идёт: удобно быстро открыть детали и live-сценарий.";
  }

  if (match.league) {
    return `Матч из турнира ${match.league}: можно быстро проверить форму команд, мотивацию и AI-разбор.`;
  }

  return "";
}

function getDailyFocusIntrigue(match: MatchItem) {
  if (isLiveMatchStatus(match.status)) {
    return "Интрига: текущий счёт может быстро изменить сценарий игры.";
  }

  if (match.round) {
    return `Этап: ${match.round}`;
  }

  return "";
}

function DailyFocusMatchCard({
  match,
  index,
  premiumAiEnabled,
  onOpenMatch,
}: {
  match: MatchItem;
  index: number;
  premiumAiEnabled: boolean;
  onOpenMatch: (match: MatchItem) => void;
}) {
  const almatyTime = formatAlmatyKickoff(match.kickoff);
  const focusReason = getDailyFocusReason(match);
  const intrigue = getDailyFocusIntrigue(match);
  const aiButtonText = premiumAiEnabled
    ? "Открыть Premium AI-разбор"
    : "Открыть базовый AI-разбор";

  return (
    <article
      className="animate-rise rounded-lg border border-line bg-panel p-4 shadow-card"
      style={{ animationDelay: `${Math.min(index * 55, 220)}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {match.league && (
            <p className="truncate text-xs font-semibold uppercase text-slate-500">
              {match.league}
            </p>
          )}
          <div className="mt-3 rounded-md bg-white/[0.025] px-3 py-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <TeamLogo logo={match.home_logo} name={match.home} size="sm" />
              <p className="truncate text-base font-extrabold text-white">
                {match.home || "Хозяева"}
              </p>
            </div>
            <div className="my-2 h-px bg-line/70" />
            <div className="flex min-w-0 items-center gap-2.5">
              <TeamLogo logo={match.away_logo} name={match.away} size="sm" />
              <p className="truncate text-base font-extrabold text-white">
                {match.away || "Гости"}
              </p>
            </div>
          </div>
        </div>
        {almatyTime && (
          <span className="shrink-0 rounded-md bg-white/[0.06] px-2.5 py-1.5 text-xs font-bold text-slate-200">
            {almatyTime} Алматы
          </span>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {match.round && (
          <p className="text-xs leading-5 text-slate-500">
            Этап: {match.round}
          </p>
        )}
        {focusReason && (
          <div className="rounded-md bg-white/[0.035] px-3 py-2">
            <p className="text-[10px] font-bold uppercase text-slate-500">
              Почему в фокусе
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-300">
              {focusReason}
            </p>
          </div>
        )}
        {intrigue && intrigue !== match.round && (
          <div className="rounded-md border border-amber-400/15 bg-amber-400/[0.035] px-3 py-2">
            <p className="text-[10px] font-bold uppercase text-amber-200/70">
              Интрига
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-300">
              {intrigue}
            </p>
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={() => onOpenMatch(match)}
        className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm font-bold text-white transition active:scale-[0.98]"
      >
        <Bot className="h-4 w-4" />
        {aiButtonText}
      </button>
      {!premiumAiEnabled && (
        <p className="mt-2 text-center text-[11px] text-slate-500">
          Глубокий разбор доступен в Premium
        </p>
      )}
    </article>
  );
}

type TeamScenarioTier = "top" | "strong" | "regular";
type DailyScenarioKind = "readable" | "balanced" | "bold";

interface DailyScenarioItem {
  kind: DailyScenarioKind;
  badge: string;
  title: string;
  explanation: string;
  match: MatchItem;
}

const TOP_TEAMS = new Set(
  [
    "Argentina",
    "Brazil",
    "France",
    "England",
    "Spain",
    "Portugal",
    "Germany",
    "Netherlands",
    "Belgium",
    "Croatia",
    "Italy",
    "Real Madrid",
    "Barcelona",
    "Liverpool",
    "Man City",
    "Manchester City",
    "Arsenal",
    "Bayern",
    "PSG",
    "Chelsea",
    "Man United",
    "Manchester United",
    "Аргентина",
    "Бразилия",
    "Франция",
    "Англия",
    "Испания",
    "Португалия",
    "Германия",
    "Нидерланды",
    "Бельгия",
    "Хорватия",
    "Италия",
  ].map((team) => team.toLocaleLowerCase("ru-RU")),
);

const STRONG_TEAMS = new Set(
  [
    "Morocco",
    "Colombia",
    "Uruguay",
    "Switzerland",
    "Denmark",
    "Senegal",
    "USA",
    "Mexico",
    "Japan",
    "Norway",
    "Sweden",
    "Ghana",
    "Austria",
    "Serbia",
    "Poland",
    "Turkey",
    "Egypt",
    "Algeria",
    "Ecuador",
    "Paraguay",
    "Марокко",
    "Колумбия",
    "Уругвай",
    "Швейцария",
    "Дания",
    "Сенегал",
    "США",
    "Мексика",
    "Япония",
    "Норвегия",
    "Швеция",
    "Гана",
    "Австрия",
    "Египет",
    "Алжир",
    "Эквадор",
    "Парагвай",
  ].map((team) => team.toLocaleLowerCase("ru-RU")),
);

const DAILY_SCENARIO_META: Record<
  DailyScenarioKind,
  Omit<DailyScenarioItem, "kind" | "match">
> = {
  readable: {
    badge: "🎯",
    title: "Понятный сценарий",
    explanation:
      "Самый читаемый матч дня: статус команд и турнирный контекст дают понятную интригу.",
  },
  balanced: {
    badge: "⚖️",
    title: "Сбалансированный сценарий",
    explanation:
      "Матч с несколькими сильными сигналами, но без полного преимущества одной стороны.",
  },
  bold: {
    badge: "🔥",
    title: "Смелый сценарий",
    explanation:
      "Больше неопределённости: сценарий может зависеть от темпа, первого гола и деталей состава.",
  },
};

function normalizeScenarioTeamName(teamName: string) {
  return teamName.trim().replace(/\s+/g, " ").toLocaleLowerCase("ru-RU");
}

function getTeamScenarioTier(teamName: string): TeamScenarioTier {
  const normalized = normalizeScenarioTeamName(teamName);
  if (TOP_TEAMS.has(normalized)) return "top";
  if (STRONG_TEAMS.has(normalized)) return "strong";
  return "regular";
}

function getScenarioTieBreaker(match: MatchItem) {
  let score = 0;
  if (isLiveMatchStatus(match.status)) score += 6;
  if (match.league) score += 4;
  if (match.round) score += 2;
  if (match.kickoff) score += 1;
  return score;
}

function scoreReadableScenario(match: MatchItem): number {
  const tiers = [
    getTeamScenarioTier(match.home),
    getTeamScenarioTier(match.away),
  ];
  const hasTop = tiers.includes("top");
  const hasRegular = tiers.includes("regular");
  const hasStrong = tiers.includes("strong");

  if (hasTop && hasRegular) return 90 + getScenarioTieBreaker(match);
  if (hasTop && hasStrong) return 78 + getScenarioTieBreaker(match);
  return 0;
}

function scoreBalancedScenario(match: MatchItem): number {
  const tiers = [
    getTeamScenarioTier(match.home),
    getTeamScenarioTier(match.away),
  ];
  const topCount = tiers.filter((tier) => tier === "top").length;
  const strongCount = tiers.filter((tier) => tier === "strong").length;

  if (topCount === 2) return 92 + getScenarioTieBreaker(match);
  if (topCount === 1 && strongCount === 1) {
    return 82 + getScenarioTieBreaker(match);
  }
  if (strongCount === 2) return 72 + getScenarioTieBreaker(match);
  return 0;
}

function scoreBoldScenario(match: MatchItem): number {
  const tiers = [
    getTeamScenarioTier(match.home),
    getTeamScenarioTier(match.away),
  ];
  const regularCount = tiers.filter((tier) => tier === "regular").length;
  const strongCount = tiers.filter((tier) => tier === "strong").length;

  if (regularCount === 2) return 90 + getScenarioTieBreaker(match);
  if (regularCount === 1 && strongCount === 1) {
    return 82 + getScenarioTieBreaker(match);
  }
  if (regularCount === 1) return 62 + getScenarioTieBreaker(match);
  return 0;
}

function pickDailyScenarioMatch(
  matches: MatchItem[],
  scoreMatch: (match: MatchItem) => number,
) {
  let selectedMatch: MatchItem | null = null;
  let selectedScore = 0;

  matches.forEach((match) => {
    const score = scoreMatch(match);
    if (score > selectedScore) {
      selectedMatch = match;
      selectedScore = score;
    }
  });

  return selectedMatch;
}

function buildDailyScenarioMatches(matches: MatchItem[]): DailyScenarioItem[] {
  const pool = [...matches];
  const items: DailyScenarioItem[] = [];
  const scenarioOrder: Array<{
    kind: DailyScenarioKind;
    scoreMatch: (match: MatchItem) => number;
  }> = [
    { kind: "readable", scoreMatch: scoreReadableScenario },
    { kind: "balanced", scoreMatch: scoreBalancedScenario },
    { kind: "bold", scoreMatch: scoreBoldScenario },
  ];

  scenarioOrder.forEach(({ kind, scoreMatch }) => {
    if (pool.length === 0) return;

    const selectedMatch = pickDailyScenarioMatch(pool, scoreMatch) || pool[0];
    const selectedIndex = pool.findIndex((match) => match.id === selectedMatch.id);
    if (selectedIndex >= 0) pool.splice(selectedIndex, 1);

    items.push({
      kind,
      ...DAILY_SCENARIO_META[kind],
      match: selectedMatch,
    });
  });

  return items;
}

function DailyFocusScenariosTeaser({
  matches,
  premiumAiEnabled,
  onOpenMatch,
  onOpenSubscription,
}: {
  matches: MatchItem[];
  premiumAiEnabled: boolean;
  onOpenMatch: (match: MatchItem) => void;
  onOpenSubscription: () => void;
}) {
  const scenarios = useMemo(() => buildDailyScenarioMatches(matches), [matches]);

  if (scenarios.length === 0) return null;

  return (
    <section className="animate-rise rounded-lg border border-gold/20 bg-gold/[0.055] p-4 shadow-card">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gold/15 text-gold">
          <Sparkles className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-extrabold text-white">
            🎯 Сценарии дня
          </h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            MatchLab группирует матчи по читаемости данных и уровню
            неопределённости.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {scenarios.map((scenario) => (
          <article
            key={`${scenario.kind}:${scenario.match.id}`}
            className="rounded-md border border-line/70 bg-white/[0.025] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-bold uppercase text-gold">
                  {scenario.badge} {scenario.title}
                </p>
                <p className="mt-2 truncate text-sm font-extrabold text-white">
                  {scenario.match.home || "Хозяева"} —{" "}
                  {scenario.match.away || "Гости"}
                </p>
              </div>
              {formatAlmatyKickoff(scenario.match.kickoff) && (
                <span className="shrink-0 rounded-md bg-white/[0.06] px-2 py-1 text-[11px] font-bold text-slate-300">
                  {formatAlmatyKickoff(scenario.match.kickoff)}
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {scenario.match.league && (
                <span className="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
                  {scenario.match.league}
                </span>
              )}
              {scenario.match.round && (
                <span className="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
                  {scenario.match.round}
                </span>
              )}
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-300">
              {scenario.explanation}
            </p>
            <button
              type="button"
              onClick={() =>
                premiumAiEnabled
                  ? onOpenMatch(scenario.match)
                  : onOpenSubscription()
              }
              className={`mt-3 h-9 w-full rounded-md text-xs font-bold transition active:scale-[0.98] ${
                premiumAiEnabled
                  ? "bg-accent text-white"
                  : "bg-gold text-zinc-950"
              }`}
            >
              {premiumAiEnabled
                ? "Открыть Premium AI-разбор"
                : "Смотреть Premium"}
            </button>
            {!premiumAiEnabled && (
              <p className="mt-2 text-center text-[11px] text-slate-500">
                Подробный AI-сценарий доступен в Premium.
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function MatchesScreen({
  initialType,
  dailyFocusMode,
  premiumAiEnabled,
  onOpenMatch,
  onOpenAllMatches,
  onOpenSubscription,
  onOpenTournament,
  onOpenTeam,
  reminderMatchIds,
  remindersLoading,
  reminderLoadingIds,
  reminderActionError,
  deepLinkError,
  onToggleReminder,
}: {
  initialType: MatchListType;
  dailyFocusMode: boolean;
  premiumAiEnabled: boolean;
  onOpenMatch: (match: MatchItem) => void;
  onOpenAllMatches: () => void;
  onOpenSubscription: () => void;
  onOpenTournament: (tournament: TournamentSelection) => void;
  onOpenTeam: (team: TeamSearchItem) => void;
  reminderMatchIds: Set<string>;
  remindersLoading: boolean;
  reminderLoadingIds: Set<string>;
  reminderActionError: string;
  deepLinkError: string;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const [activeType, setActiveType] = useState<MatchListType>(initialType);
  const [activeView, setActiveView] = useState<MatchesView>("matches");
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [dailyFocusFallbackMatches, setDailyFocusFallbackMatches] = useState<
    MatchItem[]
  >([]);
  const [dailyFocusFallbackLoading, setDailyFocusFallbackLoading] =
    useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [expandedLeagues, setExpandedLeagues] = useState<Set<string>>(
    new Set(),
  );
  const [teamQuery, setTeamQuery] = useState("");
  const [teamResults, setTeamResults] = useState<TeamSearchItem[]>([]);
  const [teamSearchLoading, setTeamSearchLoading] = useState(false);
  const [teamSearchError, setTeamSearchError] = useState(false);
  const normalizedTeamQuery = teamQuery.trim();
  const isTeamSearchActive =
    !dailyFocusMode && normalizedTeamQuery.length >= 2;
  const focusMatches = useMemo(
    () => sortMatchesByImportance(matches).slice(0, 5),
    [matches],
  );
  const dailyFocusDisplayMatches = useMemo(
    () =>
      focusMatches.length > 0
        ? focusMatches
        : sortMatchesByImportance(dailyFocusFallbackMatches).slice(0, 5),
    [dailyFocusFallbackMatches, focusMatches],
  );
  const groupedMatches = useMemo(() => {
    const groups = new Map<string, MatchItem[]>();
    sortMatchesByImportance(matches).forEach((match) => {
      const leagueName = match.league || "Другие турниры";
      const group = groups.get(leagueName) || [];
      group.push(match);
      groups.set(leagueName, group);
    });
    return Array.from(groups.entries());
  }, [matches]);

  useEffect(() => {
    let active = true;

    if (!isTeamSearchActive) {
      setTeamResults([]);
      setTeamSearchLoading(false);
      setTeamSearchError(false);
      return () => {
        active = false;
      };
    }

    setTeamSearchLoading(true);
    setTeamSearchError(false);
    const timeoutId = window.setTimeout(() => {
      searchTeams(normalizedTeamQuery)
        .then((response) => {
          if (!active) return;
          if (!response.ok) {
            throw new Error(response.error || "Team search error");
          }
          setTeamResults(response.items || []);
        })
        .catch(() => {
          if (!active) return;
          setTeamResults([]);
          setTeamSearchError(true);
        })
        .finally(() => {
          if (active) setTeamSearchLoading(false);
        });
    }, 400);

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [isTeamSearchActive, normalizedTeamQuery]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    setExpandedLeagues(new Set());

    getMatches(activeType)
      .then((response) => {
        if (!active) return;
        if (!response.ok) throw new Error(response.error || "Matches error");
        const nextMatches = sortMatchesByImportance(response.items || []);
        const firstLeague = nextMatches[0]?.league || "Другие турниры";
        setMatches(nextMatches);
        setExpandedLeagues(
          firstLeague && nextMatches.length > 0
            ? new Set([firstLeague])
            : new Set(),
        );
      })
      .catch(() => {
        if (!active) return;
        setMatches([]);
        setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [activeType, reloadKey]);

  useEffect(() => {
    let active = true;

    if (!dailyFocusMode) {
      setDailyFocusFallbackMatches([]);
      setDailyFocusFallbackLoading(false);
      return () => {
        active = false;
      };
    }

    setDailyFocusFallbackLoading(true);

    Promise.allSettled([getMatches("top"), getMatches("tomorrow")])
      .then((results) => {
        if (!active) return;

        const uniqueMatches = new Map<string, MatchItem>();
        results.forEach((result) => {
          if (result.status !== "fulfilled" || !result.value.ok) return;
          result.value.items.forEach((match) => {
            uniqueMatches.set(match.id, match);
          });
        });

        const upcomingMatches = sortMatchesByImportance(
          Array.from(uniqueMatches.values()).filter((match) => {
            if (!match.kickoff) return true;
            const kickoffTime = new Date(match.kickoff).getTime();
            return (
              !Number.isFinite(kickoffTime) ||
              kickoffTime >= Date.now() - 2 * 60 * 60 * 1000
            );
          }),
        );

        setDailyFocusFallbackMatches(upcomingMatches);
      })
      .catch(() => {
        if (active) setDailyFocusFallbackMatches([]);
      })
      .finally(() => {
        if (active) setDailyFocusFallbackLoading(false);
      });

    return () => {
      active = false;
    };
  }, [dailyFocusMode, reloadKey]);

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <div className="mb-5 flex items-end justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-slate-500">
            {dailyFocusMode ? "Сегодня в фокусе" : "Расписание"}
          </p>
          <h1 className="mt-1 text-2xl font-extrabold text-white">
            {dailyFocusMode ? "🔥 Матчи дня" : "Матчи"}
          </h1>
        </div>
        {!loading && !error && (
          <span className="rounded-full bg-panelSoft px-2.5 py-1 text-xs font-semibold text-slate-300">
            {dailyFocusMode ? dailyFocusDisplayMatches.length : matches.length}
          </span>
        )}
      </div>

      {!dailyFocusMode && (
        <div className="relative mb-4">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="search"
          value={teamQuery}
          onChange={(event) => setTeamQuery(event.target.value)}
          placeholder="Искать команду"
          className="h-11 w-full rounded-lg border border-line bg-panel pl-10 pr-4 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-accent/60"
        />
      </div>
      )}

      {isTeamSearchActive && (
        <section className="mb-5 overflow-hidden rounded-lg border border-line bg-panel">
          {teamSearchLoading && (
            <div className="flex min-h-28 items-center justify-center">
              <LoaderCircle className="h-5 w-5 animate-spin text-accent" />
            </div>
          )}

          {!teamSearchLoading && teamSearchError && (
            <p className="px-4 py-8 text-center text-sm text-slate-400">
              Поиск команд временно недоступен.
            </p>
          )}

          {!teamSearchLoading &&
            !teamSearchError &&
            teamResults.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-slate-400">
                Команды не найдены.
              </p>
            )}

          {!teamSearchLoading &&
            !teamSearchError &&
            teamResults.map((team) => (
              <button
                key={team.id}
                type="button"
                onClick={() => onOpenTeam(team)}
                className="flex w-full items-center gap-3 border-t border-line/80 px-4 py-3 text-left first:border-t-0 hover:bg-white/[0.035]"
              >
                <TeamLogo logo={team.logo} name={team.name} size="sm" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-white">
                    {team.name}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {team.country || "Страна не указана"}
                  </p>
                </div>
                <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-slate-500" />
              </button>
            ))}
        </section>
      )}

      {!isTeamSearchActive && (
        <>
      {deepLinkError && (
        <p className="mb-4 rounded-md border border-amber-400/15 bg-amber-400/[0.07] px-3 py-2 text-xs text-amber-100">
          {deepLinkError}
        </p>
      )}
      {reminderActionError && (
        <p className="mb-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-xs text-red-200">
          {reminderActionError}
        </p>
      )}
      {dailyFocusMode && (
        <section className="mb-5 rounded-lg border border-lime/20 bg-lime/[0.06] p-4 shadow-card">
          <p className="text-sm leading-6 text-slate-300">
            AI выбрал матчи, за которыми сегодня стоит следить: форма команд,
            мотивация, риски и возможный сценарий игры.
          </p>
        </section>
      )}

      {!dailyFocusMode && (
        <>
      <div className="relative mb-3 grid grid-cols-2 rounded-full bg-panel p-1">
        <span
          className={`absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-full bg-accent shadow-card transition-transform duration-300 ease-out ${
            activeView === "leagues" ? "translate-x-full" : "translate-x-0"
          }`}
          aria-hidden="true"
        />
        {[
          { id: "matches" as MatchesView, label: "Матчи" },
          { id: "leagues" as MatchesView, label: "Лиги" },
        ].map((view) => (
          <button
            key={view.id}
            type="button"
            onClick={() => setActiveView(view.id)}
            className={`relative z-10 h-9 rounded-full text-sm font-semibold transition-colors duration-300 ${
              activeView === view.id ? "text-white" : "text-slate-400"
            }`}
          >
            {view.label}
          </button>
        ))}
      </div>
        </>
      )}

      {!dailyFocusMode && (
        <div className="mb-5 grid grid-cols-4 rounded-lg bg-panel p-1">
        {matchTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              setExpandedLeagues(new Set());
              setActiveType(tab.id);
            }}
            className={`h-10 rounded-md text-sm font-semibold transition ${
              activeType === tab.id
                ? "bg-accent text-white"
                : "text-slate-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      )}

      <div className="space-y-3">
        {(loading ||
          (dailyFocusMode &&
            dailyFocusDisplayMatches.length === 0 &&
            dailyFocusFallbackLoading)) &&
          Array.from({ length: 4 }, (_, index) => (
            <MatchSkeleton key={index} />
          ))}

        {!loading && error && (
          <div className="py-14 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10 text-red-400">
              <RefreshCw className="h-5 w-5" />
            </div>
            <p className="mt-4 text-sm font-semibold text-white">
              Не удалось загрузить матчи
            </p>
            <p className="mx-auto mt-2 max-w-64 text-xs leading-5 text-slate-400">
              Проверьте соединение и попробуйте обновить список.
            </p>
            <button
              type="button"
              onClick={() => setReloadKey((value) => value + 1)}
              className="mt-5 h-10 rounded-md bg-accent px-5 text-sm font-semibold text-white"
            >
              Повторить
            </button>
          </div>
        )}

        {!loading &&
          !dailyFocusFallbackLoading &&
          !error &&
          dailyFocusMode &&
          dailyFocusDisplayMatches.length === 0 && (
          <div className="rounded-lg border border-line bg-panel px-4 py-8 text-center shadow-card">
            <CalendarDays className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-4 text-sm font-semibold text-white">
              Пока нет доступных матчей.
            </p>
            <p className="mx-auto mt-2 max-w-64 text-xs leading-5 text-slate-400">
              Попробуй открыть общий список позже.
            </p>
            <button
              type="button"
              onClick={() => {
                setActiveType("top");
                onOpenAllMatches();
              }}
              className="mt-5 h-10 rounded-md bg-accent px-5 text-sm font-semibold text-white"
            >
              Открыть все матчи
            </button>
          </div>
        )}

        {!loading && !error && !dailyFocusMode && matches.length === 0 && (
          <div className="py-16 text-center">
            <CalendarDays className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-4 text-sm font-semibold text-white">
              {activeType === "live"
                ? "Сейчас live-матчей нет."
                : "Матчей пока нет"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {activeType === "live"
                ? "Загляните позже или откройте матчи на сегодня."
                : "Расписание обновится автоматически."}
            </p>
          </div>
        )}

        {!loading &&
          (!dailyFocusFallbackLoading ||
            dailyFocusDisplayMatches.length > 0) &&
          !error &&
          dailyFocusMode &&
          dailyFocusDisplayMatches.length > 0 && (
            <>
              <DailyFocusScenariosTeaser
                matches={dailyFocusDisplayMatches}
                premiumAiEnabled={premiumAiEnabled}
                onOpenMatch={onOpenMatch}
                onOpenSubscription={onOpenSubscription}
              />
              <section>
                <h2 className="mb-3 text-sm font-extrabold text-white">
                  Все матчи дня
                </h2>
                <div className="space-y-3">
                  {dailyFocusDisplayMatches.map((match, index) => (
                    <DailyFocusMatchCard
                      key={match.id}
                      match={match}
                      index={index}
                      premiumAiEnabled={premiumAiEnabled}
                      onOpenMatch={onOpenMatch}
                    />
                  ))}
                </div>
              </section>
            </>
          )}

        {!loading &&
          !error &&
          !dailyFocusMode &&
          activeView === "matches" &&
          groupedMatches.map(([leagueName, leagueMatches], index) => {
            const firstMatch = leagueMatches[0];
            const isExpanded = expandedLeagues.has(leagueName);
            return (
              <section
                key={leagueName}
                className="animate-rise overflow-hidden rounded-lg border border-line bg-panel shadow-card"
                style={{ animationDelay: `${Math.min(index * 55, 220)}ms` }}
              >
                <div className="flex items-center">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedLeagues((current) =>
                        current.has(leagueName)
                          ? new Set()
                          : new Set([leagueName]),
                      )
                    }
                    className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left transition hover:bg-white/[0.035] active:bg-white/[0.06]"
                    aria-expanded={isExpanded}
                  >
                    <LeagueLogo
                      logo={firstMatch.league_logo}
                      name={leagueName}
                    />
                    <div className="min-w-0">
                      <h2 className="truncate text-sm font-bold text-white">
                        {leagueName}
                      </h2>
                      <p className="truncate text-[11px] text-slate-500">
                        {firstMatch.country || "Международный турнир"}
                      </p>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-500">
                        {leagueMatches.length}
                      </span>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-slate-500" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-slate-500" />
                      )}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpenTournament({
                        league: leagueName,
                        country:
                          firstMatch.country || "Международный турнир",
                        leagueLogo: firstMatch.league_logo,
                        matches: leagueMatches,
                      });
                    }}
                    className="mr-3 flex h-8 shrink-0 items-center gap-1 rounded-md bg-white/[0.05] px-2 text-[10px] font-semibold text-slate-300 transition hover:bg-white/[0.09] active:scale-[0.98]"
                  >
                    Турнир
                    <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
                {isExpanded &&
                  leagueMatches.map((match) => (
                    <CompactMatchRow
                      key={match.id}
                      match={match}
                      onOpen={onOpenMatch}
                      reminderActive={reminderMatchIds.has(match.id)}
                      reminderLoading={
                        remindersLoading || reminderLoadingIds.has(match.id)
                      }
                      onToggleReminder={onToggleReminder}
                    />
                  ))}
              </section>
            );
          })}

        {!loading &&
          !error &&
          !dailyFocusMode &&
          activeView === "leagues" &&
          groupedMatches.map(([leagueName, leagueMatches], index) => {
            const firstMatch = leagueMatches[0];
            return (
              <button
                key={leagueName}
                type="button"
                onClick={() =>
                  onOpenTournament({
                    league: leagueName,
                    country:
                      firstMatch.country || "Международный турнир",
                    leagueLogo: firstMatch.league_logo,
                    matches: leagueMatches,
                  })
                }
                className="animate-rise flex w-full items-center gap-3 rounded-lg border border-line bg-panel px-4 py-3 text-left shadow-card transition hover:bg-white/[0.035] active:scale-[0.99]"
                style={{ animationDelay: `${Math.min(index * 45, 180)}ms` }}
              >
                <LeagueLogo
                  logo={firstMatch.league_logo}
                  name={leagueName}
                />
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-bold text-white">
                    {leagueName}
                  </h2>
                  <p className="truncate text-[11px] text-slate-500">
                    {firstMatch.country || "Международный турнир"}
                  </p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <span className="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
                    {leagueMatches.length}
                  </span>
                  <ChevronRight className="h-4 w-4 text-slate-500" />
                </div>
              </button>
            );
          })}
      </div>
        </>
      )}
    </div>
  );
}

function MatchContextLoading() {
  return (
    <div className="flex min-h-40 items-center justify-center">
      <LoaderCircle className="h-6 w-6 animate-spin text-accent" />
    </div>
  );
}

function ContextMatchRow({
  match,
  onOpen,
}: {
  match: MatchContextMatch;
  onOpen: (match: MatchContextMatch) => Promise<void>;
}) {
  const hasScore =
    hasNumericMatchScore(match.home_score, match.away_score);
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState("");

  async function handleOpen() {
    if (opening) return;
    setOpening(true);
    setOpenError("");

    try {
      await onOpen(match);
    } catch {
      setOpenError("Не удалось открыть матч.");
    } finally {
      setOpening(false);
    }
  }

  return (
    <div className="border-t border-line/80 first:border-t-0">
      <button
        type="button"
        onClick={handleOpen}
        disabled={opening}
        className="grid w-full grid-cols-[4.75rem_minmax(0,1fr)_auto_1.25rem] items-center gap-3 px-3 py-3 text-left transition hover:bg-white/[0.035] disabled:cursor-wait disabled:opacity-70"
      >
        <div>
          <p className="text-[10px] leading-4 text-slate-500">
            {formatContextMatchDate(match.date)}
          </p>
          <p className="mt-0.5 text-[10px] font-semibold text-slate-400">
            {formatMatchStatus(match.status, hasScore)}
          </p>
        </div>
        <div className="min-w-0 space-y-1.5">
          <p className="truncate text-xs font-semibold text-white">
            {match.home || "Хозяева"}
          </p>
          <p className="truncate text-xs font-semibold text-white">
            {match.away || "Гости"}
          </p>
        </div>
        <div className="space-y-1.5 text-right text-xs font-bold text-white">
          <p>{hasScore ? match.home_score : "—"}</p>
          <p>{hasScore ? match.away_score : "—"}</p>
        </div>
        {opening ? (
          <LoaderCircle className="h-4 w-4 animate-spin text-accent" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-600" />
        )}
      </button>
      {openError && (
        <p className="px-3 pb-2 text-[10px] text-red-200">{openError}</p>
      )}
    </div>
  );
}

function MatchContextGroup({
  title,
  matches,
  onOpenMatch,
}: {
  title: string;
  matches: MatchContextMatch[];
  onOpenMatch: (match: MatchContextMatch) => Promise<void>;
}) {
  if (matches.length === 0) {
    return null;
  }

  return (
    <section>
      <h2 className="mb-2 text-sm font-bold text-white">{title}</h2>
      <div className="overflow-hidden rounded-lg border border-line bg-panel">
        {matches.map((contextMatch, index) => (
          <ContextMatchRow
            key={`${title}-${contextMatch.id}-${index}`}
            match={contextMatch}
            onOpen={onOpenMatch}
          />
        ))}
      </div>
    </section>
  );
}

function StandingsTable({
  rows,
  highlightedTeams = [],
  highlightTeamId,
  highlightTeamName,
}: {
  rows: MatchStandingRow[];
  highlightedTeams?: string[];
  highlightTeamId?: number;
  highlightTeamName?: string;
}) {
  const normalizedHighlightedTeams = new Set(
    [...highlightedTeams, highlightTeamName || ""]
      .filter(Boolean)
      .map(normalizeTeamLabel),
  );

  return (
    <div className="space-y-5">
      {groupStandingsByGroup(rows).map(([groupName, groupRows]) => {
        const descriptions = Array.from(
          new Set(
            groupRows
              .map((row) => row.description.trim())
              .filter(Boolean),
          ),
        );

        return (
          <section key={groupName}>
            <h2 className="mb-2 text-sm font-bold text-white">{groupName}</h2>
            <div className="overflow-hidden rounded-lg border border-line bg-panel">
              <div className="grid grid-cols-[minmax(7rem,1fr)_1.5rem_1.5rem_1.5rem_1.5rem_3rem_2rem] items-center gap-1 border-b border-line px-2 py-2 text-[9px] font-semibold uppercase text-slate-500">
                <span>Команда</span>
                <span className="text-center">P</span>
                <span className="text-center">W</span>
                <span className="text-center">D</span>
                <span className="text-center">L</span>
                <span className="text-center">GLS</span>
                <span className="text-center">PTS</span>
              </div>
              {groupRows.map((row) => {
                const isSelectedTeam =
                  (typeof highlightTeamId === "number" &&
                    row.team_id === highlightTeamId) ||
                  normalizedHighlightedTeams.has(
                    normalizeTeamLabel(row.team),
                  );
                const zoneStyle = getStandingZoneStyle(row.description);

                return (
                  <div
                    key={`${groupName}-${row.rank}-${row.team}`}
                    className={`grid grid-cols-[minmax(7rem,1fr)_1.5rem_1.5rem_1.5rem_1.5rem_3rem_2rem] items-center gap-1 border-t border-line/70 px-2 py-2.5 text-[11px] first:border-t-0 ${zoneStyle.rowClass} ${
                      isSelectedTeam
                        ? "bg-accent/[0.12] shadow-[inset_3px_0_0_rgba(99,102,241,0.95)] ring-1 ring-inset ring-accent/30"
                        : ""
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span className="w-4 shrink-0 text-center font-semibold text-slate-500">
                        {row.rank}
                      </span>
                      <span
                        className={`truncate font-semibold ${
                          isSelectedTeam ? "text-lime" : "text-white"
                        }`}
                      >
                        {row.team}
                      </span>
                    </div>
                    <span className="text-center text-slate-300">
                      {row.played ?? "—"}
                    </span>
                    <span className="text-center text-slate-300">
                      {row.wins ?? "—"}
                    </span>
                    <span className="text-center text-slate-300">
                      {row.draws ?? "—"}
                    </span>
                    <span className="text-center text-slate-300">
                      {row.losses ?? "—"}
                    </span>
                    <span className="text-center text-slate-300">
                      {row.goals_for ?? "—"}:{row.goals_against ?? "—"}
                    </span>
                    <span className="text-center font-bold text-white">
                      {row.points ?? "—"}
                    </span>
                  </div>
                );
              })}
            </div>

            {descriptions.length > 0 && (
              <div className="mt-2 space-y-1.5 px-1">
                {descriptions.map((description) => {
                  const zoneStyle = getStandingZoneStyle(description);
                  return (
                    <div
                      key={description}
                      className="flex items-start gap-2 text-[10px] leading-4 text-slate-500"
                    >
                      <span
                        className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${zoneStyle.dotClass}`}
                      />
                      <span>{description}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

type BracketStage =
  | "round-of-32"
  | "round-of-16"
  | "quarterfinal"
  | "semifinal"
  | "final";

const bracketStages: Array<{ id: BracketStage; label: string }> = [
  { id: "round-of-32", label: "1/16" },
  { id: "round-of-16", label: "1/8" },
  { id: "quarterfinal", label: "1/4" },
  { id: "semifinal", label: "Полуфинал" },
  { id: "final", label: "Финал" },
];

const bracketStageColumns: Record<BracketStage, [string, string, string]> = {
  "round-of-32": ["1/16 финала", "1/8 финала", "1/4 финала"],
  "round-of-16": ["1/8 финала", "1/4 финала", "1/2 финала"],
  quarterfinal: ["1/4 финала", "Полуфинал", "Финал"],
  semifinal: ["Полуфинал", "Финал", "Победитель"],
  final: ["Финал", "Победитель", "Трофей"],
};

function BracketMatchPlaceholder({
  labels,
  className,
}: {
  labels: string[];
  className: string;
}) {
  return (
    <div
      className={`absolute overflow-hidden rounded-lg border border-line bg-panelSoft shadow-card ${className}`}
    >
      {labels.map((label, index) => (
        <div
          key={`${label}-${index}`}
          className="flex h-10 items-center gap-2 border-t border-line/80 px-3 first:border-t-0"
        >
          <span className="h-5 w-5 shrink-0 rounded-full border border-white/[0.06] bg-white/[0.04]" />
          <span className="truncate text-xs font-semibold text-slate-300">
            {label}
          </span>
        </div>
      ))}
    </div>
  );
}

function TournamentBracketPlaceholder() {
  const [activeStage, setActiveStage] =
    useState<BracketStage>("round-of-16");
  const stageColumns = bracketStageColumns[activeStage];

  return (
    <section className="animate-rise">
      <div className="flex items-start gap-3 px-1">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/[0.04] text-slate-300">
          <Trophy className="h-5 w-5" strokeWidth={1.8} />
        </div>
        <div>
          <h2 className="text-base font-bold text-white">Сетка плей-офф</h2>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Сетка появится после формирования матчей на выбывание. Сейчас
            показан пример структуры.
          </p>
        </div>
      </div>

      <div className="-mx-4 mt-5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-2">
          {bracketStages.map((stage) => (
            <button
              key={stage.id}
              type="button"
              onClick={() => setActiveStage(stage.id)}
              aria-pressed={activeStage === stage.id}
              className={`h-9 rounded-full px-4 text-xs font-semibold transition ${
                activeStage === stage.id
                  ? "bg-white text-slate-950"
                  : "border border-line bg-panel text-slate-400 hover:text-white"
              }`}
            >
              {stage.label}
            </button>
          ))}
        </div>
      </div>

      <div className="-mx-4 mt-4 overflow-x-auto px-4 pb-4 [scrollbar-width:thin] [scrollbar-color:rgba(148,163,184,0.25)_transparent]">
        <div className="min-w-[752px] rounded-lg border border-line bg-panel/70 p-4">
          <div className="grid w-[718px] grid-cols-[190px_190px_190px] gap-x-[74px]">
            {stageColumns.map((stage) => (
              <p
                key={stage}
                className="text-[10px] font-semibold uppercase text-slate-500"
              >
                {stage}
              </p>
            ))}
          </div>

          <div className="relative mt-3 h-[274px] w-[718px]">
            <BracketMatchPlaceholder
              labels={["Участник 1", "Участник 2"]}
              className="left-0 top-3 w-[190px]"
            />
            <BracketMatchPlaceholder
              labels={["Участник 3", "Участник 4"]}
              className="left-0 top-[175px] w-[190px]"
            />
            <BracketMatchPlaceholder
              labels={["Победитель пары", "Победитель пары"]}
              className="left-[264px] top-[94px] w-[190px]"
            />
            <BracketMatchPlaceholder
              labels={["Финалист"]}
              className="left-[528px] top-[114px] w-[190px]"
            />

            <span className="absolute left-[190px] top-[52px] w-9 border-t border-line" />
            <span className="absolute left-[190px] top-[214px] w-9 border-t border-line" />
            <span className="absolute left-[226px] top-[52px] h-[162px] border-l border-line" />
            <span className="absolute left-[226px] top-[133px] w-[38px] border-t border-line" />
            <span className="absolute left-[454px] top-[133px] w-[74px] border-t border-line" />
            <span className="absolute left-[222px] top-[129px] h-2 w-2 rounded-full border border-line bg-panel" />
            <span className="absolute left-[524px] top-[129px] h-2 w-2 rounded-full border border-line bg-panel" />
          </div>

          <div className="flex items-center gap-2 border-t border-line pt-3">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-slate-600" />
            <p className="text-[10px] leading-4 text-slate-500">
              Структура демонстрационная, участники будут добавлены после
              формирования этапа.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function TournamentDetails({
  tournament,
  onBack,
  onOpenMatch,
  reminderMatchIds,
  remindersLoading,
  reminderLoadingIds,
  onToggleReminder,
}: {
  tournament: TournamentSelection;
  onBack: () => void;
  onOpenMatch: (match: MatchItem) => void;
  reminderMatchIds: Set<string>;
  remindersLoading: boolean;
  reminderLoadingIds: Set<string>;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const [activeTab, setActiveTab] = useState<TournamentTab>("overview");
  const [context, setContext] = useState<MatchContextResponse | null>(null);
  const [contextLoading, setContextLoading] = useState(true);
  const [contextError, setContextError] = useState(false);
  const sortedTournamentMatches = useMemo(
    () => sortMatchesByImportance(tournament.matches),
    [tournament.matches],
  );
  const firstMatch = sortedTournamentMatches[0];
  const nearestMatch = useMemo(
    () =>
      [...tournament.matches].sort(
        (left, right) => getMatchKickoffTime(left) - getMatchKickoffTime(right),
      )[0],
    [tournament.matches],
  );
  const nearestKickoff = formatKickoff(nearestMatch?.kickoff || null);
  const standingsTeamCount = context?.standings.length || 0;
  const standingsGroupCount = context
    ? new Set(
        context.standings
          .map((row) => row.group.trim())
          .filter(Boolean),
      ).size
    : 0;
  const tournamentTabs: Array<{ id: TournamentTab; label: string }> = [
    { id: "overview", label: "Обзор" },
    { id: "matches", label: "Матчи" },
    { id: "standings", label: "Турнирная таблица" },
    ...(isKnockoutLikeTournament(tournament.league)
      ? [{ id: "bracket" as TournamentTab, label: "Сетка" }]
      : []),
  ];

  useEffect(() => {
    let active = true;
    if (!firstMatch) {
      setContextLoading(false);
      return () => {
        active = false;
      };
    }

    setContextLoading(true);
    setContextError(false);
    getMatchContext(firstMatch.id)
      .then((response) => {
        if (active) {
          setContext(response);
        }
      })
      .catch(() => {
        if (active) {
          setContextError(true);
        }
      })
      .finally(() => {
        if (active) {
          setContextLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [firstMatch?.id]);

  return (
    <div className="animate-rise">
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-panel text-white"
          aria-label="Назад"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-panel">
            <LeagueLogo
              logo={tournament.leagueLogo}
              name={tournament.league}
            />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-extrabold text-white">
              {tournament.league}
            </h1>
            <p className="truncate text-xs text-slate-500">
              {tournament.country}
            </p>
          </div>
        </div>
        <span className="rounded-full bg-panelSoft px-2.5 py-1 text-xs font-semibold text-slate-300">
          {tournament.matches.length}
        </span>
      </div>

      <div className="-mx-4 mb-5 overflow-x-auto border-y border-line px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-1">
          {tournamentTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`relative h-12 px-4 text-sm font-semibold transition ${
                activeTab === tab.id ? "text-white" : "text-slate-500"
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-lime" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "overview" && (
        <section className="space-y-4">
          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="flex items-start gap-3">
              <LeagueLogo
                logo={tournament.leagueLogo}
                name={tournament.league}
              />
              <div className="min-w-0">
                <h2 className="truncate text-base font-bold text-white">
                  {tournament.league}
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  {tournament.country}
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
              <div>
                <p className="text-[10px] uppercase text-slate-500">
                  Матчей в списке
                </p>
                <p className="mt-1 text-lg font-bold text-white">
                  {tournament.matches.length}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-slate-500">
                  Статус данных
                </p>
                <p className="mt-1 text-sm font-semibold text-lime">
                  Данные MatchLab
                </p>
              </div>
              {standingsTeamCount > 0 && (
                <div>
                  <p className="text-[10px] uppercase text-slate-500">
                    Команд в таблице
                  </p>
                  <p className="mt-1 text-lg font-bold text-white">
                    {standingsTeamCount}
                  </p>
                </div>
              )}
              {standingsGroupCount > 0 && (
                <div>
                  <p className="text-[10px] uppercase text-slate-500">
                    Групп
                  </p>
                  <p className="mt-1 text-lg font-bold text-white">
                    {standingsGroupCount}
                  </p>
                </div>
              )}
            </div>
          </div>

          {nearestMatch && (
            <div className="rounded-lg border border-line bg-panel p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                Ближайший матч
              </p>
              <div className="mt-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-white">
                    {nearestMatch.home} — {nearestMatch.away}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {nearestKickoff.time}, {nearestKickoff.date}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenMatch(nearestMatch)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/[0.05] text-slate-300"
                  aria-label="Открыть ближайший матч"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}

          {!contextLoading &&
            (contextError || !context || context.standings.length === 0) && (
              <p className="rounded-lg border border-line bg-panel px-4 py-3 text-sm leading-6 text-slate-400">
                Расширенная информация по турниру пока недоступна.
              </p>
            )}
        </section>
      )}

      {activeTab === "matches" && (
        <>
          {sortedTournamentMatches.length > 0 ? (
            <section className="overflow-hidden rounded-lg border border-line bg-panel">
              {sortedTournamentMatches.map((match) => (
                <CompactMatchRow
                  key={match.id}
                  match={match}
                  onOpen={onOpenMatch}
                  reminderActive={reminderMatchIds.has(match.id)}
                  reminderLoading={
                    remindersLoading || reminderLoadingIds.has(match.id)
                  }
                  onToggleReminder={onToggleReminder}
                />
              ))}
            </section>
          ) : (
            <div className="py-10 text-center">
              <CalendarDays className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mt-4 text-sm font-semibold text-white">
                Матчи турнира пока недоступны.
              </p>
            </div>
          )}
        </>
      )}

      {activeTab === "standings" && (
        <section>
          {contextLoading && <MatchContextLoading />}
          {!contextLoading && contextError && (
            <div className="py-10 text-center">
              <Trophy className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mt-4 text-sm font-semibold text-white">
                Турнирная таблица временно недоступна.
              </p>
            </div>
          )}
          {!contextLoading &&
            !contextError &&
            (!context || context.standings.length === 0) && (
              <div className="py-10 text-center">
                <Trophy className="mx-auto h-7 w-7 text-slate-600" />
                <p className="mt-4 text-sm font-semibold text-white">
                  Турнирная таблица пока недоступна.
                </p>
              </div>
            )}
          {!contextLoading &&
            !contextError &&
            context &&
            context.standings.length > 0 && (
              <StandingsTable rows={context.standings} />
            )}
        </section>
      )}

      {activeTab === "bracket" && <TournamentBracketPlaceholder />}
    </div>
  );
}

function getTeamMatchResult(match: MatchItem, teamId: number) {
  const homeScore = match.score?.home;
  const awayScore = match.score?.away;
  if (
    typeof homeScore !== "number" ||
    typeof awayScore !== "number"
  ) {
    return "neutral";
  }

  const isHomeTeam = match.home_id === teamId;
  const isAwayTeam = match.away_id === teamId;
  if (!isHomeTeam && !isAwayTeam) {
    return "neutral";
  }

  const teamScore = isHomeTeam ? homeScore : awayScore;
  const opponentScore = isHomeTeam ? awayScore : homeScore;
  if (teamScore > opponentScore) return "win";
  if (teamScore < opponentScore) return "loss";
  return "draw";
}

function TeamDetails({
  team: initialTeam,
  onBack,
  onOpenMatch,
  isFavorite,
  favoriteLoading,
  favoriteError,
  onToggleFavorite,
  reminderMatchIds,
  remindersLoading,
  reminderLoadingIds,
  onToggleReminder,
}: {
  team: TeamSearchItem;
  onBack: () => void;
  onOpenMatch: (match: MatchItem) => void;
  isFavorite: boolean;
  favoriteLoading: boolean;
  favoriteError: string;
  onToggleFavorite: (team: TeamSearchItem) => void;
  reminderMatchIds: Set<string>;
  remindersLoading: boolean;
  reminderLoadingIds: Set<string>;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const [activeTab, setActiveTab] = useState<TeamDetailTab>("details");
  const [team, setTeam] = useState<TeamSearchItem>(initialTeam);
  const [matches, setMatches] = useState<TeamMatchesResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState(false);
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState(false);
  const [standings, setStandings] =
    useState<TeamStandingsResponse | null>(null);
  const [standingsLoading, setStandingsLoading] = useState(true);
  const [standingsError, setStandingsError] = useState(false);
  const nearestMatch = matches?.upcoming[0] || null;
  const nearestKickoff = formatKickoff(nearestMatch?.kickoff || null);
  const relevantTeamStandings = useMemo(
    () =>
      getTeamRelevantStandingsRows(
        standings?.standings || [],
        standings?.team_id || team.id,
        standings?.team_name || team.name,
      ),
    [standings, team.id, team.name],
  );

  useEffect(() => {
    let active = true;
    setTeam(initialTeam);
    setMatches(null);
    setStandings(null);
    setProfileLoading(true);
    setProfileError(false);
    setMatchesLoading(true);
    setMatchesError(false);
    setStandingsLoading(true);
    setStandingsError(false);

    getTeamProfile(initialTeam.id)
      .then((response) => {
        if (active) setTeam(response.team);
      })
      .catch(() => {
        if (active) setProfileError(true);
      })
      .finally(() => {
        if (active) setProfileLoading(false);
      });

    getTeamMatches(initialTeam.id)
      .then((response) => {
        if (active) setMatches(response);
      })
      .catch(() => {
        if (active) setMatchesError(true);
      })
      .finally(() => {
        if (active) setMatchesLoading(false);
      });

    getTeamStandings(initialTeam.id)
      .then((response) => {
        if (!active) return;
        if (!response.ok || !response.standings?.length) {
          setStandingsError(true);
          return;
        }
        setStandings(response);
      })
      .catch(() => {
        if (active) setStandingsError(true);
      })
      .finally(() => {
        if (active) setStandingsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialTeam.id]);

  const tabs: Array<{ id: TeamDetailTab; label: string }> = [
    { id: "details", label: "Детали" },
    { id: "matches", label: "Матчи" },
    { id: "standings", label: "Турнирная таблица" },
  ];

  return (
    <div className="animate-rise">
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-panel text-white"
          aria-label="Назад"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <TeamLogo logo={team.logo} name={team.name} size="md" />
          <div className="min-w-0">
            <h1 className="truncate text-lg font-extrabold text-white">
              {team.name}
            </h1>
            <p className="truncate text-xs text-slate-500">
              {team.country || "Страна не указана"}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => onToggleFavorite(team)}
          disabled={favoriteLoading}
          className={`flex h-10 w-10 items-center justify-center rounded-lg border transition disabled:cursor-wait disabled:opacity-60 ${
            isFavorite
              ? "border-gold/30 bg-gold/10 text-gold"
              : "border-line bg-panel text-slate-500 hover:text-white"
          }`}
          aria-label={
            isFavorite
              ? "Удалить команду из избранного"
              : "Добавить команду в избранное"
          }
        >
          {favoriteLoading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Star
              className="h-5 w-5"
              fill={isFavorite ? "currentColor" : "none"}
            />
          )}
        </button>
      </div>

      {favoriteError && (
        <p className="mb-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-xs text-red-200">
          {favoriteError}
        </p>
      )}

      <div className="-mx-4 mb-5 overflow-x-auto border-y border-line px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`relative h-12 px-4 text-sm font-semibold transition ${
                activeTab === tab.id ? "text-white" : "text-slate-500"
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-lime" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "details" && profileLoading && <MatchContextLoading />}

      {activeTab === "details" && !profileLoading && profileError && (
        <div className="py-12 text-center">
          <RefreshCw className="mx-auto h-7 w-7 text-slate-600" />
          <p className="mt-4 text-sm font-semibold text-white">
            Профиль команды временно недоступен.
          </p>
        </div>
      )}

      {activeTab === "details" && !profileLoading && !profileError && (
        <section className="space-y-4">
          <div className="rounded-lg border border-line bg-panel p-4">
            <div className="grid grid-cols-2 gap-x-4 gap-y-5">
              {[
                ["Страна", team.country || "Не указана"],
                ["Основана", team.founded ? String(team.founded) : "Нет данных"],
                ["Тип", team.national ? "Сборная" : "Клуб"],
                ["Стадион", team.venue_name || "Нет данных"],
                ["Город", team.venue_city || "Нет данных"],
                [
                  "Вместимость",
                  team.venue_capacity
                    ? new Intl.NumberFormat("ru-RU").format(
                        team.venue_capacity,
                      )
                    : "Нет данных",
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-[10px] uppercase text-slate-500">
                    {label}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-white">
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {nearestMatch && (
            <div className="rounded-lg border border-line bg-panel p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                Ближайший матч
              </p>
              <button
                type="button"
                onClick={() => onOpenMatch(nearestMatch)}
                className="mt-3 flex w-full items-center gap-3 text-left"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-white">
                    {nearestMatch.home} — {nearestMatch.away}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {nearestKickoff.time}, {nearestKickoff.date}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
              </button>
            </div>
          )}

          {matches && matches.recent.length > 0 && (
            <div className="rounded-lg border border-line bg-panel p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                Форма
              </p>
              <div className="mt-3 flex gap-2">
                {matches.recent.slice(0, 5).map((match) => {
                  const result = getTeamMatchResult(match, team.id);
                  const resultClass = {
                    win: "bg-lime/20 text-lime",
                    draw: "bg-slate-600/40 text-slate-300",
                    loss: "bg-red-500/15 text-red-400",
                    neutral: "bg-white/[0.05] text-slate-500",
                  }[result];
                  const resultLabel = {
                    win: "В",
                    draw: "Н",
                    loss: "П",
                    neutral: "—",
                  }[result];

                  return (
                    <span
                      key={match.id}
                      className={`flex h-8 w-8 items-center justify-center rounded-md text-xs font-bold ${resultClass}`}
                    >
                      {resultLabel}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {activeTab === "matches" && matchesLoading && <MatchContextLoading />}

      {activeTab === "matches" && !matchesLoading && matchesError && (
        <div className="py-12 text-center">
          <CalendarDays className="mx-auto h-7 w-7 text-slate-600" />
          <p className="mt-4 text-sm font-semibold text-white">
            Матчи команды пока недоступны.
          </p>
        </div>
      )}

      {activeTab === "matches" && !matchesLoading && !matchesError && (
        <div className="space-y-6">
          {matches && matches.upcoming.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-bold text-white">
                Ближайшие матчи
              </h2>
              <div className="overflow-hidden rounded-lg border border-line bg-panel">
                {sortMatchesByImportance(matches.upcoming).map((match) => (
                  <CompactMatchRow
                    key={match.id}
                    match={match}
                    onOpen={onOpenMatch}
                    reminderActive={reminderMatchIds.has(match.id)}
                    reminderLoading={
                      remindersLoading || reminderLoadingIds.has(match.id)
                    }
                    onToggleReminder={onToggleReminder}
                  />
                ))}
              </div>
            </section>
          )}

          {matches && matches.recent.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-bold text-white">
                Последние матчи
              </h2>
              <div className="overflow-hidden rounded-lg border border-line bg-panel">
                {matches.recent.map((match) => (
                  <CompactMatchRow
                    key={match.id}
                    match={match}
                    onOpen={onOpenMatch}
                    reminderActive={reminderMatchIds.has(match.id)}
                    reminderLoading={
                      remindersLoading || reminderLoadingIds.has(match.id)
                    }
                    onToggleReminder={onToggleReminder}
                  />
                ))}
              </div>
            </section>
          )}

          {matches &&
            matches.upcoming.length === 0 &&
            matches.recent.length === 0 && (
              <p className="py-10 text-center text-sm text-slate-400">
                Матчи команды пока недоступны.
              </p>
            )}
        </div>
      )}

      {activeTab === "standings" && standingsLoading && (
        <MatchContextLoading />
      )}

      {activeTab === "standings" &&
        !standingsLoading &&
        (standingsError || !standings?.standings?.length) && (
          <div className="py-12 text-center">
            <Trophy className="mx-auto h-7 w-7 text-slate-600" />
            <p className="mt-4 text-sm font-semibold text-white">
              Турнирная таблица команды пока недоступна.
            </p>
          </div>
        )}

      {activeTab === "standings" &&
        !standingsLoading &&
        !standingsError &&
        standings?.standings &&
        standings.standings.length > 0 && (
          <section className="space-y-4">
            {standings.league && (
              <div className="flex items-center gap-3 rounded-lg border border-line bg-panel px-4 py-3">
                <LeagueLogo
                  logo={standings.league.logo}
                  name={standings.league.name}
                />
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-white">
                    {standings.league.name}
                    {standings.league.country
                      ? ` · ${standings.league.country}`
                      : ""}
                  </p>
                  {standings.league.season && (
                    <p className="mt-0.5 text-xs text-slate-500">
                      Сезон {standings.league.season}
                    </p>
                  )}
                  {relevantTeamStandings.groupName && (
                    <p className="mt-0.5 text-xs text-slate-400">
                      Группа команды: {relevantTeamStandings.groupName}
                    </p>
                  )}
                </div>
              </div>
            )}
            <StandingsTable
              rows={relevantTeamStandings.rows}
              highlightTeamId={standings.team_id || team.id}
              highlightTeamName={standings.team_name || team.name}
            />
          </section>
        )}
    </div>
  );
}

function MatchStatisticRow({ item }: { item: MatchStatisticItem }) {
  const homeValue =
    typeof item.home_value === "number" && item.home_value >= 0
      ? item.home_value
      : null;
  const awayValue =
    typeof item.away_value === "number" && item.away_value >= 0
      ? item.away_value
      : null;
  const total =
    homeValue !== null && awayValue !== null
      ? homeValue + awayValue
      : 0;
  const homeWidth = total > 0 ? ((homeValue ?? 0) / total) * 100 : 50;
  const awayWidth = total > 0 ? ((awayValue ?? 0) / total) * 100 : 50;
  const hasComparableValues =
    homeValue !== null && awayValue !== null && total > 0;

  return (
    <div className="border-t border-line/80 px-4 py-3.5 first:border-t-0">
      <div className="grid grid-cols-[3rem_minmax(0,1fr)_3rem] items-center gap-3">
        <p className="text-left text-sm font-bold text-white">
          {item.home ?? "—"}
        </p>
        <p className="text-center text-xs font-semibold text-slate-300">
          {item.label}
        </p>
        <p className="text-right text-sm font-bold text-white">
          {item.away ?? "—"}
        </p>
      </div>
      {hasComparableValues && (
        <div className="mt-2.5 flex h-1.5 gap-1 overflow-hidden rounded-full bg-white/[0.04]">
          <div
            className="h-full rounded-full bg-lime"
            style={{ width: `${homeWidth}%` }}
          />
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${awayWidth}%` }}
          />
        </div>
      )}
    </div>
  );
}

function MatchStatisticsPanel({
  match,
  statistics,
}: {
  match: MatchItem;
  statistics: MatchContextResponse["statistics"];
}) {
  const homeTeam = statistics.home;
  const awayTeam = statistics.away;

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <TeamLogo
            logo={homeTeam?.team_logo || match.home_logo}
            name={homeTeam?.team_name || match.home}
            size="xs"
          />
          <p className="truncate text-xs font-bold text-white">
            {homeTeam?.team_name || match.home}
          </p>
        </div>
        <Activity className="h-4 w-4 text-slate-600" />
        <div className="flex min-w-0 items-center justify-end gap-2">
          <p className="truncate text-right text-xs font-bold text-white">
            {awayTeam?.team_name || match.away}
          </p>
          <TeamLogo
            logo={awayTeam?.team_logo || match.away_logo}
            name={awayTeam?.team_name || match.away}
            size="xs"
          />
        </div>
      </div>
      <div>
        {statistics.items.map((item) => (
          <MatchStatisticRow key={item.type} item={item} />
        ))}
      </div>
      <div className="flex items-center justify-center gap-4 border-t border-line px-4 py-3 text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-3 rounded-full bg-lime" />
          {match.home}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-3 rounded-full bg-accent" />
          {match.away}
        </span>
      </div>
    </div>
  );
}

function MatchLineupPlayerList({
  title,
  players,
}: {
  title: string;
  players: MatchLineupPlayer[];
}) {
  return (
    <section>
      <h3 className="px-4 pb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      {players.length > 0 ? (
        <div className="border-y border-line/70 bg-white/[0.012]">
          {players.map((player, index) => (
            <div
              key={`${player.id ?? player.name}-${index}`}
              className="grid min-h-12 grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-line/60 px-4 py-2.5 first:border-t-0"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.06] bg-white/[0.04] text-[11px] font-bold text-slate-300">
                {player.number ?? "—"}
              </span>
              <span className="truncate text-sm font-semibold text-slate-100">
                {player.name}
              </span>
              <span className="min-w-8 rounded-full bg-white/[0.05] px-2 py-1 text-center text-[10px] font-bold uppercase text-slate-400">
                {player.pos || "—"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mx-4 rounded-md bg-white/[0.025] px-3 py-3 text-xs leading-5 text-slate-500">
          Данные пока не опубликованы.
        </p>
      )}
    </section>
  );
}

interface PositionedLineupPlayer {
  player: MatchLineupPlayer;
  row: number;
  column: number;
}

function getShortPlayerName(name: string) {
  const normalizedName = name.trim().replace(/\s+/g, " ");
  if (!normalizedName) return "Игрок";

  const nameParts = normalizedName.split(" ");
  return nameParts[nameParts.length - 1] || normalizedName;
}

function getPositionedLineupPlayers(players: MatchLineupPlayer[]) {
  const positionedPlayers: PositionedLineupPlayer[] = [];

  players.forEach((player) => {
    const gridMatch = player.grid?.trim().match(/^(\d+):(\d+)$/);
    if (!gridMatch) return;

    const row = Number(gridMatch[1]);
    const column = Number(gridMatch[2]);
    if (
      !Number.isSafeInteger(row) ||
      !Number.isSafeInteger(column) ||
      row <= 0 ||
      column <= 0
    ) {
      return;
    }

    positionedPlayers.push({ player, row, column });
  });

  return positionedPlayers;
}

function getLineupColumnsByRow(positionedPlayers: PositionedLineupPlayer[]) {
  const columnsByRow = new Map<number, number>();
  positionedPlayers.forEach(({ row, column }) => {
    columnsByRow.set(row, Math.max(columnsByRow.get(row) || 0, column));
  });
  return columnsByRow;
}

function canRenderTeamOnPitch(team: MatchLineupTeam) {
  return getPositionedLineupPlayers(team.start_xi).length >= 5;
}

function MatchLineupsPitch({ teams }: { teams: MatchLineupTeam[] }) {
  const pitchTeams = teams.slice(0, 2);
  if (
    pitchTeams.length < 2 ||
    !pitchTeams.every((team) => canRenderTeamOnPitch(team))
  ) {
    return null;
  }

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-panel shadow-card">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 border-b border-line/70 px-4 py-4">
        <LineupPitchTeamHeader team={pitchTeams[0]} align="left" />
        <span className="rounded-full border border-white/[0.06] bg-white/[0.035] px-2 py-1 text-[10px] font-black uppercase text-slate-500">
          vs
        </span>
        <LineupPitchTeamHeader team={pitchTeams[1]} align="right" />
      </div>

      <div className="relative h-[620px] overflow-hidden bg-[repeating-linear-gradient(0deg,rgba(16,75,53,0.96)_0px,rgba(16,75,53,0.96)_62px,rgba(18,86,59,0.96)_62px,rgba(18,86,59,0.96)_124px)] shadow-inner">
        <div className="pointer-events-none absolute inset-3 rounded-md border border-white/35" />
        <div className="pointer-events-none absolute inset-x-3 top-1/2 border-t border-white/35" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/35" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/50" />
        <div className="pointer-events-none absolute left-1/2 top-3 h-20 w-36 -translate-x-1/2 border border-t-0 border-white/35" />
        <div className="pointer-events-none absolute bottom-3 left-1/2 h-20 w-36 -translate-x-1/2 border border-b-0 border-white/35" />
        <div className="pointer-events-none absolute left-1/2 top-3 h-8 w-16 -translate-x-1/2 border border-t-0 border-white/35" />
        <div className="pointer-events-none absolute bottom-3 left-1/2 h-8 w-16 -translate-x-1/2 border border-b-0 border-white/35" />

        {pitchTeams.map((team, teamIndex) => (
          <LineupPitchPlayers
            key={`${team.team_id ?? team.team_name}-${teamIndex}`}
            team={team}
            side={teamIndex === 0 ? "away" : "home"}
          />
        ))}
      </div>
    </section>
  );
}

function LineupPitchTeamHeader({
  team,
  align,
}: {
  team: MatchLineupTeam;
  align: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center gap-2 ${
        align === "right" ? "justify-end text-right" : ""
      }`}
    >
      {align === "left" && (
        <TeamLogo
          logo={team.team_logo}
          name={team.team_name || "Команда"}
          size="xs"
        />
      )}
      <div className="min-w-0">
        <p className="truncate text-xs font-bold text-white">
          {team.team_name || "Команда"}
        </p>
        {team.formation && (
          <span className="mt-1 inline-flex rounded-full border border-lime/15 bg-lime/[0.08] px-2 py-0.5 text-[9px] font-bold text-lime">
            {team.formation}
          </span>
        )}
      </div>
      {align === "right" && (
        <TeamLogo
          logo={team.team_logo}
          name={team.team_name || "Команда"}
          size="xs"
        />
      )}
    </div>
  );
}

function LineupPitchPlayers({
  team,
  side,
}: {
  team: MatchLineupTeam;
  side: "home" | "away";
}) {
  const positionedPlayers = getPositionedLineupPlayers(team.start_xi);
  const maxRow = Math.max(
    ...positionedPlayers.map((positionedPlayer) => positionedPlayer.row),
  );
  const columnsByRow = getLineupColumnsByRow(positionedPlayers);
  const isHome = side === "home";

  return (
    <>
      {positionedPlayers.map(({ player, row, column }, index) => {
        const rowColumns = columnsByRow.get(row) || 1;
        const left = (column / (rowColumns + 1)) * 100;
        const rowProgress =
          maxRow === 1 ? 0.5 : (row - 1) / (maxRow - 1);
        const top = isHome
          ? 90 - rowProgress * 32
          : 10 + rowProgress * 32;
        const accentClass = isHome
          ? "border-lime/80 text-lime"
          : "border-accent/80 text-accent";

        return (
          <div
            key={`${team.team_id ?? team.team_name}-${player.id ?? player.name}-${row}-${column}-${index}`}
            className="absolute z-10 flex w-[4.75rem] -translate-x-1/2 -translate-y-1/2 flex-col items-center text-center"
            style={{ left: `${left}%`, top: `${top}%` }}
          >
            <span
              className={`flex h-8 w-8 items-center justify-center rounded-full border-2 bg-slate-950 text-xs font-black shadow-[0_4px_14px_rgba(0,0,0,0.45)] ${accentClass}`}
            >
              {player.number ?? "?"}
            </span>
            <span className="mt-1 max-w-[4.75rem] truncate rounded bg-slate-950/75 px-2 py-0.5 text-[9px] font-bold text-white shadow-sm backdrop-blur-sm">
              {getShortPlayerName(player.name)}
            </span>
          </div>
        );
      })}
    </>
  );
}

function MatchLineupTeamCard({
  team,
  absencePlayers = [],
}: {
  team: MatchLineupTeam;
  absencePlayers?: MatchAbsencePlayer[];
}) {
  return (
    <article className="overflow-hidden rounded-lg border border-line bg-panel shadow-card">
      <div className="flex items-center gap-3 px-4 py-4">
        <TeamLogo
          logo={team.team_logo}
          name={team.team_name || "Команда"}
          size="sm"
        />
        <div className="min-w-0">
          <h2 className="truncate text-sm font-bold text-white">
            {team.team_name || "Команда"}
          </h2>
          {team.formation && (
            <span className="mt-1.5 inline-flex rounded-full border border-lime/15 bg-lime/[0.08] px-2 py-1 text-[10px] font-bold text-lime">
              Схема {team.formation}
            </span>
          )}
        </div>
      </div>

      {team.coach && (
        <div className="flex items-center justify-between gap-4 border-t border-line/70 bg-white/[0.018] px-4 py-3">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
            Тренер
          </p>
          <p className="truncate text-right text-sm font-semibold text-slate-200">
            {team.coach.name || "Имя не указано"}
          </p>
        </div>
      )}

      <div className="space-y-5 border-t border-line/70 py-4">
        <MatchLineupPlayerList
          title="Запасные"
          players={team.substitutes}
        />
        <MatchLineupAbsencesList players={absencePlayers} />
        <MatchLineupPlayerList
          title="Стартовый состав"
          players={team.start_xi}
        />
      </div>
    </article>
  );
}

function MatchLineupAbsencesList({
  players,
}: {
  players: MatchAbsencePlayer[];
}) {
  if (players.length === 0) {
    return null;
  }

  return (
    <section>
      <h3 className="px-4 pb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">
        Не сыграют / под вопросом
      </h3>
      <div className="border-y border-line/70 bg-red-500/[0.025]">
        {players.map((player, index) => {
          const reason = formatAbsenceReason(player.reason);
          const type = formatAbsenceReason(player.type);
          const details = [reason, type].filter(Boolean).join(" · ");

          return (
            <div
              key={`${player.id ?? player.name}-${index}`}
              className="grid min-h-12 grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-line/60 px-4 py-2.5 first:border-t-0"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-md border border-red-300/10 bg-red-500/[0.08] text-[11px] font-black text-red-200">
                !
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-100">
                  {player.name}
                </p>
                <p className="mt-0.5 truncate text-xs text-slate-500">
                  {details || "Статус уточняется"}
                </p>
              </div>
              <span className="rounded-full bg-red-500/[0.08] px-2 py-1 text-[10px] font-bold text-red-200">
                Потеря
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function MatchLineupTeamSwitcher({
  teams,
  selectedIndex,
  onSelect,
}: {
  teams: MatchLineupTeam[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 rounded-xl border border-line bg-white/[0.025] p-1.5">
      {teams.slice(0, 2).map((team, index) => {
        const active = selectedIndex === index;
        return (
          <button
            key={`${team.team_id ?? team.team_name}-${index}`}
            type="button"
            onClick={() => onSelect(index)}
            className={`flex min-w-0 items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold transition ${
              active
                ? "bg-lime text-slate-950 shadow-[0_10px_26px_rgba(190,242,100,0.18)]"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-white"
            }`}
          >
            <TeamLogo
              logo={team.team_logo}
              name={team.team_name || "Команда"}
              size="xs"
            />
            <span className="truncate">{team.team_name || "Команда"}</span>
          </button>
        );
      })}
    </div>
  );
}

function getAbsenceTeamForLineupTeam(
  absences: MatchContextResponse["absences"] | undefined,
  lineupTeam: MatchLineupTeam,
) {
  if (!absences?.available) {
    return undefined;
  }

  if (lineupTeam.team_id !== null) {
    const teamById = absences.teams.find(
      (team) => team.team_id === lineupTeam.team_id,
    );
    if (teamById) return teamById;
  }

  const normalizedLineupTeamName = normalizeTeamLabel(
    lineupTeam.team_name,
  );
  if (!normalizedLineupTeamName) {
    return undefined;
  }

  return absences.teams.find(
    (team) =>
      normalizeTeamLabel(team.team_name) === normalizedLineupTeamName,
  );
}

function MatchLineupsPanel({
  teams,
  absences,
}: {
  teams: MatchLineupTeam[];
  absences?: MatchContextResponse["absences"];
}) {
  const [selectedLineupTeamIndex, setSelectedLineupTeamIndex] = useState(0);
  const canShowSharedPitch =
    teams.length >= 2 && teams.slice(0, 2).every(canRenderTeamOnPitch);
  const safeSelectedIndex = Math.min(
    selectedLineupTeamIndex,
    Math.max(teams.length - 1, 0),
  );
  const selectedTeam = teams[safeSelectedIndex];

  if (!canShowSharedPitch) {
    return (
      <div className="space-y-4">
        {teams.map((team, index) => (
          <MatchLineupTeamCard
            key={`${team.team_id ?? team.team_name}-${index}`}
            team={team}
            absencePlayers={
              getAbsenceTeamForLineupTeam(absences, team)?.players || []
            }
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <MatchLineupsPitch teams={teams} />
      <MatchLineupTeamSwitcher
        teams={teams}
        selectedIndex={safeSelectedIndex}
        onSelect={setSelectedLineupTeamIndex}
      />
      {selectedTeam && (
        <MatchLineupTeamCard
          team={selectedTeam}
          absencePlayers={
            getAbsenceTeamForLineupTeam(absences, selectedTeam)?.players || []
          }
        />
      )}
    </div>
  );
}

function formatAbsenceReason(value: string) {
  const normalizedValue = value.trim().toLocaleLowerCase("en-US");
  const translations: Record<string, string> = {
    injury: "Травма",
    suspended: "Дисквалификация",
    illness: "Болезнь",
    questionable: "Под вопросом",
    "missing fixture": "Не сыграет",
    doubtful: "Под вопросом",
  };

  return translations[normalizedValue] || value.trim();
}

function getLiveEventIcon(event: MatchLiveEvent) {
  const eventType = event.type.trim().toLocaleLowerCase("en-US");
  if (eventType === "goal") return "⚽";
  if (eventType === "card") {
    const cardDetail = event.detail.toLocaleLowerCase("en-US");
    return cardDetail.includes("red") || cardDetail.includes("second yellow")
      ? "🟥"
      : "🟨";
  }
  if (eventType === "subst") return "🔁";
  if (eventType === "var") return "📺";
  return "•";
}

function formatLiveEventMinute(event: MatchLiveEvent) {
  if (typeof event.time !== "number") return "—";
  if (typeof event.extra === "number" && event.extra > 0) {
    return `${event.time}+${event.extra}’`;
  }
  return `${event.time}’`;
}

function MatchLiveEventRow({ event }: { event: MatchLiveEvent }) {
  return (
    <div className="grid grid-cols-[3.25rem_1.5rem_minmax(0,1fr)] gap-2 border-t border-line/70 px-4 py-3 first:border-t-0">
      <span className="text-xs font-bold text-slate-400">
        {formatLiveEventMinute(event)}
      </span>
      <span className="text-sm">{getLiveEventIcon(event)}</span>
      <div className="min-w-0">
        <p className="truncate text-xs font-semibold text-slate-400">
          {event.team_name || "Команда"}
        </p>
        <p className="mt-0.5 truncate text-sm font-semibold text-white">
          {event.player || event.detail || event.type || "Событие матча"}
        </p>
        {event.assist && (
          <p className="mt-0.5 truncate text-xs text-slate-500">
            Ассист: {event.assist}
          </p>
        )}
      </div>
    </div>
  );
}

function AiAnalysisTextBlock({
  title,
  text,
}: {
  title: string;
  text: string;
}) {
  if (!text) return null;

  return (
    <section className="rounded-lg border border-line bg-panel p-4">
      <h3 className="text-xs font-bold uppercase text-slate-500">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-200">{text}</p>
    </section>
  );
}

function AiAnalysisSignalCard({
  signal,
}: {
  signal: MatchAiAnalysisSignal;
}) {
  const confidenceClass = {
    low: "bg-slate-500/10 text-slate-400",
    medium: "bg-amber-400/10 text-amber-200",
    high: "bg-lime/10 text-lime",
  }[signal.confidence];

  return (
    <div className="rounded-lg border border-line bg-white/[0.025] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">{signal.label}</p>
          <p className="mt-1 text-xs font-semibold text-accent">
            {signal.value}
          </p>
        </div>
        <span
          className={`shrink-0 rounded px-2 py-1 text-[9px] font-bold uppercase ${confidenceClass}`}
        >
          {signal.confidence}
        </span>
      </div>
      {signal.reason && (
        <p className="mt-2 text-xs leading-5 text-slate-400">
          {signal.reason}
        </p>
      )}
    </div>
  );
}

function AiStructuredAnalysis({
  analysis,
  home,
  away,
}: {
  analysis: MatchAiStructuredAnalysis;
  home: string;
  away: string;
}) {
  const probabilities = [
    {
      label: home || "Команда 1",
      value: analysis.outcome_probabilities.home_win,
    },
    {
      label: "Ничья",
      value: analysis.outcome_probabilities.draw,
    },
    {
      label: away || "Команда 2",
      value: analysis.outcome_probabilities.away_win,
    },
  ];

  return (
    <div className="space-y-3">
      <AiAnalysisTextBlock
        title="Краткий вывод"
        text={analysis.summary}
      />

      <section className="rounded-lg border border-line bg-panel p-4">
        <h3 className="text-xs font-bold uppercase text-slate-500">
          Вероятности исхода
        </h3>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {probabilities.map((item) => (
            <div
              key={item.label}
              className="min-w-0 rounded-md bg-white/[0.035] px-2 py-3 text-center"
            >
              <p className="truncate text-[10px] font-semibold text-slate-400">
                {item.label}
              </p>
              <p className="mt-1 text-xl font-black text-white">
                {item.value}%
              </p>
            </div>
          ))}
        </div>
      </section>

      {analysis.signals.length > 0 && (
        <section className="rounded-lg border border-line bg-panel p-4">
          <h3 className="text-xs font-bold uppercase text-slate-500">
            Статистические сигналы
          </h3>
          <div className="mt-3 space-y-2">
            {analysis.signals.map((signal) => (
              <AiAnalysisSignalCard
                key={`${signal.label}-${signal.value}`}
                signal={signal}
              />
            ))}
          </div>
        </section>
      )}

      <AiAnalysisTextBlock title="Контекст матча" text={analysis.context} />
      <AiAnalysisTextBlock title="Форма команд" text={analysis.form} />
      <AiAnalysisTextBlock
        title="Составы и потери"
        text={analysis.lineups_and_absences}
      />
      <AiAnalysisTextBlock
        title="Тактика и статистика"
        text={analysis.tactical_notes}
      />

      {analysis.risks.length > 0 && (
        <section className="rounded-lg border border-amber-400/15 bg-amber-400/[0.04] p-4">
          <h3 className="text-xs font-bold uppercase text-amber-200/70">
            Риски оценки
          </h3>
          <div className="mt-3 space-y-2">
            {analysis.risks.map((risk) => (
              <p
                key={risk}
                className="text-sm leading-5 text-slate-300 before:mr-2 before:text-amber-300 before:content-['•']"
              >
                {risk}
              </p>
            ))}
          </div>
        </section>
      )}

      <AiAnalysisTextBlock
        title="Итоговый сценарий"
        text={analysis.scenario}
      />

      {analysis.disclaimer && (
        <p className="px-2 text-[11px] leading-5 text-slate-500">
          {analysis.disclaimer}
        </p>
      )}
    </div>
  );
}

function MatchDetails({
  match,
  initialTab = "details",
  premiumAiEnabled,
  onBack,
  onOpenTeam,
  onOpenContextMatch,
  onOpenSubscription,
  reminderActive,
  reminderLoading,
  reminderActionError,
  onToggleReminder,
}: {
  match: MatchItem;
  initialTab?: MatchDetailTab;
  premiumAiEnabled: boolean;
  onBack: () => void;
  onOpenTeam: (team: TeamSearchItem) => void;
  onOpenContextMatch: (match: MatchContextMatch) => Promise<void>;
  onOpenSubscription: () => void;
  reminderActive: boolean;
  reminderLoading: boolean;
  reminderActionError: string;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const kickoff = formatKickoff(match.kickoff);
  const hasScore = hasNumericMatchScore(
    match.score.home,
    match.score.away,
  );
  const matchStatus = formatMatchStatus(match.status, hasScore);
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const [aiAnalysis, setAiAnalysis] =
    useState<MatchAiAnalysisSuccessResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [savedAiLoading, setSavedAiLoading] = useState(false);
  const [savedAiLoadFailed, setSavedAiLoadFailed] = useState(false);
  const [savedAiRetryKey, setSavedAiRetryKey] = useState(0);
  const savedAiRequestMatchIdRef = useRef<string | null>(null);
  const [activeTab, setActiveTab] = useState<MatchDetailTab>(initialTab);
  const [liveData, setLiveData] = useState<MatchLiveResponse | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState(false);
  const [matchContext, setMatchContext] =
    useState<MatchContextResponse | null>(null);
  const [contextLoading, setContextLoading] = useState(true);
  const [contextError, setContextError] = useState(false);
  const relevantStandings = useMemo(
    () =>
      matchContext
        ? getRelevantMatchStandings(
            matchContext.standings,
            matchContext.match_group,
          )
        : [],
    [matchContext],
  );

  useEffect(() => {
    let active = true;
    setContextLoading(true);
    setContextError(false);
    setMatchContext(null);

    getMatchContext(match.id)
      .then((response) => {
        if (active) {
          setMatchContext(response);
        }
      })
      .catch(() => {
        if (active) {
          setContextError(true);
        }
      })
      .finally(() => {
        if (active) {
          setContextLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [match.id]);

  useEffect(() => {
    setAiAnalysis(null);
    setAiError("");
    setSavedAiLoading(false);
    setSavedAiLoadFailed(false);
    savedAiRequestMatchIdRef.current = null;
  }, [match.id]);

  useEffect(() => {
    if (
      activeTab !== "ai" ||
      savedAiRequestMatchIdRef.current === match.id
    ) {
      return;
    }

    const requestedMatchId = match.id;
    savedAiRequestMatchIdRef.current = requestedMatchId;
    setSavedAiLoading(true);
    setSavedAiLoadFailed(false);

    getSavedMatchAiAnalysis(requestedMatchId, telegramIdentity.id)
      .then((response) => {
        if (savedAiRequestMatchIdRef.current === requestedMatchId) {
          if (!response.ok) {
            setAiAnalysis(null);
            setAiError("");
            setSavedAiLoadFailed(false);
            return;
          }
          setAiError("");
          setSavedAiLoadFailed(false);
          setAiAnalysis(response);
        }
      })
      .catch((error) => {
        if (
          savedAiRequestMatchIdRef.current === requestedMatchId &&
          !(
            error instanceof MatchAiAnalysisError &&
            (error.status === 404 || error.code === "analysis_not_found")
          )
        ) {
          setSavedAiLoadFailed(true);
          setAiError(
            "Не удалось загрузить AI-разбор. Можно повторить или сделать новый разбор.",
          );
        }
      })
      .finally(() => {
        if (savedAiRequestMatchIdRef.current === requestedMatchId) {
          setSavedAiLoading(false);
        }
      });
  }, [
    activeTab,
    match.id,
    savedAiRetryKey,
    telegramIdentity.id,
  ]);

  function retrySavedAiAnalysisLoad() {
    setAiError("");
    setSavedAiLoadFailed(false);
    savedAiRequestMatchIdRef.current = null;
    setSavedAiRetryKey((value) => value + 1);
  }

  const loadLiveData = useCallback(
    async (showLoader: boolean) => {
      if (showLoader) {
        setLiveLoading(true);
      }
      setLiveError(false);

      try {
        const response = await getMatchLive(match.id);
        setLiveData(response);
      } catch {
        setLiveError(true);
      } finally {
        if (showLoader) {
          setLiveLoading(false);
        }
      }
    },
    [match.id],
  );

  useEffect(() => {
    if (activeTab !== "live") return;
    void loadLiveData(true);
  }, [activeTab, loadLiveData]);

  useEffect(() => {
    if (
      activeTab !== "live" ||
      !liveData ||
      !["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"].includes(
        liveData.status.short.toLocaleUpperCase("en-US"),
      )
    ) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadLiveData(false);
    }, 60_000);

    return () => window.clearInterval(intervalId);
  }, [activeTab, liveData?.status.short, loadLiveData]);

  async function handleAiAnalysis() {
    setAiLoading(true);
    setAiError("");
    setSavedAiLoadFailed(false);
    const forceRefresh = Boolean(aiAnalysis);
    void trackMiniappEvent(telegramIdentity.id, "miniapp_ai_clicked", {
      ...buildMiniappMatchEventData(match, aiEventSource),
      analysis_mode_expected: premiumAiEnabled ? "premium" : "default",
    });

    try {
      const response = await requestMatchAiAnalysis(
        match.id,
        telegramIdentity.id,
        forceRefresh,
        true,
      );
      if (!response.ok) {
        if (response.status === "needs_unlock") {
          setAiAnalysis(null);
          setAiError("");
        } else if (response.status === "premium_required") {
          setAiError("Premium AI-разбор доступен по подписке.");
        } else if (response.status === "ai_limit_exceeded") {
          void trackMiniappEvent(
            telegramIdentity.id,
            "miniapp_ai_limit_reached",
            {
              match_id: match.id,
              source: "miniapp",
            },
          );
          setAiError(
            "AI-лимит закончился. Можно оформить подписку или докупить AI-разборы.",
          );
        } else {
          setAiError("Не удалось получить AI-разбор. Попробуйте позже.");
        }
        return;
      }
      setAiAnalysis(response);
      void trackMiniappEvent(telegramIdentity.id, "miniapp_ai_success", {
        match_id: match.id,
        analysis_mode: response.analysis_mode,
        limit_charged: response.limit_charged,
        charged: response.charged,
        source: response.source,
        from_personal_cache: response.from_personal_cache,
        from_global_cache: response.from_global_cache,
      });
    } catch (error) {
      if (error instanceof MatchAiAnalysisError) {
        if (error.status === 402 || error.code === "ai_limit_exceeded") {
          void trackMiniappEvent(
            telegramIdentity.id,
            "miniapp_ai_limit_reached",
            {
              match_id: match.id,
              source: "miniapp",
            },
          );
          setAiError(
            "AI-лимит закончился. Можно оформить подписку или докупить AI-разборы.",
          );
        } else if (error.code === "premium_required") {
          setAiError("Premium AI-разбор доступен по подписке.");
        } else if (error.status === 404 || error.code === "match_not_found") {
          setAiError("Матч не найден или уже недоступен.");
        } else if (
          error.status === 503 ||
          error.code === "ai_analysis_unavailable"
        ) {
          setAiError("AI-разбор временно недоступен.");
        } else if (
          error.status === 429 ||
          error.code === "ai_refresh_limit_exceeded"
        ) {
          setAiError(error.message);
        } else {
          setAiError("Не удалось получить AI-разбор. Попробуйте позже.");
        }
      } else {
        setAiError("Не удалось получить AI-разбор. Попробуйте позже.");
      }
    } finally {
      setAiLoading(false);
    }
  }

  const refreshLimitReached = Boolean(
    aiAnalysis &&
      !aiAnalysis.is_admin &&
      aiAnalysis.free_refreshes_left === 0,
  );
  const aiAnalysisMode = aiAnalysis?.analysis_mode || "default";
  const aiModeIsPremium = aiAnalysisMode === "premium";
  const aiActionText = premiumAiEnabled
    ? "Сделать Premium AI-разбор"
    : "Сделать базовый AI-разбор";
  const aiEventSource = initialTab === "ai" ? "daily_focus" : "match_details";

  return (
    <div className="animate-rise">
      <div className="mb-7 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-panel text-white"
          aria-label="Назад"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <p className="text-sm font-bold text-white">Матч</p>
          <p className="text-xs text-slate-500">{match.league}</p>
        </div>
      </div>

      <section className="pb-6 text-center">
        <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-4">
          <button
            type="button"
            disabled={!match.home_id}
            onClick={() =>
              match.home_id &&
              onOpenTeam({
                id: match.home_id,
                name: match.home,
                country: match.country,
                logo: match.home_logo,
                founded: null,
                national: false,
                venue_name: "",
                venue_city: "",
                venue_capacity: null,
              })
            }
            className="flex min-w-0 flex-col items-center disabled:cursor-default"
          >
            <TeamLogo logo={match.home_logo} name={match.home} size="lg" />
            <p className="mt-3 line-clamp-2 text-sm font-bold text-white">
              {match.home || "Хозяева"}
            </p>
          </button>
          <div className="pt-3">
            <p className="text-2xl font-black text-white">
              {hasScore
                ? `${match.score.home}:${match.score.away}`
                : kickoff.time}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {hasScore ? matchStatus : kickoff.date}
            </p>
            {canSetMatchReminder(match) && (
              <button
                type="button"
                onClick={() => onToggleReminder(match)}
                disabled={reminderLoading}
                className={`mx-auto mt-3 flex h-9 items-center justify-center gap-1.5 rounded-md px-3 text-xs font-semibold transition disabled:cursor-wait disabled:opacity-60 ${
                  reminderActive
                    ? "bg-lime/15 text-lime"
                    : "bg-panel text-slate-400"
                }`}
              >
                {reminderLoading ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Bell
                    className="h-4 w-4"
                    fill={reminderActive ? "currentColor" : "none"}
                  />
                )}
                {reminderActive ? "Включено" : "За 1 час"}
              </button>
            )}
          </div>
          <button
            type="button"
            disabled={!match.away_id}
            onClick={() =>
              match.away_id &&
              onOpenTeam({
                id: match.away_id,
                name: match.away,
                country: match.country,
                logo: match.away_logo,
                founded: null,
                national: false,
                venue_name: "",
                venue_city: "",
                venue_capacity: null,
              })
            }
            className="flex min-w-0 flex-col items-center disabled:cursor-default"
          >
            <TeamLogo logo={match.away_logo} name={match.away} size="lg" />
            <p className="mt-3 line-clamp-2 text-sm font-bold text-white">
              {match.away || "Гости"}
            </p>
          </button>
        </div>
      </section>

      {reminderActionError && (
        <p className="mb-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-center text-xs text-red-200">
          {reminderActionError}
        </p>
      )}

      <div className="-mx-4 overflow-x-auto border-y border-line px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-1">
          {matchDetailTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`relative h-12 px-4 text-sm font-semibold transition ${
                activeTab === tab.id
                  ? "text-white"
                  : "text-slate-500"
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-lime" />
              )}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "details" && (
        <section className="animate-rise py-6">
          <div className="mb-4 flex items-center gap-2">
            <LeagueLogo logo={match.league_logo} name={match.league} />
            <div>
              <h2 className="text-sm font-bold text-white">
                {match.league || "Турнир"}
              </h2>
              <p className="text-xs text-slate-500">
                {match.country || "Страна не указана"}
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-line bg-panel p-4">
            <p className="text-sm font-semibold text-white">
              Матчевый контекст и базовая информация
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] uppercase text-slate-500">
                  Начало
                </p>
                <p className="mt-1 text-sm font-semibold text-white">
                  {kickoff.date}, {kickoff.time}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-slate-500">
                  Статус
                </p>
                <p className="mt-1 text-sm font-semibold text-white">
                  {matchStatus}
                </p>
              </div>
            </div>
            {matchContext && (
              <div className="mt-4 border-t border-line pt-3">
                <p className="text-[10px] uppercase text-slate-500">
                  Источник данных
                </p>
                <p className="mt-1 text-xs font-semibold text-slate-300">
                  MatchLab
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {activeTab === "live" && (
        <section className="animate-rise py-6">
          {liveLoading && !liveData && <MatchContextLoading />}

          {!liveLoading && liveError && !liveData && (
            <div className="rounded-lg border border-line bg-panel px-5 py-10 text-center">
              <RefreshCw className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mt-4 text-sm font-semibold text-white">
                Live-данные временно недоступны.
              </p>
            </div>
          )}

          {liveData && (
            <div className="space-y-4">
              <div className="rounded-lg border border-line bg-panel p-5 text-center shadow-card">
                <p className="text-xs font-semibold text-slate-500">
                  {liveData.fixture.league || match.league}
                </p>
                <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
                  <div className="min-w-0">
                    <TeamLogo
                      logo={liveData.fixture.home_logo}
                      name={liveData.fixture.home}
                      size="sm"
                    />
                    <p className="mt-2 truncate text-xs font-bold text-white">
                      {liveData.fixture.home || match.home}
                    </p>
                  </div>
                  <div>
                    <p className="text-3xl font-black text-white">
                      {liveData.score.home ?? "—"}:
                      {liveData.score.away ?? "—"}
                    </p>
                    <p className="mt-1 text-xs font-semibold text-lime">
                      {formatMatchStatus(
                        liveData.status.short,
                        hasNumericMatchScore(
                          liveData.score.home,
                          liveData.score.away,
                        ),
                      )}
                      {typeof liveData.status.elapsed === "number"
                        ? ` · ${liveData.status.elapsed}’`
                        : ""}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <TeamLogo
                      logo={liveData.fixture.away_logo}
                      name={liveData.fixture.away}
                      size="sm"
                    />
                    <p className="mt-2 truncate text-xs font-bold text-white">
                      {liveData.fixture.away || match.away}
                    </p>
                  </div>
                </div>
                {liveError && (
                  <p className="mt-4 text-xs text-slate-500">
                    Не удалось обновить данные. Показана последняя версия.
                  </p>
                )}
              </div>

              {["NS", "TBD"].includes(
                liveData.status.short.toLocaleUpperCase("en-US"),
              ) ? (
                <div className="rounded-lg border border-line bg-panel px-4 py-6 text-center text-sm text-slate-400">
                  Live появится после начала матча.
                </div>
              ) : liveData.events.length > 0 ? (
                <div className="overflow-hidden rounded-lg border border-line bg-panel">
                  <div className="px-4 py-3">
                    <h2 className="text-sm font-bold text-white">
                      События матча
                    </h2>
                  </div>
                  {liveData.events.map((event, index) => (
                    <MatchLiveEventRow
                      key={`${event.time}-${event.extra}-${event.type}-${index}`}
                      event={event}
                    />
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-line bg-panel px-4 py-6 text-center text-sm text-slate-400">
                  Событий пока нет.
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {activeTab === "statistics" && (
        <section className="animate-rise py-6">
          {contextLoading && <MatchContextLoading />}

          {!contextLoading &&
            (contextError ||
              !matchContext?.statistics?.available ||
              matchContext.statistics.items.length === 0) && (
              <div className="py-10 text-center">
                <Activity className="mx-auto h-7 w-7 text-slate-600" />
                <p className="mt-4 text-sm font-semibold text-white">
                  Статистика матча пока недоступна.
                </p>
              </div>
            )}

          {!contextLoading &&
            !contextError &&
            matchContext?.statistics?.available &&
            matchContext.statistics.items.length > 0 && (
              <MatchStatisticsPanel
                match={match}
                statistics={matchContext.statistics}
              />
            )}
        </section>
      )}

      {activeTab === "lineups" && (
        <section className="animate-rise py-6">
          {contextLoading && <MatchContextLoading />}

          {!contextLoading &&
            (contextError ||
              !matchContext?.lineups?.available ||
              matchContext.lineups.teams.length === 0) && (
              <div className="rounded-lg border border-line bg-panel px-5 py-10 text-center shadow-card">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.035]">
                  <CircleUserRound className="h-6 w-6 text-slate-500" />
                </div>
                <p className="mt-4 text-sm font-semibold text-white">
                  Составы пока недоступны.
                </p>
                <p className="mx-auto mt-2 max-w-72 text-xs leading-5 text-slate-400">
                  Обычно они появляются ближе к началу матча.
                </p>
              </div>
            )}

          {!contextLoading &&
            !contextError &&
            matchContext?.lineups?.available &&
            matchContext.lineups.teams.length > 0 && (
              <MatchLineupsPanel
                teams={matchContext.lineups.teams}
                absences={matchContext.absences}
              />
            )}
        </section>
      )}

      {activeTab === "ai" && (
        <section className="animate-rise pt-6">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">
                AI-разбор MatchLab
              </h2>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                Матчевый контекст, форма команд и аналитические сигналы.
              </p>
            </div>
          </div>

          {aiAnalysis && (
            <div className="mt-5">
              <div className="mb-3 flex items-center gap-2">
                <div>
                  <span
                    className={`rounded px-2 py-1 text-[10px] font-bold uppercase ${
                      aiModeIsPremium
                        ? "bg-gold/15 text-gold"
                        : "bg-accent/10 text-accent"
                    }`}
                  >
                    {aiModeIsPremium
                      ? "👑 Premium AI-разбор"
                      : "🔓 Базовый AI-разбор"}
                  </span>
                  <p className="mt-2 text-[11px] text-slate-500">
                    {aiModeIsPremium
                      ? "Глубокая версия: вероятности, сценарии, расширенные сигналы и риски."
                      : "Краткая версия: общий сценарий, основные аргументы и риски."}
                  </p>
                </div>
              </div>
              {aiAnalysis.structured ? (
                <AiStructuredAnalysis
                  analysis={aiAnalysis.structured}
                  home={aiAnalysis.home}
                  away={aiAnalysis.away}
                />
              ) : (
                <div className="rounded-lg border border-accent/20 bg-panel p-4">
                  <div className="whitespace-pre-line text-sm leading-6 text-slate-200">
                    {aiAnalysis.analysis}
                  </div>
                </div>
              )}
              <div className="mt-4 border-t border-line pt-3">
                {aiAnalysis.is_admin && (
                  <p className="text-xs font-semibold text-lime">
                    Админ-режим: AI-разборы не расходуются.
                  </p>
                )}
                {typeof aiAnalysis.remaining_ai === "number" && (
                  <p className="text-xs font-semibold text-lime">
                    Осталось AI-разборов: {aiAnalysis.remaining_ai}
                  </p>
                )}
                {typeof aiAnalysis.free_refreshes_left === "number" && (
                  <p className="mt-2 text-xs leading-5 text-slate-400">
                    Доступно 2 бесплатных обновления. Лучше обновлять после
                    публикации стартовых составов.
                    <br />
                    Осталось бесплатных обновлений:{" "}
                    {aiAnalysis.free_refreshes_left}
                  </p>
                )}
                {refreshLimitReached && (
                  <p className="mt-2 text-xs font-semibold text-amber-200">
                    Бесплатные обновления для этого матча закончились.
                  </p>
                )}
              </div>
              {!aiModeIsPremium && (
                <div className="mt-4 rounded-lg border border-gold/20 bg-gold/[0.055] p-4">
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gold/15 text-gold">
                      <Crown className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-sm font-bold text-white">
                        Хочешь глубже?
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-slate-400">
                        Premium открывает расширенный разбор: вероятности,
                        сценарии, сигналы и риски.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      void trackMiniappEvent(
                        telegramIdentity.id,
                        "miniapp_premium_upsell_clicked",
                        {
                          source: "basic_ai_upsell",
                          match_id: match.id,
                        },
                      );
                      onOpenSubscription();
                    }}
                    className="mt-4 h-10 w-full rounded-md bg-gold text-sm font-bold text-zinc-950 transition active:scale-[0.98]"
                  >
                    Открыть Premium
                  </button>
                </div>
              )}
            </div>
          )}

          {aiError && (
            <div className="mt-5 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm leading-5 text-red-200">
              {aiError}
              {savedAiLoadFailed && (
                <button
                  type="button"
                  onClick={retrySavedAiAnalysisLoad}
                  className="mt-3 flex h-9 items-center justify-center gap-2 rounded-md bg-white/[0.06] px-3 text-xs font-semibold text-white transition active:scale-[0.99]"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Повторить загрузку
                </button>
              )}
            </div>
          )}

          {savedAiLoading && !aiAnalysis && (
            <div className="mt-5 flex items-center justify-center gap-2 rounded-lg border border-line bg-panel px-4 py-5 text-sm text-slate-400">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Загружаю AI-разбор…
            </div>
          )}

          <button
            type="button"
            onClick={handleAiAnalysis}
            disabled={aiLoading || savedAiLoading || refreshLimitReached}
            className="mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm font-bold text-white transition active:scale-[0.99] disabled:cursor-wait disabled:opacity-70"
          >
            {aiLoading ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Bot className="h-4 w-4" />
            )}
            {aiLoading
              ? "AI-разбор готовится…"
              : refreshLimitReached
                ? "Обновления закончились"
              : aiAnalysis
                ? "Обновить AI-разбор"
                : aiActionText}
          </button>
          {!aiAnalysis && !premiumAiEnabled && (
            <p className="mt-2 text-center text-[11px] text-slate-500">
              Глубокий разбор доступен в Premium
            </p>
          )}
        </section>
      )}

      {activeTab === "table" && (
        <section className="animate-rise py-6">
          {contextLoading && <MatchContextLoading />}

          {!contextLoading && contextError && (
            <div className="py-10 text-center">
              <Trophy className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mt-4 text-sm font-semibold text-white">
                Данные таблицы временно недоступны.
              </p>
            </div>
          )}

          {!contextLoading &&
            !contextError &&
            (!matchContext || matchContext.standings.length === 0) && (
              <div className="py-10 text-center">
                <Trophy className="mx-auto h-7 w-7 text-slate-600" />
                <p className="mt-4 text-sm font-semibold text-white">
                  Таблица для этого турнира пока недоступна.
                </p>
              </div>
            )}

          {!contextLoading &&
            !contextError &&
            matchContext &&
            matchContext.standings.length > 0 && (
              <StandingsTable
                rows={relevantStandings}
                highlightedTeams={[match.home, match.away]}
              />
            )}
        </section>
      )}

      {activeTab === "matches" && (
        <section className="animate-rise py-6">
          {contextLoading && <MatchContextLoading />}

          {!contextLoading && contextError && (
            <div className="py-10 text-center">
              <CalendarDays className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mx-auto mt-4 max-w-72 text-sm font-semibold leading-6 text-white">
                Данные матчей временно недоступны.
              </p>
            </div>
          )}

          {!contextLoading &&
            !contextError &&
            matchContext &&
            matchContext.h2h.length === 0 &&
            matchContext.home_recent.length === 0 &&
            matchContext.away_recent.length === 0 &&
            matchContext.upcoming.length === 0 && (
              <div className="py-10 text-center">
                <CalendarDays className="mx-auto h-7 w-7 text-slate-600" />
                <p className="mx-auto mt-4 max-w-72 text-sm font-semibold leading-6 text-white">
                  История и ближайшие матчи пока недоступны.
                </p>
              </div>
            )}

          {!contextLoading && !contextError && matchContext && (
            <div className="space-y-6">
              <MatchContextGroup
                title="Очные встречи"
                matches={matchContext.h2h}
                onOpenMatch={onOpenContextMatch}
              />
              <MatchContextGroup
                title={`Последние матчи: ${match.home}`}
                matches={matchContext.home_recent}
                onOpenMatch={onOpenContextMatch}
              />
              <MatchContextGroup
                title={`Последние матчи: ${match.away}`}
                matches={matchContext.away_recent}
                onOpenMatch={onOpenContextMatch}
              />
              <MatchContextGroup
                title="Ближайшие матчи"
                matches={matchContext.upcoming}
                onOpenMatch={onOpenContextMatch}
              />
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function favoriteTeamToSearchItem(
  favoriteTeam: FavoriteTeamItem,
): TeamSearchItem {
  return {
    id: favoriteTeam.team_id,
    name: favoriteTeam.team_name,
    logo: favoriteTeam.team_logo,
    country: favoriteTeam.team_country,
    founded: null,
    national: false,
    venue_name: "",
    venue_city: "",
    venue_capacity: null,
  };
}

function FavoritesScreen({
  teams,
  loading,
  loadError,
  actionError,
  removingTeamIds,
  reminders,
  remindersLoading,
  reminderLoadingIds,
  reminderActionError,
  onOpenTeam,
  onRemoveTeam,
  onOpenMatch,
  reminderMatchIds,
  onToggleReminder,
  onOpenReminder,
  onRemoveReminder,
}: {
  teams: FavoriteTeamItem[];
  loading: boolean;
  loadError: string;
  actionError: string;
  removingTeamIds: Set<number>;
  reminders: MatchReminderItem[];
  remindersLoading: boolean;
  reminderLoadingIds: Set<string>;
  reminderActionError: string;
  onOpenTeam: (team: TeamSearchItem) => void;
  onRemoveTeam: (team: TeamSearchItem) => void;
  onOpenMatch: (match: MatchItem) => void;
  reminderMatchIds: Set<string>;
  onToggleReminder: (match: MatchItem) => void;
  onOpenReminder: (reminder: MatchReminderItem) => void;
  onRemoveReminder: (reminder: MatchReminderItem) => void;
}) {
  const [activeFavoriteTab, setActiveFavoriteTab] =
    useState<FavoriteTab>("teams");
  const [favoriteTeamMatches, setFavoriteTeamMatches] = useState<
    FavoriteTeamMatchesGroup[]
  >([]);
  const [favoriteTeamMatchesLoading, setFavoriteTeamMatchesLoading] =
    useState(false);
  const [favoriteTeamMatchesError, setFavoriteTeamMatchesError] =
    useState("");
  const [loadedFavoriteTeamsKey, setLoadedFavoriteTeamsKey] = useState("");
  const favoriteTeamsToLoad = teams.slice(0, 10);
  const favoriteTeamsKey = favoriteTeamsToLoad
    .map((team) => team.team_id)
    .join(",");
  const visibleFavoriteTeamMatches = favoriteTeamMatches.filter((group) =>
    teams.some((team) => team.team_id === group.team.team_id),
  );

  useEffect(() => {
    if (
      activeFavoriteTab !== "matches" ||
      favoriteTeamsKey === loadedFavoriteTeamsKey
    ) {
      return;
    }

    if (!favoriteTeamsKey) {
      setFavoriteTeamMatches([]);
      setFavoriteTeamMatchesError("");
      setFavoriteTeamMatchesLoading(false);
      setLoadedFavoriteTeamsKey("");
      return;
    }

    let active = true;
    setFavoriteTeamMatchesLoading(true);
    setFavoriteTeamMatchesError("");

    Promise.allSettled(
      favoriteTeamsToLoad.map(async (team) => {
        const response = await getTeamMatches(team.team_id);
        return {
          team,
          matches: sortMatchesByImportance(response.upcoming).slice(0, 2),
        };
      }),
    )
      .then((results) => {
        if (!active) return;

        const loadedGroups = results.flatMap((result) =>
          result.status === "fulfilled" ? [result.value] : [],
        );
        const failedRequests = results.length - loadedGroups.length;

        setFavoriteTeamMatches(
          loadedGroups.filter((group) => group.matches.length > 0),
        );
        setLoadedFavoriteTeamsKey(favoriteTeamsKey);

        if (failedRequests === results.length) {
          setFavoriteTeamMatchesError(
            "Не удалось загрузить ближайшие матчи.",
          );
        } else if (failedRequests > 0) {
          setFavoriteTeamMatchesError(
            "Часть ближайших матчей временно недоступна.",
          );
        }
      })
      .finally(() => {
        if (active) setFavoriteTeamMatchesLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    activeFavoriteTab,
    favoriteTeamsKey,
    loadedFavoriteTeamsKey,
  ]);

  const favoriteTabs: Array<{ id: FavoriteTab; label: string }> = [
    { id: "teams", label: "Команды" },
    { id: "matches", label: "Матчи" },
    { id: "reminders", label: "Напоминания" },
  ];

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <p className="text-xs font-semibold uppercase text-slate-500">
        Личное пространство
      </p>
      <h1 className="mt-1 text-2xl font-extrabold text-white">Избранное</h1>

      <div className="mt-6 grid grid-cols-3 rounded-lg border border-line bg-panel p-1">
        {favoriteTabs.map((tab) => {
          const active = activeFavoriteTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveFavoriteTab(tab.id)}
              className={`min-w-0 rounded-md px-2 py-2.5 text-xs font-bold transition ${
                active
                  ? "bg-accent text-white shadow-card"
                  : "text-slate-500 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeFavoriteTab === "teams" && (
        <>
          {loading && (
            <div className="mt-7 flex min-h-40 items-center justify-center">
              <LoaderCircle className="h-6 w-6 animate-spin text-accent" />
            </div>
          )}

          {!loading && loadError && (
            <div className="mt-7 rounded-lg border border-line bg-panel px-4 py-8 text-center">
              <Star className="mx-auto h-7 w-7 text-slate-600" />
              <p className="mt-4 text-sm font-semibold text-white">
                {loadError}
              </p>
            </div>
          )}

          {!loading && !loadError && actionError && (
            <p className="mt-5 rounded-md bg-red-500/[0.08] px-3 py-2 text-sm text-red-200">
              {actionError}
            </p>
          )}

          {!loading && !loadError && teams.length === 0 && (
            <div className="mt-7 rounded-lg border border-line bg-panel px-5 py-10 text-center">
              <Star className="mx-auto h-8 w-8 text-slate-600" />
              <p className="mx-auto mt-4 max-w-64 text-sm leading-6 text-slate-400">
                Добавьте команду через поиск или профиль команды.
              </p>
            </div>
          )}

          {!loading && !loadError && teams.length > 0 && (
            <div className="mt-6 overflow-hidden rounded-lg border border-line bg-panel">
              {teams.map((favoriteTeam) => {
                const team = favoriteTeamToSearchItem(favoriteTeam);
                const removing = removingTeamIds.has(team.id);

                return (
                  <div
                    key={team.id}
                    className="flex items-center border-t border-line/80 first:border-t-0"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenTeam(team)}
                      className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left transition hover:bg-white/[0.035]"
                    >
                      <TeamLogo logo={team.logo} name={team.name} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">
                          {team.name}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          {team.country || "Страна не указана"}
                        </p>
                      </div>
                      <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-slate-500" />
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemoveTeam(team);
                      }}
                      disabled={removing}
                      className="mr-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gold/10 text-gold transition active:scale-95 disabled:cursor-wait disabled:opacity-60"
                      aria-label={`Удалить ${team.name} из избранного`}
                    >
                      {removing ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Star className="h-4 w-4" fill="currentColor" />
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {activeFavoriteTab === "matches" && (
        <section className="mt-6">
          {favoriteTeamMatchesError && (
            <p className="mb-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-sm text-red-200">
              {favoriteTeamMatchesError}
            </p>
          )}

          {favoriteTeamMatchesLoading && (
            <div className="flex min-h-40 items-center justify-center rounded-lg border border-line bg-panel">
              <LoaderCircle className="h-6 w-6 animate-spin text-accent" />
            </div>
          )}

          {!favoriteTeamMatchesLoading && teams.length === 0 && (
            <div className="rounded-lg border border-line bg-panel px-5 py-8 text-center">
              <Activity className="mx-auto h-8 w-8 text-slate-600" />
              <p className="mx-auto mt-4 max-w-64 text-sm leading-6 text-slate-400">
                Добавьте команду в избранное, чтобы видеть её ближайшие матчи.
              </p>
            </div>
          )}

          {!favoriteTeamMatchesLoading &&
            teams.length > 0 &&
            visibleFavoriteTeamMatches.length === 0 &&
            !favoriteTeamMatchesError && (
              <div className="rounded-lg border border-line bg-panel px-5 py-8 text-center">
                <CalendarDays className="mx-auto h-8 w-8 text-slate-600" />
                <p className="mt-4 text-sm text-slate-400">
                  Пока нет ближайших матчей избранных команд.
                </p>
              </div>
            )}

          {!favoriteTeamMatchesLoading &&
            visibleFavoriteTeamMatches.length > 0 && (
              <div className="space-y-5">
                {visibleFavoriteTeamMatches.map((group) => (
                  <section
                    key={group.team.team_id}
                    className="overflow-hidden rounded-lg border border-line bg-panel"
                  >
                    <div className="flex items-center gap-3 px-4 py-3">
                      <TeamLogo
                        logo={group.team.team_logo}
                        name={group.team.team_name}
                        size="xs"
                      />
                      <div className="min-w-0">
                        <h2 className="truncate text-sm font-bold text-white">
                          {group.team.team_name}
                        </h2>
                        <p className="truncate text-[11px] text-slate-500">
                          {group.team.team_country || "Страна не указана"}
                        </p>
                      </div>
                      <span className="ml-auto rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
                        {group.matches.length}
                      </span>
                    </div>
                    {group.matches.map((match) => (
                      <CompactMatchRow
                        key={match.id}
                        match={match}
                        onOpen={onOpenMatch}
                        reminderActive={reminderMatchIds.has(match.id)}
                        reminderLoading={
                          remindersLoading ||
                          reminderLoadingIds.has(match.id)
                        }
                        onToggleReminder={onToggleReminder}
                      />
                    ))}
                  </section>
                ))}
              </div>
            )}
        </section>
      )}

      {activeFavoriteTab === "reminders" && (
        <section className="mt-6">
          {reminderActionError && (
            <p className="mb-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-sm text-red-200">
              {reminderActionError}
            </p>
          )}

          {remindersLoading && (
            <div className="flex min-h-28 items-center justify-center rounded-lg border border-line bg-panel">
              <LoaderCircle className="h-5 w-5 animate-spin text-accent" />
            </div>
          )}

          {!remindersLoading && reminders.length === 0 && (
            <div className="rounded-lg border border-line bg-panel px-4 py-5">
              <p className="text-sm leading-6 text-slate-400">
                Нажмите 🔔 на будущем матче, чтобы получить уведомление за 1 час.
              </p>
            </div>
          )}

          {!remindersLoading && reminders.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-line bg-panel">
              {reminders.map((reminder) => {
                const reminderLoading = reminderLoadingIds.has(
                  reminder.match_id,
                );

                return (
                  <div
                    key={reminder.match_id}
                    className="flex items-center border-t border-line/80 first:border-t-0"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenReminder(reminder)}
                      disabled={reminderLoading}
                      className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left transition hover:bg-white/[0.035] disabled:cursor-wait disabled:opacity-60"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-lime/10 text-lime">
                        <Bell className="h-4 w-4" fill="currentColor" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">
                          {reminder.home_team} — {reminder.away_team}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-slate-500">
                          {reminder.league || "Турнир не указан"}
                        </p>
                        <p className="mt-1 text-[11px] font-semibold text-slate-300">
                          {formatReminderKickoff(reminder.kickoff)}
                        </p>
                        <p className="mt-0.5 text-[10px] text-slate-500">
                          Уведомление за 1 час до матча
                        </p>
                      </div>
                      <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-slate-500" />
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemoveReminder(reminder);
                      }}
                      disabled={reminderLoading}
                      className="mr-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/[0.05] text-slate-500 transition hover:text-red-200 active:scale-95 disabled:cursor-wait disabled:opacity-60"
                      aria-label={`Удалить напоминание ${reminder.home_team} — ${reminder.away_team}`}
                    >
                      {reminderLoading ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <X className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function ProfileScreen({
  onNavigate,
}: {
  onNavigate: (screen: Screen) => void;
}) {
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const [profile, setProfile] = useState<SubscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    getSubscription(telegramIdentity.id)
      .then(setProfile)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [telegramIdentity.id]);

  const remainingAi = profile
    ? Math.max(profile.ai_limit_monthly - profile.ai_used_monthly, 0) +
      profile.extra_ai_credits
    : 0;
  const premiumUntil = formatPremiumUntil(profile?.premium_until || null);
  const accessLabel = profile?.is_admin
    ? "Admin"
    : profile?.plan === "premium"
      ? "Premium"
      : "Free";
  const accessBadgeClass = profile?.is_admin
    ? "border-lime/25 bg-lime/10 text-lime"
    : profile?.plan === "premium"
      ? "border-gold/25 bg-gold/10 text-gold"
      : "border-line bg-white/[0.05] text-slate-300";
  const displayName =
    telegramIdentity.displayName ||
    (telegramIdentity.username
      ? `@${telegramIdentity.username}`
      : "Пользователь MatchLab");

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <p className="text-xs font-semibold uppercase text-slate-500">Аккаунт</p>
      <h1 className="mt-1 text-2xl font-extrabold text-white">
        Личный кабинет
      </h1>

      {loading && (
        <div className="flex min-h-80 items-center justify-center">
          <LoaderCircle className="h-7 w-7 animate-spin text-accent" />
        </div>
      )}

      {!loading && error && (
        <div className="py-16 text-center">
          <p className="text-sm font-semibold text-white">
            Профиль временно недоступен
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Попробуйте открыть экран позже.
          </p>
        </div>
      )}

      {!loading && profile && (
        <div className="mt-6 space-y-5">
          <section className="rounded-lg border border-line bg-panel p-5 shadow-card">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-accent/25 bg-accent/15 text-accent">
                <CircleUserRound className="h-7 w-7" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-base font-bold text-white">
                    {displayName}
                  </p>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${accessBadgeClass}`}
                  >
                    {accessLabel}
                  </span>
                </div>
                {telegramIdentity.username && (
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    @{telegramIdentity.username}
                  </p>
                )}
                <p className="mt-0.5 text-xs text-slate-400">
                  Telegram ID: {profile.telegram_user_id}
                </p>
                <p className="mt-1 text-[11px] font-semibold text-lime">
                  {telegramIdentity.mode === "telegram"
                    ? "Telegram Mini App"
                    : "Тестовый режим"}
                </p>
              </div>
            </div>
            {profile.is_admin && (
              <div className="mt-4 rounded-md border border-lime/15 bg-lime/[0.06] px-3 py-2.5">
                <div className="flex items-center gap-2 text-sm font-semibold text-lime">
                  <ShieldCheck className="h-4 w-4" />
                  Админ-доступ
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  AI-разборы доступны без лимита.
                </p>
                <p className="mt-2 text-[10px] leading-4 text-slate-500">
                  Telegram SDK:{" "}
                  {telegramIdentity.sdkAvailable ? "есть" : "нет"}
                  {" · "}
                  initData:{" "}
                  {telegramIdentity.initDataAvailable ? "есть" : "нет"}
                </p>
              </div>
            )}
          </section>

          <section>
            <p className="mb-3 text-xs font-semibold uppercase text-slate-500">
              Статус аккаунта
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="min-h-28 rounded-lg border border-line bg-panel p-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-gold/10 text-gold">
                  <Crown className="h-4 w-4" />
                </div>
                <p className="mt-4 text-xs text-slate-500">Premium</p>
                <p className="mt-1 text-sm font-bold text-white">
                  {profile.is_admin
                    ? "Админ-доступ"
                    : profile.plan === "premium" && premiumUntil
                      ? `До ${premiumUntil}`
                      : "Не активен"}
                </p>
              </div>

              <div className="min-h-28 rounded-lg border border-line bg-panel p-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent/15 text-accent">
                  <Bot className="h-4 w-4" />
                </div>
                <p className="mt-4 text-xs text-slate-500">AI-разборы</p>
                <p className="mt-1 text-sm font-bold text-white">
                  {profile.is_admin ? "Без лимита" : `Осталось: ${remainingAi}`}
                </p>
              </div>

              <div className="col-span-2 rounded-lg border border-line bg-panel p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-lime/10 text-lime">
                    <CircleUserRound className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500">Telegram ID</p>
                    <p className="mt-0.5 truncate text-sm font-bold text-white">
                      {profile.telegram_user_id}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section>
            <p className="mb-3 text-xs font-semibold uppercase text-slate-500">
              Быстрые действия
            </p>
            <div className="overflow-hidden rounded-lg border border-line bg-panel">
              {[
                {
                  label: "Подписка",
                  caption: "Тарифы и AI-пакеты",
                  icon: Crown,
                  iconClass: "bg-gold/10 text-gold",
                  screen: "subscription" as Screen,
                },
                {
                  label: "Избранное",
                  caption: "Команды, матчи и напоминания",
                  icon: Star,
                  iconClass: "bg-lime/10 text-lime",
                  screen: "favorites" as Screen,
                },
                {
                  label: "Матчи",
                  caption: "Расписание и турниры",
                  icon: Activity,
                  iconClass: "bg-accent/15 text-accent",
                  screen: "matches" as Screen,
                },
              ].map(({ label, caption, icon: Icon, iconClass, screen }) => (
                <button
                  key={screen}
                  type="button"
                  onClick={() => onNavigate(screen)}
                  className="flex w-full items-center gap-3 border-t border-line/80 px-4 py-3 text-left transition first:border-t-0 hover:bg-white/[0.035] active:bg-white/[0.06]"
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${iconClass}`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold text-white">
                      {label}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      {caption}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" />
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-line bg-panel p-5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-lime" />
              <h2 className="text-base font-bold text-white">Ваш доступ</h2>
            </div>
            <div className="mt-4 space-y-3">
              {[
                "AI-разборы обновляются согласно вашему пакету",
                "Premium и AI-пакеты активируются после проверки оплаты",
                "Все данные привязаны к Telegram-профилю",
              ].map((item) => (
                <div key={item} className="flex items-start gap-3">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-lime" />
                  <p className="text-sm leading-5 text-slate-400">{item}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function PackageIcon({ packageCode }: { packageCode: string }) {
  if (packageCode === "ai_30") return <Zap className="h-5 w-5" />;
  if (packageCode === "premium_30") return <Crown className="h-5 w-5" />;
  return <Trophy className="h-5 w-5" />;
}

function packageDescription(item: PaymentPackage) {
  if (item.code === "ai_30") {
    return "Разовый пакет базовых AI-разборов.";
  }
  if (item.code === "premium_30") {
    return "Глубокий Premium-разбор на расширенной AI-модели.";
  }
  if (item.code === "premium_90") {
    return "Лучший вариант для регулярного использования.";
  }
  return "Удобный доступ к возможностям MatchLab.";
}

function packageBenefits(item: PaymentPackage) {
  if (item.code === "ai_30") {
    return [
      "Обычная AI-модель",
      `${item.ai_credits ?? 30} базовых AI-разборов`,
      "Подходит для точечного анализа матчей",
    ];
  }
  if (item.code === "premium_30") {
    return [
      `${item.ai_limit ?? 100} глубоких AI-разборов на период`,
      "Вероятности и сценарии игры",
      "Форма команд, таблица, составы, потери и статистические сигналы",
      "Обновление сохранённых разборов после публикации составов",
    ];
  }
  if (item.code === "premium_90") {
    return [
      `${item.ai_limit ?? 350} глубоких AI-разборов на период`,
      "Глубокий Premium-разбор",
      "Вероятности и сценарии игры",
      "Форма команд, таблица, составы, потери и статистические сигналы",
      "Обновление сохранённых разборов после публикации составов",
    ];
  }
  return [];
}

function packageDisplayTitle(item: PaymentPackage) {
  if (item.code === "ai_30") return "30 AI-разборов";
  if (item.code === "premium_30") return "Premium на 1 месяц";
  if (item.code === "premium_90") return "Premium на 3 месяца";
  return item.title;
}

function formatPremiumUntil(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

function ReferralPremiumCard({
  status,
  loading,
}: {
  status: ReferralStatus | null;
  loading: boolean;
}) {
  const [copyStatus, setCopyStatus] = useState("");
  const invitedCount = status?.invited_count ?? 0;
  const targetCount = status?.target_count ?? 3;
  const rewardValue = status?.reward_value ?? 25;
  const bonusRemaining = status?.bonus_ai_remaining ?? 0;
  const bonusExpiresAt = status?.bonus_ai_expires_at
    ? formatPremiumUntil(status.bonus_ai_expires_at)
    : "";
  const progressPercent = Math.min(
    100,
    Math.round((invitedCount / Math.max(targetCount, 1)) * 100),
  );
  const referralLink = status?.referral_link || "";
  const shareText =
    "Я смотрю футбольные AI-разборы в MatchLab. Открой матчи дня и сценарии:";

  function shareReferralLink() {
    if (!referralLink) return;

    const shareUrl =
      "https://t.me/share/url" +
      `?url=${encodeURIComponent(referralLink)}` +
      `&text=${encodeURIComponent(shareText)}`;
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(shareUrl);
      return;
    }
    window.open(shareUrl, "_blank", "noopener,noreferrer");
  }

  async function copyReferralLink() {
    if (!referralLink) return;

    try {
      await navigator.clipboard?.writeText(referralLink);
      setCopyStatus("Ссылка скопирована");
    } catch {
      setCopyStatus(referralLink);
    }
  }

  return (
    <section className="mt-7 rounded-lg border border-lime/20 bg-lime/[0.055] p-5 shadow-card">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-lime/10 text-lime">
          <Gift className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-extrabold text-white">
            🎁 Получить Premium бесплатно
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-300">
            Пригласи 3 друзей и получи {rewardValue} Premium AI-разборов.
            <br />
            Бонус действует 30 дней.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-line/70 bg-white/[0.025] p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Прогресс
          </p>
          <p className="text-sm font-black text-white">
            {loading ? "—" : `${invitedCount} / ${targetCount}`}
          </p>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className="h-full rounded-full bg-lime transition-all"
            style={{ width: `${loading ? 0 : progressPercent}%` }}
          />
        </div>
        {!loading && status?.reward_granted && (
          <p className="mt-3 text-xs leading-5 text-lime">
            Награда активирована: {rewardValue} Premium AI-разборов добавлены.
          </p>
        )}
        {!loading && bonusRemaining > 0 && (
          <p className="mt-2 text-xs leading-5 text-slate-300">
            Доступно бонусных AI-разборов: {bonusRemaining}
            {bonusExpiresAt ? (
              <>
                <br />
                Бонус действует до {bonusExpiresAt}.
              </>
            ) : null}
          </p>
        )}
        {!loading && status?.is_premium && !status.reward_granted && (
          <p className="mt-3 text-xs leading-5 text-slate-400">
            Приглашай друзей — получишь ещё {rewardValue} Premium AI-разборов.
          </p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={shareReferralLink}
          disabled={!referralLink}
          className="flex h-10 items-center justify-center gap-2 rounded-md bg-lime text-xs font-bold text-zinc-950 transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Share2 className="h-4 w-4" />
          Поделиться
        </button>
        <button
          type="button"
          onClick={copyReferralLink}
          disabled={!referralLink}
          className="flex h-10 items-center justify-center gap-2 rounded-md bg-white/[0.06] text-xs font-bold text-white transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Copy className="h-4 w-4" />
          Скопировать
        </button>
      </div>
      {copyStatus && (
        <p className="mt-3 break-all text-center text-xs leading-5 text-slate-400">
          {copyStatus}
        </p>
      )}
    </section>
  );
}

function getMiniAppPaymentPackageCode(
  packageCode: string,
): MiniAppPaymentPackageCode | null {
  if (packageCode === "ai_30") return "ai_30";
  if (packageCode === "premium_30") return "month_1";
  if (packageCode === "premium_90") return "months_3";
  return null;
}

function SubscriptionScreen() {
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [subscription, setSubscription] =
    useState<SubscriptionData | null>(null);
  const [referralStatus, setReferralStatus] =
    useState<ReferralStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState(false);
  const [referralLoading, setReferralLoading] = useState(true);
  const [selectedPackage, setSelectedPackage] =
    useState<PaymentPackage | null>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [receiptError, setReceiptError] = useState("");
  const [receiptSuccess, setReceiptSuccess] =
    useState<PaymentReceiptResponse | null>(null);

  useEffect(() => {
    let active = true;

    Promise.allSettled([
      getAppConfig(),
      getSubscription(telegramIdentity.id),
      getReferralStatus(telegramIdentity.id),
    ])
      .then(([configResult, subscriptionResult, referralResult]) => {
        if (!active) return;

        if (configResult.status === "fulfilled") {
          setConfig(configResult.value);
        } else {
          setError(true);
        }

        if (subscriptionResult.status === "fulfilled") {
          setSubscription(subscriptionResult.value);
        } else {
          setSubscriptionError(true);
        }

        if (referralResult.status === "fulfilled") {
          setReferralStatus(referralResult.value);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          setReferralLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [telegramIdentity.id]);

  const remainingAi = subscription
    ? subscription.ai_remaining_total ??
      Math.max(
          subscription.ai_limit_monthly - subscription.ai_used_monthly,
          0,
        ) +
        subscription.extra_ai_credits +
        (subscription.bonus_ai_remaining ?? 0)
    : null;
  const premiumUntil = formatPremiumUntil(
    subscription?.premium_until || null,
  );
  function selectPackage(item: PaymentPackage) {
    void trackMiniappEvent(telegramIdentity.id, "payment_plan_selected", {
      package_code: item.code,
      source: "subscription",
    });
    setSelectedPackage(item);
    setReceiptFile(null);
    setReceiptError("");
    setReceiptSuccess(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function returnToPackages() {
    setSelectedPackage(null);
    setReceiptFile(null);
    setReceiptError("");
    setReceiptSuccess(null);
    setReceiptLoading(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleReceiptSubmit() {
    if (!selectedPackage || !receiptFile) {
      setReceiptError("Загрузите PDF-чек.");
      return;
    }

    if (
      receiptFile.type !== "application/pdf" &&
      !receiptFile.name.toLowerCase().endsWith(".pdf")
    ) {
      setReceiptError("Загрузите PDF-чек.");
      return;
    }

    const packageCode = getMiniAppPaymentPackageCode(
      selectedPackage.code,
    );
    if (!packageCode) {
      setReceiptError("Не удалось отправить чек. Попробуйте позже.");
      return;
    }

    setReceiptLoading(true);
    setReceiptError("");
    setReceiptSuccess(null);
    try {
      void trackMiniappEvent(telegramIdentity.id, "payment_started", {
        package_code: selectedPackage.code,
        source: "subscription",
      });
      const response = await submitPaymentReceipt(
        telegramIdentity.id,
        packageCode,
        receiptFile,
      );
      setReceiptSuccess(response);
    } catch (submitError) {
      if (submitError instanceof PaymentReceiptError) {
        if (submitError.code === "invalid_receipt") {
          setReceiptError("Загрузите PDF-чек.");
        } else {
          setReceiptError(
            submitError.message ||
              "Не удалось отправить чек. Попробуйте позже.",
          );
        }
      } else {
        setReceiptError("Не удалось отправить чек. Попробуйте позже.");
      }
    } finally {
      setReceiptLoading(false);
    }
  }

  if (selectedPackage) {
    return (
      <div className="animate-rise">
        <AppHeader compact />
        <button
          type="button"
          onClick={returnToPackages}
          className="mb-5 flex items-center gap-2 text-sm font-semibold text-slate-300"
        >
          <ArrowLeft className="h-4 w-4" />
          Назад к тарифам
        </button>

        <p className="text-xs font-semibold uppercase text-slate-500">
          Оплата
        </p>
        <h1 className="mt-1 text-2xl font-extrabold text-white">
          {selectedPackage.title}
        </h1>
        <p className="mt-2 text-xl font-black text-gold">
          {formatPrice(selectedPackage.price_kzt)} ₸
        </p>

        <section className="mt-6 rounded-lg border border-line bg-panel p-5">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Реквизиты
          </p>
          <div className="mt-4 space-y-3">
            <div>
              <p className="text-xs text-slate-500">Получатель</p>
              <p className="mt-1 text-sm font-bold text-white">Эльдар.Д</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Карта / номер</p>
              <p className="mt-1 break-all text-sm font-bold text-white">
                4400430320823104
              </p>
            </div>
          </div>
          <p className="mt-5 border-t border-line pt-4 text-sm leading-6 text-slate-300">
            Оплатите переводом на карту, затем загрузите PDF-чек.
          </p>
        </section>

        <section className="mt-4 rounded-lg border border-line bg-panel p-5">
          {receiptSuccess ? (
            <div>
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-lime/10 text-lime">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-lg font-bold text-white">
                Чек отправлен на проверку
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                После проверки доступ будет активирован админом. Обычно это
                занимает немного времени.
              </p>
              <div className="mt-5 space-y-3 rounded-lg bg-white/[0.03] p-4">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-xs text-slate-500">Пакет</span>
                  <span className="text-right text-sm font-semibold text-white">
                    {receiptSuccess.package_title}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-xs text-slate-500">Сумма</span>
                  <span className="text-sm font-semibold text-white">
                    {formatPrice(receiptSuccess.amount)} ₸
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-xs text-slate-500">Статус</span>
                  <span className="text-sm font-semibold text-gold">
                    На проверке
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={returnToPackages}
                className="mt-5 h-11 w-full rounded-md bg-white/[0.06] text-sm font-bold text-white transition active:scale-[0.99]"
              >
                Вернуться к тарифам
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-accent" />
                <div>
                  <p className="text-sm font-bold text-white">PDF-чек</p>
                  <p className="text-xs text-slate-500">
                    Выберите файл после оплаты
                  </p>
                </div>
              </div>
              <label className="mt-4 flex min-h-24 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-600 bg-white/[0.02] px-4 text-center">
                <Upload className="h-5 w-5 text-slate-400" />
                <span className="mt-2 text-sm font-semibold text-slate-200">
                  {receiptFile ? receiptFile.name : "Выбрать PDF-файл"}
                </span>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  onChange={(event) => {
                    setReceiptFile(event.target.files?.[0] || null);
                    setReceiptError("");
                    setReceiptSuccess(null);
                  }}
                />
              </label>

              {receiptError && (
                <p className="mt-4 rounded-md bg-red-500/[0.08] px-3 py-2 text-sm text-red-200">
                  {receiptError}
                </p>
              )}
              <button
                type="button"
                onClick={handleReceiptSubmit}
                disabled={receiptLoading}
                className="mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm font-bold text-white transition active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {receiptLoading ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                {receiptLoading
                  ? "Чек отправляется…"
                  : "Отправить PDF-чек"}
              </button>
            </>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <section className="overflow-hidden rounded-lg border border-gold/20 bg-gold/[0.055] p-5 shadow-card">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-gold/15 text-gold">
            <Crown className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gold/80">
              Больше возможностей
            </p>
            <h1 className="mt-1 text-2xl font-extrabold text-white">
              Premium MatchLab
            </h1>
          </div>
        </div>
        <p className="mt-4 text-sm leading-6 text-slate-300">
          Полные AI-разборы матчей: форма, мотивация, риски, сценарии игры,
          вероятности и расширенный контекст.
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Для тех, кто следит за футболом каждый день и хочет быстро понимать,
          что важно в матче.
        </p>

        <div className="mt-5 grid gap-2 border-t border-gold/15 pt-4">
          {loading ? (
            <>
              <div className="h-4 w-44 animate-pulseSoft rounded bg-white/10" />
              <div className="h-4 w-36 animate-pulseSoft rounded bg-white/10" />
            </>
          ) : subscriptionError || !subscription ? (
            <p className="text-xs text-slate-400">
              Статус подписки временно недоступен.
            </p>
          ) : subscription.is_admin ? (
            <>
              <div className="flex items-center gap-2 text-sm font-semibold text-lime">
                <ShieldCheck className="h-4 w-4" />
                Админ-доступ: без лимита
              </div>
              <p className="text-xs text-slate-400">
                AI-разборы доступны без ограничений.
              </p>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs text-slate-400">Статус</span>
                <span
                  className={`text-right text-xs font-bold ${
                    subscription.plan === "premium"
                      ? "text-lime"
                      : "text-slate-300"
                  }`}
                >
                  {subscription.plan === "premium" && premiumUntil
                    ? `Premium активен до: ${premiumUntil}`
                    : "Premium не активен"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs text-slate-400">AI-разборы</span>
                <span className="text-right text-xs font-bold text-white">
                  Осталось AI-разборов: {remainingAi}
                </span>
              </div>
            </>
          )}
        </div>
      </section>

      <ReferralPremiumCard
        status={referralStatus}
        loading={referralLoading}
      />

      {loading && (
        <div className="mt-7 space-y-3">
          {Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="h-40 animate-pulseSoft rounded-lg bg-panel"
            />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="py-16 text-center">
          <WalletCards className="mx-auto h-8 w-8 text-slate-600" />
          <p className="mt-4 text-sm font-semibold text-white">
            Тарифы временно недоступны
          </p>
        </div>
      )}

      {!loading && config && (
        <section className="mt-7 rounded-lg border border-line bg-panel p-5 shadow-card">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-accent" />
            <h2 className="text-base font-bold text-white">
              Базовый и Premium AI-разбор
            </h2>
          </div>
          <div className="mt-4 grid gap-3">
            <div className="rounded-md border border-line/80 bg-white/[0.025] p-4">
              <p className="text-xs font-bold uppercase text-slate-500">
                Free
              </p>
              <div className="mt-3 space-y-2">
                {[
                  "5 базовых AI-разборов в месяц",
                  "Краткий сценарий матча",
                  "Основные аргументы",
                  "Главный риск",
                ].map((item) => (
                  <p
                    key={item}
                    className="text-xs leading-5 text-slate-300 before:mr-2 before:text-accent before:content-['•']"
                  >
                    {item}
                  </p>
                ))}
              </div>
            </div>
            <div className="rounded-md border border-gold/20 bg-gold/[0.055] p-4">
              <p className="text-xs font-bold uppercase text-gold">
                Premium
              </p>
              <div className="mt-3 space-y-2">
                {[
                  "Больше глубоких AI-разборов",
                  "Вероятности",
                  "Расширенные сигналы",
                  "Сценарии матча",
                  "Сценарии дня",
                  "Форма команд",
                  "Риски и контекст",
                ].map((item) => (
                  <p
                    key={item}
                    className="text-xs leading-5 text-slate-300 before:mr-2 before:text-gold before:content-['•']"
                  >
                    {item}
                  </p>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {!loading && config && (
        <section className="mt-7">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Выберите пакет
          </p>
          <h2 className="mt-1 text-xl font-extrabold text-white">
            Тарифы и AI-разборы
          </h2>

          <div className="mt-4 space-y-3">
          {config.packages.map((item, index) => {
            const premium = item.code !== "ai_30";
            const longPremium = item.code === "premium_90";
            return (
              <article
                key={item.code}
                className={`animate-rise rounded-lg border p-5 shadow-card ${
                  longPremium
                    ? "border-lime/30 bg-lime/[0.045]"
                    : premium
                    ? "border-gold/25 bg-gold/[0.06]"
                    : "border-line bg-panel"
                }`}
                style={{ animationDelay: `${index * 70}ms` }}
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                      longPremium
                        ? "bg-lime/10 text-lime"
                        : premium
                        ? "bg-gold/15 text-gold"
                        : "bg-accent/15 text-accent"
                    }`}
                  >
                    <PackageIcon packageCode={item.code} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white">
                      {packageDisplayTitle(item)}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">
                      {packageDescription(item)}
                    </p>
                  </div>
                  <p className="whitespace-nowrap text-base font-black text-white">
                    {formatPrice(item.price_kzt)} ₸
                  </p>
                </div>
                <div className="mt-4 space-y-2 border-t border-line/70 pt-4">
                  {packageBenefits(item).map((benefit) => (
                    <div key={benefit} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-lime" />
                      <p className="text-xs leading-5 text-slate-300">
                        {benefit}
                      </p>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => selectPackage(item)}
                  className={`mt-5 h-11 w-full rounded-md text-sm font-bold transition active:scale-[0.99] ${
                    longPremium
                      ? "bg-lime text-zinc-950"
                      : premium
                      ? "bg-gold text-zinc-950"
                      : "bg-accent text-white"
                  }`}
                >
                  Выбрать пакет
                </button>
              </article>
            );
          })}
          </div>
        </section>
      )}

      {!loading && config && (
        <>
          <section className="mt-7 rounded-lg border border-line bg-panel p-5">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-accent" />
              <h2 className="text-base font-bold text-white">
                Что даёт Premium
              </h2>
            </div>
            <div className="mt-4 grid gap-3">
              {[
                "Глубокий AI-разбор матча",
                "Вероятности и сценарии игры",
                "Форма команд и турнирный контекст",
                "Риски, составы и статистические сигналы",
                "Обновление сохранённых разборов после составов",
                "Сценарии дня: понятный, сбалансированный и смелый",
              ].map((item) => (
                <div key={item} className="flex items-center gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-lime/10 text-lime">
                    <ShieldCheck className="h-3 w-3" />
                  </span>
                  <p className="text-sm text-slate-300">{item}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 border-t border-line pt-4 text-xs leading-5 text-slate-500">
              Избранные команды, напоминания и профиль доступны всем
              пользователям. Premium усиливает именно AI-разборы.
            </p>
          </section>

          <section className="mt-4 rounded-lg border border-line bg-panel p-5">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-gold" />
              <h2 className="text-base font-bold text-white">Как оплатить</h2>
            </div>
            <div className="mt-4 space-y-3">
              {[
                "Выберите пакет",
                "Переведите сумму",
                "Загрузите PDF-чек",
                "После проверки доступ активируется",
              ].map((item, index) => (
                <div key={item} className="flex items-center gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/[0.05] text-[11px] font-bold text-slate-300">
                    {index + 1}
                  </span>
                  <p className="text-sm text-slate-300">{item}</p>
                </div>
              ))}
            </div>
          </section>

          <div className="mt-6 flex items-start gap-3 border-t border-line pt-5">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-lime" />
            <p className="text-xs leading-5 text-slate-500">
              Доступ привязан к вашему Telegram-профилю. MatchLab — это
              аналитика на основе данных, а не обещание результата.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function BottomNavigation({
  activeScreen,
  onNavigate,
}: {
  activeScreen: Screen;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-lg border-t border-line bg-[#0b0f15]/95 px-2 pb-[max(0.55rem,env(safe-area-inset-bottom))] pt-2 shadow-nav backdrop-blur-xl">
      <div className="grid grid-cols-5">
        {navigation.map(({ id, label, icon: Icon }) => {
          const active = activeScreen === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onNavigate(id)}
              className={`flex min-h-12 flex-col items-center justify-center gap-1 text-[10px] font-semibold transition ${
                active ? "text-lime" : "text-slate-500"
              }`}
            >
              <Icon className="h-5 w-5" strokeWidth={active ? 2.4 : 1.8} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function getInitialScreenFromUrl(): Screen {
  const requestedScreen = new URLSearchParams(
    window.location.search,
  ).get("screen");

  return requestedScreen === "profile" ? "profile" : "home";
}

function getInitialMatchIdFromUrl() {
  return (
    new URLSearchParams(window.location.search).get("match_id")?.trim() || ""
  );
}

function shouldShowInitialOnboarding() {
  const params = new URLSearchParams(window.location.search);
  const matchId = params.get("match_id")?.trim() || "";
  const requestedScreen = params.get("screen");

  if (matchId || requestedScreen === "profile") {
    return false;
  }

  try {
    return window.localStorage.getItem(ONBOARDING_STORAGE_KEY) !== "true";
  } catch {
    return false;
  }
}

function markOnboardingSeen() {
  try {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, "true");
  } catch {
    return;
  }
}

function OnboardingOverlay({
  onStart,
  onLater,
}: {
  onStart: () => void;
  onLater: () => void;
}) {
  const steps = [
    {
      label: "Откройте матч",
      icon: Activity,
      iconClass: "bg-accent/15 text-accent",
    },
    {
      label: "Включите 🔔 за 1 час до начала",
      icon: Bell,
      iconClass: "bg-lime/10 text-lime",
    },
    {
      label: "Посмотрите детали, таблицу и AI-разбор",
      icon: Bot,
      iconClass: "bg-violet-500/15 text-violet-300",
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/75 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="matchlab-onboarding-title"
    >
      <section className="w-full max-w-md animate-rise rounded-lg border border-line bg-panel p-5 shadow-card">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-white">
          <Sparkles className="h-5 w-5" />
        </div>
        <h1
          id="matchlab-onboarding-title"
          className="mt-5 text-2xl font-extrabold text-white"
        >
          Добро пожаловать в MatchLab
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          Следите за матчами, командами и турнирами, включайте напоминания и
          открывайте AI-разбор в одном месте.
        </p>

        <div className="mt-6 space-y-3">
          {steps.map(({ label, icon: Icon, iconClass }, index) => (
            <div
              key={label}
              className="flex items-center gap-3 rounded-md border border-line/80 bg-white/[0.025] p-3"
            >
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${iconClass}`}
              >
                <Icon className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase text-slate-600">
                  Шаг {index + 1}
                </p>
                <p className="mt-0.5 text-sm font-semibold text-slate-200">
                  {label}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={onLater}
            className="h-12 rounded-md border border-line bg-white/[0.04] text-sm font-bold text-slate-300 transition hover:bg-white/[0.07] active:scale-[0.98]"
          >
            Позже
          </button>
          <button
            type="button"
            onClick={onStart}
            className="h-12 rounded-md bg-accent text-sm font-bold text-white shadow-card transition active:scale-[0.98]"
          >
            Начать
          </button>
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const telegramStartParam = useMemo(getTelegramStartParam, []);
  const initialMatchId = useMemo(getInitialMatchIdFromUrl, []);
  const [screen, setScreen] = useState<Screen>(getInitialScreenFromUrl);
  const [matchType, setMatchType] = useState<MatchListType>("top");
  const [dailyFocusMode, setDailyFocusMode] = useState(false);
  const [selectedMatch, setSelectedMatch] = useState<MatchItem | null>(null);
  const [selectedMatchInitialTab, setSelectedMatchInitialTab] =
    useState<MatchDetailTab>("details");
  const [matchHistory, setMatchHistory] = useState<MatchItem[]>([]);
  const [selectedTournament, setSelectedTournament] =
    useState<TournamentSelection | null>(null);
  const [selectedTeam, setSelectedTeam] =
    useState<TeamSearchItem | null>(null);
  const [teamBeforeMatch, setTeamBeforeMatch] =
    useState<TeamSearchItem | null>(null);
  const [favoriteTeams, setFavoriteTeams] = useState<FavoriteTeamItem[]>([]);
  const [favoritesLoading, setFavoritesLoading] = useState(true);
  const [favoritesLoadError, setFavoritesLoadError] = useState("");
  const [favoriteActionError, setFavoriteActionError] = useState("");
  const [favoriteLoadingIds, setFavoriteLoadingIds] = useState<Set<number>>(
    new Set(),
  );
  const [matchReminders, setMatchReminders] = useState<MatchReminderItem[]>([]);
  const [remindersLoading, setRemindersLoading] = useState(true);
  const [reminderLoadingIds, setReminderLoadingIds] = useState<Set<string>>(
    new Set(),
  );
  const [reminderActionError, setReminderActionError] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] =
    useState<SubscriptionData | null>(null);
  const [deepLinkLoading, setDeepLinkLoading] = useState(
    Boolean(initialMatchId),
  );
  const [deepLinkError, setDeepLinkError] = useState("");
  const [onboardingVisible, setOnboardingVisible] = useState(
    shouldShowInitialOnboarding,
  );
  const reminderMatchIds = useMemo(
    () => new Set(matchReminders.map((reminder) => reminder.match_id)),
    [matchReminders],
  );
  const premiumAiEnabled = Boolean(
    subscriptionStatus?.is_admin ||
      subscriptionStatus?.plan === "premium" ||
      (subscriptionStatus?.bonus_ai_remaining ?? 0) > 0,
  );

  function trackEvent(
    eventType: string,
    eventData: Record<string, unknown> = {},
  ) {
    void trackMiniappEvent(telegramIdentity.id, eventType, eventData);
  }

  useEffect(() => {
    const telegramWebApp = window.Telegram?.WebApp;
    telegramWebApp?.ready();
    telegramWebApp?.expand();

    document.documentElement.dataset.telegramTheme =
      telegramWebApp?.colorScheme || "dark";
  }, []);

  useEffect(() => {
    void trackMiniappEvent(
      telegramIdentity.id,
      "miniapp_opened",
      {},
      { startParam: telegramStartParam || undefined },
    );
  }, [telegramIdentity.id, telegramStartParam]);

  useEffect(() => {
    if (!onboardingVisible) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [onboardingVisible]);

  useEffect(() => {
    let active = true;
    if (!initialMatchId) {
      return () => {
        active = false;
      };
    }

    getMatch(initialMatchId)
      .then((response) => {
        if (!active) return;
        setScreen("matches");
        setDailyFocusMode(false);
        setMatchHistory([]);
        setSelectedMatchInitialTab("details");
        setSelectedMatch(response.match);
      })
      .catch(() => {
        if (!active) return;
        setScreen("matches");
        setDailyFocusMode(false);
        setDeepLinkError("Не удалось открыть матч из уведомления.");
      })
      .finally(() => {
        if (active) setDeepLinkLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialMatchId]);

  useEffect(() => {
    let active = true;
    setFavoritesLoading(true);
    setFavoritesLoadError("");

    getFavoriteTeams(telegramIdentity.id)
      .then((response) => {
        if (!active) return;
        if (!response.ok) {
          throw new Error(response.error || "Favorites error");
        }
        setFavoriteTeams(response.items || []);
      })
      .catch(() => {
        if (active) {
          setFavoritesLoadError(
            "Избранные команды временно недоступны.",
          );
        }
      })
      .finally(() => {
        if (active) setFavoritesLoading(false);
      });

    return () => {
      active = false;
    };
  }, [telegramIdentity.id]);

  useEffect(() => {
    let active = true;
    setRemindersLoading(true);

    getMatchReminders(telegramIdentity.id)
      .then((response) => {
        if (!active) return;
        if (!response.ok) {
          throw new Error(response.error || "Reminders error");
        }
        setMatchReminders(response.items || []);
      })
      .catch(() => {
        if (active) {
          setReminderActionError("Напоминания временно недоступны.");
        }
      })
      .finally(() => {
        if (active) setRemindersLoading(false);
      });

    return () => {
      active = false;
    };
  }, [telegramIdentity.id]);

  useEffect(() => {
    let active = true;

    getSubscription(telegramIdentity.id)
      .then((response) => {
        if (active) setSubscriptionStatus(response);
      })
      .catch(() => {
        if (active) setSubscriptionStatus(null);
      });

    return () => {
      active = false;
    };
  }, [telegramIdentity.id]);

  function navigate(nextScreen: Screen, source = "unknown") {
    if (nextScreen === "subscription") {
      trackEvent("subscription_opened", { source });
    }
    setDailyFocusMode(false);
    setSelectedMatch(null);
    setMatchHistory([]);
    setSelectedTournament(null);
    setSelectedTeam(null);
    setTeamBeforeMatch(null);
    setScreen(nextScreen);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openMatches(type: MatchListType) {
    setDailyFocusMode(false);
    setMatchType(type);
    navigate("matches");
  }

  function openDailyFocusMatches() {
    trackEvent("daily_focus_opened", { source: "home_cta" });
    setDailyFocusMode(true);
    setMatchType("top");
    setSelectedMatch(null);
    setMatchHistory([]);
    setSelectedTournament(null);
    setSelectedTeam(null);
    setTeamBeforeMatch(null);
    setScreen("matches");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openSubscription(source: string) {
    navigate("subscription", source);
  }

  function closeOnboarding(nextScreen?: Screen) {
    markOnboardingSeen();
    setOnboardingVisible(false);
    if (nextScreen) {
      navigate(nextScreen);
    }
  }

  async function toggleFavoriteTeam(team: TeamSearchItem) {
    if (favoriteLoadingIds.has(team.id)) {
      return;
    }

    const previousFavorite = favoriteTeams.find(
      (favoriteTeam) => favoriteTeam.team_id === team.id,
    );
    const isFavorite = Boolean(previousFavorite);
    const optimisticTeam: FavoriteTeamItem = {
      team_id: team.id,
      team_name: team.name,
      team_logo: team.logo,
      team_country: team.country,
      created_at: new Date().toISOString(),
    };

    setFavoriteActionError("");
    setFavoriteLoadingIds((current) => new Set(current).add(team.id));
    setFavoriteTeams((current) =>
      isFavorite
        ? current.filter(
            (favoriteTeam) => favoriteTeam.team_id !== team.id,
          )
        : [optimisticTeam, ...current],
    );

    try {
      if (isFavorite) {
        await removeFavoriteTeam(telegramIdentity.id, team.id);
      } else {
        await addFavoriteTeam(telegramIdentity.id, team);
      }
    } catch {
      setFavoriteTeams((current) => {
        const withoutTeam = current.filter(
          (favoriteTeam) => favoriteTeam.team_id !== team.id,
        );
        return previousFavorite
          ? [previousFavorite, ...withoutTeam]
          : withoutTeam;
      });
      setFavoriteActionError(
        "Не удалось обновить избранное. Попробуйте позже.",
      );
    } finally {
      setFavoriteLoadingIds((current) => {
        const next = new Set(current);
        next.delete(team.id);
        return next;
      });
    }
  }

  async function toggleMatchReminder(match: MatchItem) {
    if (
      remindersLoading ||
      reminderLoadingIds.has(match.id) ||
      !canSetMatchReminder(match)
    ) {
      return;
    }

    const previousReminder = matchReminders.find(
      (reminder) => reminder.match_id === match.id,
    );
    const reminderActive = Boolean(previousReminder);

    setReminderActionError("");
    setReminderLoadingIds((current) => new Set(current).add(match.id));
    setMatchReminders((current) =>
      reminderActive
        ? current.filter((reminder) => reminder.match_id !== match.id)
        : [buildOptimisticMatchReminder(match), ...current],
    );

    try {
      if (reminderActive) {
        await removeMatchReminder(telegramIdentity.id, match.id);
      } else {
        await addMatchReminder(telegramIdentity.id, match);
      }
    } catch {
      setMatchReminders((current) => {
        const withoutMatch = current.filter(
          (reminder) => reminder.match_id !== match.id,
        );
        return previousReminder
          ? [previousReminder, ...withoutMatch]
          : withoutMatch;
      });
      setReminderActionError(
        "Не удалось обновить напоминание. Попробуйте позже.",
      );
    } finally {
      setReminderLoadingIds((current) => {
        const next = new Set(current);
        next.delete(match.id);
        return next;
      });
    }
  }

  async function openSavedReminder(reminder: MatchReminderItem) {
    if (reminderLoadingIds.has(reminder.match_id)) {
      return;
    }

    setReminderActionError("");
    setReminderLoadingIds((current) =>
      new Set(current).add(reminder.match_id),
    );

    try {
      const response = await getMatch(reminder.match_id);
      setTeamBeforeMatch(null);
      setMatchHistory([]);
      setSelectedMatchInitialTab("details");
      setSelectedMatch(response.match);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      setReminderActionError("Не удалось открыть матч.");
    } finally {
      setReminderLoadingIds((current) => {
        const next = new Set(current);
        next.delete(reminder.match_id);
        return next;
      });
    }
  }

  async function removeSavedReminder(reminder: MatchReminderItem) {
    if (reminderLoadingIds.has(reminder.match_id)) {
      return;
    }

    setReminderActionError("");
    setReminderLoadingIds((current) =>
      new Set(current).add(reminder.match_id),
    );
    setMatchReminders((current) =>
      current.filter((item) => item.match_id !== reminder.match_id),
    );

    try {
      await removeMatchReminder(telegramIdentity.id, reminder.match_id);
    } catch {
      setMatchReminders((current) => {
        const withoutReminder = current.filter(
          (item) => item.match_id !== reminder.match_id,
        );
        return [...withoutReminder, reminder].sort(
          (left, right) =>
            new Date(left.kickoff).getTime() -
            new Date(right.kickoff).getTime(),
        );
      });
      setReminderActionError(
        "Не удалось удалить напоминание. Попробуйте позже.",
      );
    } finally {
      setReminderLoadingIds((current) => {
        const next = new Set(current);
        next.delete(reminder.match_id);
        return next;
      });
    }
  }

  async function openContextMatch(contextMatch: MatchContextMatch) {
    const response = await getMatch(contextMatch.id);
    if (selectedMatch) {
      setMatchHistory((current) => [...current, selectedMatch]);
    }
    setSelectedMatchInitialTab("details");
    setSelectedMatch(response.match);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="min-h-dvh bg-canvas text-white">
      <main className="mx-auto min-h-dvh max-w-lg px-4 pb-28 pt-[max(1rem,env(safe-area-inset-top))]">
        {deepLinkLoading ? (
          <div className="animate-rise">
            <AppHeader compact />
            <div className="flex min-h-[60vh] items-center justify-center">
              <LoaderCircle className="h-7 w-7 animate-spin text-accent" />
            </div>
          </div>
        ) : selectedTeam ? (
          <TeamDetails
            team={selectedTeam}
            onBack={() => setSelectedTeam(null)}
            isFavorite={favoriteTeams.some(
              (favoriteTeam) =>
                favoriteTeam.team_id === selectedTeam.id,
            )}
            favoriteLoading={favoriteLoadingIds.has(selectedTeam.id)}
            favoriteError={favoriteActionError}
            onToggleFavorite={toggleFavoriteTeam}
            reminderMatchIds={reminderMatchIds}
            remindersLoading={remindersLoading}
            reminderLoadingIds={reminderLoadingIds}
            onToggleReminder={toggleMatchReminder}
            onOpenMatch={(match) => {
              setTeamBeforeMatch(selectedTeam);
              setSelectedTeam(null);
              setMatchHistory([]);
              setSelectedMatchInitialTab("details");
              setSelectedMatch(match);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        ) : selectedMatch ? (
          <MatchDetails
            key={`${selectedMatch.id}:${selectedMatchInitialTab}`}
            match={selectedMatch}
            initialTab={selectedMatchInitialTab}
            premiumAiEnabled={premiumAiEnabled}
            onBack={() => {
              const previousMatch = matchHistory[matchHistory.length - 1];
              if (previousMatch) {
                setMatchHistory((current) => current.slice(0, -1));
                setSelectedMatchInitialTab("details");
                setSelectedMatch(previousMatch);
                window.scrollTo({ top: 0, behavior: "smooth" });
                return;
              }
              setSelectedMatch(null);
              if (teamBeforeMatch) {
                setSelectedTeam(teamBeforeMatch);
                setTeamBeforeMatch(null);
              }
            }}
            onOpenTeam={(team) => {
              setSelectedTeam(team);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onOpenContextMatch={openContextMatch}
            onOpenSubscription={() => openSubscription("upsell")}
            reminderActive={reminderMatchIds.has(selectedMatch.id)}
            reminderLoading={
              remindersLoading || reminderLoadingIds.has(selectedMatch.id)
            }
            reminderActionError={reminderActionError}
            onToggleReminder={toggleMatchReminder}
          />
        ) : selectedTournament ? (
          <TournamentDetails
            tournament={selectedTournament}
            onBack={() => setSelectedTournament(null)}
            onOpenMatch={(match) => {
              setTeamBeforeMatch(null);
              setMatchHistory([]);
              setSelectedMatchInitialTab("details");
              setSelectedMatch(match);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            reminderMatchIds={reminderMatchIds}
            remindersLoading={remindersLoading}
            reminderLoadingIds={reminderLoadingIds}
            onToggleReminder={toggleMatchReminder}
          />
        ) : (
          <>
            {screen === "home" && (
              <HomeScreen
                onNavigate={navigate}
                onOpenDailyMatches={openDailyFocusMatches}
                favoriteTeams={favoriteTeams}
                matchReminders={matchReminders}
                reminderMatchIds={reminderMatchIds}
                reminderLoadingIds={reminderLoadingIds}
                remindersLoading={remindersLoading}
                onToggleReminder={toggleMatchReminder}
                onOpenMatch={(match) => {
                  setTeamBeforeMatch(null);
                  setMatchHistory([]);
                  setSelectedMatchInitialTab("details");
                  setSelectedMatch(match);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                onOpenReminder={openSavedReminder}
              />
            )}
            {screen === "matches" && (
              <MatchesScreen
                initialType={matchType}
                dailyFocusMode={dailyFocusMode}
                premiumAiEnabled={premiumAiEnabled}
                onOpenMatch={(match) => {
                  trackEvent(
                    dailyFocusMode
                      ? "daily_focus_match_selected"
                      : "miniapp_match_selected",
                    buildMiniappMatchEventData(
                      match,
                      dailyFocusMode ? "daily_focus" : "matches",
                    ),
                  );
                  setTeamBeforeMatch(null);
                  setMatchHistory([]);
                  setSelectedMatchInitialTab(
                    dailyFocusMode ? "ai" : "details",
                  );
                  setSelectedMatch(match);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                onOpenAllMatches={() => {
                  setDailyFocusMode(false);
                  setMatchType("top");
                }}
                onOpenSubscription={() => {
                  trackEvent("scenarios_teaser_clicked", {
                    source: "daily_focus_scenarios",
                  });
                  openSubscription("scenarios");
                }}
                onOpenTournament={(tournament) => {
                  setSelectedTournament(tournament);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                onOpenTeam={(team) => {
                  setSelectedTeam(team);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                reminderMatchIds={reminderMatchIds}
                remindersLoading={remindersLoading}
                reminderLoadingIds={reminderLoadingIds}
                reminderActionError={reminderActionError}
                deepLinkError={deepLinkError}
                onToggleReminder={toggleMatchReminder}
              />
            )}
            {screen === "favorites" && (
              <FavoritesScreen
                teams={favoriteTeams}
                loading={favoritesLoading}
                loadError={favoritesLoadError}
                actionError={favoriteActionError}
                removingTeamIds={favoriteLoadingIds}
                reminders={matchReminders}
                remindersLoading={remindersLoading}
                reminderLoadingIds={reminderLoadingIds}
                reminderActionError={reminderActionError}
                onOpenTeam={(team) => {
                  setSelectedTeam(team);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                onRemoveTeam={toggleFavoriteTeam}
                onOpenMatch={(match) => {
                  setTeamBeforeMatch(null);
                  setMatchHistory([]);
                  setSelectedMatchInitialTab("details");
                  setSelectedMatch(match);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                reminderMatchIds={reminderMatchIds}
                onToggleReminder={toggleMatchReminder}
                onOpenReminder={openSavedReminder}
                onRemoveReminder={removeSavedReminder}
              />
            )}
            {screen === "subscription" && (
              <SubscriptionScreen />
            )}
            {screen === "profile" && (
              <ProfileScreen onNavigate={navigate} />
            )}
          </>
        )}
      </main>

      <BottomNavigation
        activeScreen={screen}
        onNavigate={(nextScreen) =>
          navigate(nextScreen, nextScreen === "subscription" ? "navbar" : "unknown")
        }
      />
      {onboardingVisible && (
        <OnboardingOverlay
          onStart={() => closeOnboarding("matches")}
          onLater={() => closeOnboarding()}
        />
      )}
    </div>
  );
}
