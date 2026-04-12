// Public runtime config for static UI pages.
// Override by setting window.SWORDFINDER_CONFIG before loading app scripts.
window.SWORDFINDER_CONFIG = Object.assign(
  {
    supabaseUrl: "https://seagurfpitfslyxxxztw.supabase.co",
    supabaseAnonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlYWd1cmZwaXRmc2x5eHh4enR3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDk0NTM5MjIsImV4cCI6MjA2NTAyOTkyMn0.qwRNWppt-O4RAIyjUS54M25zWoRjb1Zx2jB-6LmqW38",
    seasonYear: 2026,
    appName: "SwordFinder",
  },
  window.SWORDFINDER_CONFIG || {}
);
