// Built once with: npx tailwindcss@3.4 -c tailwind.config.cjs -o ui/assets/tailwind.css --minify
module.exports = {
  content: ['./ui/**/*.html', './ui/assets/*.js'],
  theme: { extend: { screens: { xs: '420px' } } },
};
