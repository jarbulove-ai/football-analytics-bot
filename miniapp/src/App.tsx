import {
  Activity,
  ArrowLeft,
  Bot,
  CalendarDays,
  ChevronRight,
  CircleUserRound,
  Clock3,
  Crown,
  FileText,
  Flame,
  Home,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trophy,
  Upload,
  WalletCards,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  getAppConfig,
  getMatches,
  getSubscription,
  MatchAiAnalysisError,
  PaymentReceiptError,
  requestMatchAiAnalysis,
  submitPaymentReceipt,
} from "./api";
import { getTelegramUserIdentity } from "./telegramUser";
import type {
  AppConfig,
  MatchAiAnalysisResponse,
  MatchItem,
  MatchListType,
  MiniAppPaymentPackageCode,
  PaymentPackage,
  PaymentReceiptResponse,
  Screen,
  SubscriptionData,
} from "./types";

const matchTabs: Array<{ id: MatchListType; label: string }> = [
  { id: "top", label: "Топ" },
  { id: "today", label: "Сегодня" },
  { id: "tomorrow", label: "Завтра" },
];

const navigation = [
  { id: "home" as Screen, label: "Главная", icon: Home },
  { id: "matches" as Screen, label: "Матчи", icon: Activity },
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

function formatPrice(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function TeamLogo({
  logo,
  name,
  size = "md",
}: {
  logo: string | null;
  name: string;
  size?: "sm" | "md" | "lg";
}) {
  const sizeClass = {
    sm: "h-8 w-8 text-xs",
    md: "h-11 w-11 text-sm",
    lg: "h-16 w-16 text-lg",
  }[size];

  if (logo) {
    return (
      <div
        className={`${sizeClass} flex shrink-0 items-center justify-center rounded-full bg-white/95 p-1.5`}
      >
        <img
          src={logo}
          alt=""
          className="h-full w-full object-contain"
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
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="mb-5 flex items-center gap-3">
        <div className="h-6 w-6 animate-pulseSoft rounded-full bg-white/10" />
        <div className="h-3 w-36 animate-pulseSoft rounded bg-white/10" />
      </div>
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 animate-pulseSoft rounded-full bg-white/10" />
          <div className="h-4 w-32 animate-pulseSoft rounded bg-white/10" />
        </div>
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 animate-pulseSoft rounded-full bg-white/10" />
          <div className="h-4 w-28 animate-pulseSoft rounded bg-white/10" />
        </div>
      </div>
    </div>
  );
}

function MatchCard({
  match,
  onOpen,
  index,
}: {
  match: MatchItem;
  onOpen: (match: MatchItem) => void;
  index: number;
}) {
  const kickoff = formatKickoff(match.kickoff);

  return (
    <article
      className="animate-rise rounded-lg border border-line bg-panel p-4 shadow-card"
      style={{ animationDelay: `${Math.min(index * 45, 225)}ms` }}
    >
      <div className="mb-4 flex items-center gap-2.5 border-b border-line pb-3">
        <LeagueLogo logo={match.league_logo} name={match.league} />
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-slate-200">
            {match.league || "Турнир"}
          </p>
          <p className="truncate text-[11px] text-slate-500">
            {match.country || "Страна не указана"}
          </p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-sm font-bold text-white">{kickoff.time}</p>
          <p className="text-[10px] uppercase text-slate-500">{kickoff.date}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <TeamLogo logo={match.home_logo} name={match.home} />
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-white">
            {match.home || "Хозяева"}
          </p>
          <span className="text-[10px] font-semibold uppercase text-slate-500">
            Дома
          </span>
        </div>
        <div className="flex items-center gap-3">
          <TeamLogo logo={match.away_logo} name={match.away} />
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-white">
            {match.away || "Гости"}
          </p>
          <span className="text-[10px] font-semibold uppercase text-slate-500">
            Гости
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => onOpen(match)}
        className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-white/[0.06] text-sm font-semibold text-white transition hover:bg-white/10 active:scale-[0.99]"
      >
        Открыть
        <ChevronRight className="h-4 w-4" />
      </button>
    </article>
  );
}

function MatchesScreen({
  initialType,
  onOpenMatch,
}: {
  initialType: MatchListType;
  onOpenMatch: (match: MatchItem) => void;
}) {
  const [activeType, setActiveType] = useState<MatchListType>(initialType);
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);

    getMatches(activeType)
      .then((response) => {
        if (!active) return;
        if (!response.ok) throw new Error(response.error || "Matches error");
        setMatches(response.items || []);
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

      <div className="mb-5 grid grid-cols-3 rounded-lg bg-panel p-1">
        {matchTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveType(tab.id)}
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
          matches.map((match, index) => (
            <MatchCard
              key={match.id}
              match={match}
              index={index}
              onOpen={onOpenMatch}
            />
          ))}
      </div>
    </div>
  );
}

function MatchDetails({
  match,
  onBack,
}: {
  match: MatchItem;
  onBack: () => void;
}) {
  const kickoff = formatKickoff(match.kickoff);
  const telegramIdentity = useMemo(getTelegramUserIdentity, []);
  const [aiAnalysis, setAiAnalysis] =
    useState<MatchAiAnalysisResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");

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

      <section className="border-b border-line pb-7 text-center">
        <div className="mb-6 flex items-center justify-center gap-3 text-xs text-slate-400">
          <LeagueLogo logo={match.league_logo} name={match.league} />
          <span>{match.league || "Турнир"}</span>
          <span className="text-slate-700">•</span>
          <span>{match.country}</span>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-4">
          <div className="flex min-w-0 flex-col items-center">
            <TeamLogo logo={match.home_logo} name={match.home} size="lg" />
            <p className="mt-3 line-clamp-2 text-sm font-bold text-white">
              {match.home || "Хозяева"}
            </p>
          </div>
          <div className="pt-3">
            <p className="text-2xl font-black text-white">{kickoff.time}</p>
            <p className="mt-1 text-xs text-slate-500">{kickoff.date}</p>
          </div>
          <div className="flex min-w-0 flex-col items-center">
            <TeamLogo logo={match.away_logo} name={match.away} size="lg" />
            <p className="mt-3 line-clamp-2 text-sm font-bold text-white">
              {match.away || "Гости"}
            </p>
          </div>
        </div>
      </section>

      <section className="py-6">
        <div className="mb-3 flex items-center gap-2">
          <Activity className="h-4 w-4 text-lime" />
          <h2 className="text-sm font-bold text-white">Краткий обзор</h2>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg bg-panel p-3">
            <p className="text-[10px] uppercase text-slate-500">Статус</p>
            <p className="mt-1 text-sm font-semibold text-white">
              Матч ожидается
            </p>
          </div>
          <div className="rounded-lg bg-panel p-3">
            <p className="text-[10px] uppercase text-slate-500">Источник</p>
            <p className="mt-1 text-sm font-semibold text-white">MatchLab</p>
          </div>
        </div>
      </section>

      <section className="border-t border-line pt-6">
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
      <div className="grid grid-cols-4">
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

export default function App() {
  const [screen, setScreen] = useState<Screen>(getInitialScreenFromUrl);
  const [matchType, setMatchType] = useState<MatchListType>("top");
  const [selectedMatch, setSelectedMatch] = useState<MatchItem | null>(null);

  useEffect(() => {
    const telegramWebApp = window.Telegram?.WebApp;
    telegramWebApp?.ready();
    telegramWebApp?.expand();

    document.documentElement.dataset.telegramTheme =
      telegramWebApp?.colorScheme || "dark";
  }, []);

  function navigate(nextScreen: Screen) {
    setSelectedMatch(null);
    setScreen(nextScreen);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openMatches(type: MatchListType) {
    setMatchType(type);
    navigate("matches");
  }

  return (
    <div className="min-h-dvh bg-canvas text-white">
      <main className="mx-auto min-h-dvh max-w-lg px-4 pb-28 pt-[max(1rem,env(safe-area-inset-top))]">
        {selectedMatch ? (
          <MatchDetails
            match={selectedMatch}
            onBack={() => setSelectedMatch(null)}
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
                  setSelectedMatch(match);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
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
