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
  Clock3,
  Crown,
  FileText,
  Flame,
  Home,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Trophy,
  Upload,
  WalletCards,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  addMatchReminder,
  addFavoriteTeam,
  getAppConfig,
  getFavoriteTeams,
  getMatch,
  getMatchContext,
  getMatchReminders,
  getMatches,
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
} from "./api";
import { getTelegramUserIdentity } from "./telegramUser";
import type {
  AppConfig,
  FavoriteTeamItem,
  MatchAiAnalysisResponse,
  MatchContextMatch,
  MatchContextResponse,
  MatchItem,
  MatchListType,
  MatchReminderItem,
  MatchStandingRow,
  MiniAppPaymentPackageCode,
  PaymentPackage,
  PaymentReceiptResponse,
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
];

type MatchDetailTab = "details" | "ai" | "table" | "matches";
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
  onOpenMatches,
  onNavigate,
}: {
  onOpenMatches: (type: MatchListType) => void;
  onNavigate: (screen: Screen) => void;
}) {
  const shortcuts = [
    {
      title: "Топ матчи",
      caption: "Главные игры ближайших дней",
      icon: Flame,
      iconClass: "bg-red-500/15 text-red-400",
      action: () => onOpenMatches("top"),
    },
    {
      title: "Сегодня",
      caption: "Расписание на текущий день",
      icon: CalendarDays,
      iconClass: "bg-accent/15 text-accent",
      action: () => onOpenMatches("today"),
    },
    {
      title: "Завтра",
      caption: "Матчи следующего дня",
      icon: Clock3,
      iconClass: "bg-lime/10 text-lime",
      action: () => onOpenMatches("tomorrow"),
    },
    {
      title: "Подписка",
      caption: "Тарифы и AI-лимиты",
      icon: Crown,
      iconClass: "bg-gold/10 text-gold",
      action: () => onNavigate("subscription"),
    },
  ];

  return (
    <div className="animate-rise">
      <AppHeader />

      <section className="mb-7">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">
              Центр матчей
            </p>
            <h1 className="mt-1 text-2xl font-extrabold text-white">
              Что смотрим?
            </h1>
          </div>
          <Sparkles className="h-5 w-5 text-lime" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          {shortcuts.map(({ title, caption, icon: Icon, iconClass, action }) => (
            <button
              key={title}
              type="button"
              onClick={action}
              className="group min-h-36 rounded-lg border border-line bg-panel p-4 text-left shadow-card transition duration-200 active:scale-[0.98]"
            >
              <span
                className={`mb-5 flex h-10 w-10 items-center justify-center rounded-lg ${iconClass}`}
              >
                <Icon className="h-5 w-5" />
              </span>
              <span className="block text-base font-bold text-white">
                {title}
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-400">
                {caption}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="border-t border-line pt-6">
        <div className="mb-4 flex items-center gap-2">
          <Bot className="h-5 w-5 text-accent" />
          <h2 className="text-base font-bold text-white">
            Что умеет MatchLab
          </h2>
        </div>
        <div className="space-y-4">
          {[
            ["Форма и тренды", "Последние матчи, голы и динамика команд"],
            ["Матчевый контекст", "Турнир, время начала и ключевые показатели"],
            ["AI-разбор", "Краткие выводы и аналитические сигналы"],
          ].map(([title, text], index) => (
            <div key={title} className="flex items-start gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-panelSoft text-xs font-bold text-lime">
                {index + 1}
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{title}</p>
                <p className="mt-0.5 text-xs leading-5 text-slate-400">
                  {text}
                </p>
              </div>
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
        <span className="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-slate-400">
          {hasScore ? `${match.score.home}:${match.score.away}` : "Детали"}
        </span>
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

function MatchesScreen({
  initialType,
  onOpenMatch,
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
  onOpenMatch: (match: MatchItem) => void;
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
  const isTeamSearchActive = normalizedTeamQuery.length >= 2;
  const groupedMatches = useMemo(() => {
    const groups = new Map<string, MatchItem[]>();
    matches.forEach((match) => {
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
        const nextMatches = response.items || [];
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

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <div className="mb-5 flex items-end justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-slate-500">
            Расписание
          </p>
          <h1 className="mt-1 text-2xl font-extrabold text-white">Матчи</h1>
        </div>
        {!loading && !error && (
          <span className="rounded-full bg-panelSoft px-2.5 py-1 text-xs font-semibold text-slate-300">
            {matches.length}
          </span>
        )}
      </div>

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

      <div className="mb-5 grid grid-cols-3 rounded-lg bg-panel p-1">
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

      <div className="space-y-3">
        {loading &&
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

        {!loading && !error && matches.length === 0 && (
          <div className="py-16 text-center">
            <CalendarDays className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-4 text-sm font-semibold text-white">
              Матчей пока нет
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Расписание обновится автоматически.
            </p>
          </div>
        )}

        {!loading &&
          !error &&
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

function ContextMatchRow({ match }: { match: MatchContextMatch }) {
  const hasScore =
    typeof match.home_score === "number" &&
    typeof match.away_score === "number";

  return (
    <div className="grid grid-cols-[4.75rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-line/80 px-3 py-3 first:border-t-0">
      <div>
        <p className="text-[10px] leading-4 text-slate-500">
          {formatContextMatchDate(match.date)}
        </p>
        {match.status && (
          <p className="mt-0.5 text-[10px] font-semibold text-slate-400">
            {match.status}
          </p>
        )}
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
    </div>
  );
}

function MatchContextGroup({
  title,
  matches,
}: {
  title: string;
  matches: MatchContextMatch[];
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
  const firstMatch = tournament.matches[0];
  const nearestMatch = useMemo(
    () =>
      [...tournament.matches].sort((left, right) => {
        const leftTime = left.kickoff
          ? new Date(left.kickoff).getTime()
          : Number.POSITIVE_INFINITY;
        const rightTime = right.kickoff
          ? new Date(right.kickoff).getTime()
          : Number.POSITIVE_INFINITY;
        return leftTime - rightTime;
      })[0],
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
          {tournament.matches.length > 0 ? (
            <section className="overflow-hidden rounded-lg border border-line bg-panel">
              {tournament.matches.map((match) => (
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
                {matches.upcoming.map((match) => (
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

function MatchDetails({
  match,
  onBack,
  onOpenTeam,
  reminderActive,
  reminderLoading,
  reminderActionError,
  onToggleReminder,
}: {
  match: MatchItem;
  onBack: () => void;
  onOpenTeam: (team: TeamSearchItem) => void;
  reminderActive: boolean;
  reminderLoading: boolean;
  reminderActionError: string;
  onToggleReminder: (match: MatchItem) => void;
}) {
  const kickoff = formatKickoff(match.kickoff);
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const [aiAnalysis, setAiAnalysis] =
    useState<MatchAiAnalysisResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [activeTab, setActiveTab] =
    useState<MatchDetailTab>("details");
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

  async function handleAiAnalysis() {
    setAiLoading(true);
    setAiError("");

    try {
      const response = await requestMatchAiAnalysis(
        match.id,
        telegramIdentity.id,
      );
      setAiAnalysis(response);
    } catch (error) {
      setAiAnalysis(null);
      if (error instanceof MatchAiAnalysisError) {
        if (error.status === 402 || error.code === "ai_limit_exceeded") {
          setAiError(
            "AI-лимит закончился. Можно оформить подписку или докупить AI-разборы.",
          );
        } else if (error.status === 404 || error.code === "match_not_found") {
          setAiError("Матч не найден или уже недоступен.");
        } else if (
          error.status === 503 ||
          error.code === "ai_analysis_unavailable"
        ) {
          setAiError("AI-разбор временно недоступен.");
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
            <p className="text-2xl font-black text-white">{kickoff.time}</p>
            <p className="mt-1 text-xs text-slate-500">{kickoff.date}</p>
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
                  Матч ожидается
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
            <div className="mt-5 rounded-lg border border-accent/20 bg-panel p-4">
              <div className="whitespace-pre-line text-sm leading-6 text-slate-200">
                {aiAnalysis.analysis}
              </div>
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
              </div>
            </div>
          )}

          {aiError && (
            <div className="mt-5 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm leading-5 text-red-200">
              {aiError}
            </div>
          )}

          <button
            type="button"
            onClick={handleAiAnalysis}
            disabled={aiLoading}
            className="mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm font-bold text-white transition active:scale-[0.99] disabled:cursor-wait disabled:opacity-70"
          >
            {aiLoading ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Bot className="h-4 w-4" />
            )}
            {aiLoading ? "AI-разбор готовится…" : "AI-разбор"}
          </button>
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
              />
              <MatchContextGroup
                title={`Последние матчи: ${match.home}`}
                matches={matchContext.home_recent}
              />
              <MatchContextGroup
                title={`Последние матчи: ${match.away}`}
                matches={matchContext.away_recent}
              />
              <MatchContextGroup
                title="Ближайшие матчи"
                matches={matchContext.upcoming}
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
          matches: response.upcoming.slice(0, 2),
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
                      className="mr-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-lime/10 text-lime transition active:scale-95 disabled:cursor-wait disabled:opacity-60"
                      aria-label={`Удалить напоминание ${reminder.home_team} — ${reminder.away_team}`}
                    >
                      {reminderLoading ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Bell className="h-4 w-4" fill="currentColor" />
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

function ProfileScreen() {
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

  const usagePercent = useMemo(() => {
    if (!profile || profile.is_admin || profile.ai_limit_monthly <= 0) return 0;
    return Math.min(
      100,
      Math.round(
        (profile.ai_used_monthly / profile.ai_limit_monthly) * 100,
      ),
    );
  }, [profile]);

  return (
    <div className="animate-rise">
      <AppHeader compact />
      <p className="text-xs font-semibold uppercase text-slate-500">Аккаунт</p>
      <h1 className="mt-1 text-2xl font-extrabold text-white">Профиль</h1>

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
        <div className="mt-6 space-y-6">
          <section className="rounded-lg border border-line bg-panel p-5 shadow-card">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-lg font-black text-white">
                M
              </div>
              <div>
                <p className="text-base font-bold text-white">
                  MatchLab User
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  Telegram ID: {profile.telegram_user_id}
                </p>
                <p className="mt-1 text-[11px] font-semibold text-lime">
                  {telegramIdentity.mode === "telegram"
                    ? "Telegram Mini App"
                    : "Тестовый режим"}
                </p>
                {profile.is_admin && (
                  <p className="mt-1 text-[10px] leading-4 text-slate-500">
                    Telegram SDK:{" "}
                    {telegramIdentity.sdkAvailable ? "есть" : "нет"}
                    {" · "}
                    initData:{" "}
                    {telegramIdentity.initDataAvailable ? "есть" : "нет"}
                  </p>
                )}
              </div>
              {profile.is_admin && (
                <ShieldCheck className="ml-auto h-5 w-5 text-lime" />
              )}
            </div>
          </section>

          <section>
            <p className="mb-3 text-xs font-semibold uppercase text-slate-500">
              Тариф
            </p>
            <div className="rounded-lg border border-gold/20 bg-gold/[0.06] p-4">
              <div className="flex items-center gap-3">
                <Crown className="h-5 w-5 text-gold" />
                <div>
                  <p className="text-sm font-bold capitalize text-white">
                    {profile.plan}
                  </p>
                  <p className="text-xs text-slate-400">
                    {profile.is_admin
                      ? "Административный доступ"
                      : `Период: ${profile.usage_period}`}
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase text-slate-500">
                AI-разборы
              </p>
              <span className="text-xs font-semibold text-lime">
                {profile.ai_text ||
                  `${profile.ai_used_monthly} / ${profile.ai_limit_monthly}`}
              </span>
            </div>
            <div className="rounded-lg bg-panel p-4">
              {!profile.is_admin && (
                <div className="mb-4 h-2 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full bg-lime transition-all duration-500"
                    style={{ width: `${usagePercent}%` }}
                  />
                </div>
              )}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-2xl font-black text-white">
                    {profile.is_admin ? "∞" : profile.ai_used_monthly}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Использовано
                  </p>
                </div>
                <div>
                  <p className="text-2xl font-black text-white">
                    {profile.extra_ai_credits}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Дополнительно
                  </p>
                </div>
              </div>
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
  if (item.ai_credits) return `${item.ai_credits} полных AI-разборов`;
  if (item.days && item.ai_limit) {
    return `${item.ai_limit} AI-разборов на ${item.days} дней`;
  }
  return "Возможности MatchLab";
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedPackage, setSelectedPackage] =
    useState<PaymentPackage | null>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [receiptError, setReceiptError] = useState("");
  const [receiptSuccess, setReceiptSuccess] =
    useState<PaymentReceiptResponse | null>(null);

  useEffect(() => {
    getAppConfig()
      .then(setConfig)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  function selectPackage(item: PaymentPackage) {
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
      <p className="text-xs font-semibold uppercase text-slate-500">
        Больше возможностей
      </p>
      <h1 className="mt-1 text-2xl font-extrabold text-white">Подписка</h1>
      <p className="mt-2 max-w-sm text-sm leading-6 text-slate-400">
        Выберите подходящий пакет аналитики.
      </p>

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
        <div className="mt-7 space-y-3">
          {config.packages.map((item, index) => {
            const premium = item.code !== "ai_30";
            return (
              <article
                key={item.code}
                className={`animate-rise rounded-lg border p-5 shadow-card ${
                  premium
                    ? "border-gold/25 bg-gold/[0.06]"
                    : "border-line bg-panel"
                }`}
                style={{ animationDelay: `${index * 70}ms` }}
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                      premium
                        ? "bg-gold/15 text-gold"
                        : "bg-accent/15 text-accent"
                    }`}
                  >
                    <PackageIcon packageCode={item.code} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white">{item.title}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {packageDescription(item)}
                    </p>
                  </div>
                  <p className="whitespace-nowrap text-base font-black text-white">
                    {formatPrice(item.price_kzt)} ₸
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => selectPackage(item)}
                  className={`mt-5 h-11 w-full rounded-md text-sm font-bold transition active:scale-[0.99] ${
                    premium
                      ? "bg-gold text-zinc-950"
                      : "bg-accent text-white"
                  }`}
                >
                  Выбрать
                </button>
              </article>
            );
          })}
        </div>
      )}

      <div className="mt-6 flex items-start gap-3 border-t border-line pt-5">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-lime" />
        <p className="text-xs leading-5 text-slate-500">
          Доступ привязан к вашему Telegram-профилю.
        </p>
      </div>
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

export default function App() {
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const initialMatchId = useMemo(getInitialMatchIdFromUrl, []);
  const [screen, setScreen] = useState<Screen>(getInitialScreenFromUrl);
  const [matchType, setMatchType] = useState<MatchListType>("top");
  const [selectedMatch, setSelectedMatch] = useState<MatchItem | null>(null);
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
  const [deepLinkLoading, setDeepLinkLoading] = useState(
    Boolean(initialMatchId),
  );
  const [deepLinkError, setDeepLinkError] = useState("");
  const reminderMatchIds = useMemo(
    () => new Set(matchReminders.map((reminder) => reminder.match_id)),
    [matchReminders],
  );

  useEffect(() => {
    const telegramWebApp = window.Telegram?.WebApp;
    telegramWebApp?.ready();
    telegramWebApp?.expand();

    document.documentElement.dataset.telegramTheme =
      telegramWebApp?.colorScheme || "dark";
  }, []);

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
        setSelectedMatch(response.match);
      })
      .catch(() => {
        if (!active) return;
        setScreen("matches");
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

  function navigate(nextScreen: Screen) {
    setSelectedMatch(null);
    setSelectedTournament(null);
    setSelectedTeam(null);
    setTeamBeforeMatch(null);
    setScreen(nextScreen);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openMatches(type: MatchListType) {
    setMatchType(type);
    navigate("matches");
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
              setSelectedMatch(match);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        ) : selectedMatch ? (
          <MatchDetails
            match={selectedMatch}
            onBack={() => {
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
                onOpenMatches={openMatches}
                onNavigate={navigate}
              />
            )}
            {screen === "matches" && (
              <MatchesScreen
                initialType={matchType}
                onOpenMatch={(match) => {
                  setTeamBeforeMatch(null);
                  setSelectedMatch(match);
                  window.scrollTo({ top: 0, behavior: "smooth" });
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
            {screen === "profile" && <ProfileScreen />}
          </>
        )}
      </main>

      <BottomNavigation activeScreen={screen} onNavigate={navigate} />
    </div>
  );
}
