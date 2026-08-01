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
        // Primary Green System
        primary: {
          DEFAULT: '#1B5E20',
          light: '#2E7D32',
          dark: '#0D3A12',
          50: '#E8F5E9',
          100: '#C8E6C9',
          200: '#A5D6A7',
          300: '#81C784',
          400: '#66BB6A',
          500: '#4CAF50',
          600: '#2E7D32',
          700: '#1B5E20',
          800: '#0D3A12',
          900: '#051F07',
        },
        // Accent Yellow
        accent: {
          DEFAULT: '#FBC02D',
          light: '#FDD835',
          dark: '#F9A825',
          50: '#FFFDE7',
          100: '#FFF9C4',
          200: '#FFF59D',
          300: '#FFF176',
          400: '#FFEE58',
          500: '#FBC02D',
          600: '#F9A825',
          700: '#F57F17',
          800: '#E65100',
          900: '#BF360C',
        },
        // Alert Red
        danger: {
          DEFAULT: '#D32F2F',
          light: '#EF5350',
          dark: '#B71C1C',
          50: '#FFEBEE',
          100: '#FFCDD2',
          200: '#EF9A9A',
          300: '#E57373',
          400: '#EF5350',
          500: '#D32F2F',
          600: '#C62828',
          700: '#B71C1C',
          800: '#8B0000',
          900: '#5C0000',
        },
        // Background Colors
        surface: {
          DEFAULT: '#F4F6F8',
          card: '#FFFFFF',
          hover: '#E8F5E9',
        },
        // Text Colors
        content: {
          primary: '#1F2937',
          secondary: '#6B7280',
          muted: '#9CA3AF',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        tamil: ['Noto Sans Tamil', 'sans-serif'],
      },
      fontSize: {
        'page-title': ['1.5rem', { lineHeight: '2rem', fontWeight: '600' }],
        'card-title': ['1.125rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'section-label': ['0.75rem', { lineHeight: '1rem', fontWeight: '500', letterSpacing: '0.05em' }],
      },
      spacing: {
        'sidebar': '72px',
        'sidebar-expanded': '256px',
        'navbar': '60px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideInRight: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
        'sidebar': '4px 0 6px -1px rgba(0, 0, 0, 0.1)',
      },
      borderRadius: {
        'card': '12px',
      },
      maxWidth: {
        'content': '1280px',
      },
    },
  },
  plugins: [],
}
