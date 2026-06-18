# MatchLab Mini App

Telegram Mini App frontend for MatchLab, built with Vite, React, TypeScript, and Tailwind CSS.

## Run locally

```bash
npm install
npm run dev
```

## Production build

```bash
npm run build
```

## Environment

Create `.env.local` when you need to override the API URL:

```env
VITE_API_BASE_URL=https://matchlab-miniapp-api.onrender.com
```

Without this variable, the app uses the production MatchLab API URL by default.
