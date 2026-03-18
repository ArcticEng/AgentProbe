// Production API URL — set VITE_API_URL in Vercel env vars to your Fly.io backend URL
const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "/api";

export default API_BASE;
