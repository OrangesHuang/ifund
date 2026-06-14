/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {},
  },
  plugins: [],
  // 避免与 antd 的样式冲突
  corePlugins: {
    preflight: false,
  },
}
