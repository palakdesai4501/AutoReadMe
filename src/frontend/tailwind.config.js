/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          light: '#0070F3',
          dark: '#4C94FF',
        },
        background: {
          canvas: {
            light: '#FFFFFF',
            dark: '#111827',
          },
          surface: {
            light: '#F9FAFB',
            dark: '#1F2937',
          },
        },
        text: {
          primary: {
            light: '#111827',
            dark: '#F9FAFB',
          },
          secondary: {
            light: '#6B7280',
            dark: '#9CA3AF',
          },
        },
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['Fira Code', 'JetBrains Mono', 'Consolas', 'Monaco', 'Andale Mono', 'Ubuntu Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}

