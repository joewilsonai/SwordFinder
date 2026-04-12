// Public runtime config for static UI pages.
// Override by setting window.SWORDFINDER_CONFIG before loading app scripts.
window.SWORDFINDER_CONFIG = Object.assign(
  {
    apiBaseUrl: "https://swordfinder-production.up.railway.app",
    supabaseUrl: "",
    supabaseAnonKey: "",
    seasonYear: 2026,
    appName: "SwordFinder",
  },
  window.SWORDFINDER_CONFIG || {}
);
