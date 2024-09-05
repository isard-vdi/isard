import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

export default {
  darkMode: ['class'],
  safelist: ['dark'],
  prefix: '',

  content: [
    './pages/**/*.{ts,tsx,vue}',
    './components/**/*.{ts,tsx,vue}',
    './app/**/*.{ts,tsx,vue}',
    './src/**/*.{ts,tsx,vue}'
  ],

  theme: {
    backgroundImage: {
      'cover-img': "url('@/assets/img/cover-img.svg')"
    },
    fontFamily: {
      sans: ['Montserrat', 'sans-serif']
    },
    fontSize: {
      base: [
        'var(--font-size-text-md)',
        {
          lineHeight: 'var(--font-line-height-text-md)',
          letterSpacing: 'var(--font-letter-spacing-text-md)'
        }
      ],
      xs: [
        'var(--font-size-text-xs)',
        {
          lineHeight: 'var(--font-line-height-text-xs)',
          letterSpacing: 'var(--font-letter-spacing-text-xs)'
        }
      ],
      sm: [
        'var(--font-size-text-sm)',
        {
          lineHeight: 'var(--font-line-height-text-sm)',
          letterSpacing: 'var(--font-letter-spacing-text-sm)'
        }
      ],
      md: [
        'var(--font-size-text-md)',
        {
          lineHeight: 'var(--font-line-height-text-md)',
          letterSpacing: 'var(--font-letter-spacing-text-md)'
        }
      ],
      lg: [
        'var(--font-size-text-lg)',
        {
          lineHeight: 'var(--font-line-height-text-lg)',
          letterSpacing: 'var(--font-letter-spacing-text-lg)'
        }
      ],
      xl: [
        'var(--font-size-text-xl)',
        {
          lineHeight: 'var(--font-line-height-text-xl)',
          letterSpacing: 'var(--font-letter-spacing-text-xl)'
        }
      ],
      'display-xs': [
        'var(--font-size-display-xs)',
        {
          lineHeight: 'var(--font-line-height-display-xs)',
          letterSpacing: 'var(--font-letter-spacing-display-xs)'
        }
      ],
      'display-sm': [
        'var(--font-size-display-sm)',
        {
          lineHeight: 'var(--font-line-height-display-sm)',
          letterSpacing: 'var(--font-letter-spacing-display-sm)'
        }
      ],
      'display-md': [
        'var(--font-size-display-md)',
        {
          lineHeight: 'var(--font-line-height-display-md)',
          letterSpacing: 'var(--font-letter-spacing-display-md)'
        }
      ],
      'display-lg': [
        'var(--font-size-display-lg)',
        {
          lineHeight: 'var(--font-line-height-display-lg)',
          letterSpacing: 'var(--font-letter-spacing-display-lg)'
        }
      ],
      'display-xl': [
        'var(--font-size-display-xl)',
        {
          lineHeight: 'var(--font-line-height-display-xl)',
          letterSpacing: 'var(--font-letter-spacing-display-xl)'
        }
      ],
      'display-2xl': [
        'var(--font-size-display-2xl)',
        {
          lineHeight: 'var(--font-line-height-display-2xl)',
          letterSpacing: 'var(--font-letter-spacing-display-2xl)'
        }
      ]
    },
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px'
      }
    },
    extend: {
      colors: {
        base: {
          white: 'var(--base-white)',
          black: 'var(--base-black)',
          background: 'var(--base-background)',
          menu: 'var(--base-menu)',
          'menu-hover': 'var(--base-menu-hover)',
          'menu-current': 'var(--base-menu-current)'
        },
        brand: {
          100: 'var(--brand-100)',
          200: 'var(--brand-200)',
          600: 'var(--brand-600)',
          700: 'var(--brand-700)',
          800: 'var(--brand-800)',
          900: 'var(--brand-900)'
        },
        'gray-warm': {
          25: 'var(--gray-warm-25)',
          50: 'var(--gray-warm-50)',
          100: 'var(--gray-warm-100)',
          200: 'var(--gray-warm-200)',
          300: 'var(--gray-warm-300)',
          400: 'var(--gray-warm-400)',
          500: 'var(--gray-warm-500)',
          600: 'var(--gray-warm-600)',
          700: 'var(--gray-warm-700)',
          800: 'var(--gray-warm-800)',
          900: 'var(--gray-warm-900)',
          950: 'var(--gray-warm-950)'
        },
        error: {
          25: 'var(--error-25)',
          50: 'var(--error-50)',
          100: 'var(--error-100)',
          200: 'var(--error-200)',
          300: 'var(--error-300)',
          400: 'var(--error-400)',
          500: 'var(--error-500)',
          600: 'var(--error-600)',
          700: 'var(--error-700)',
          800: 'var(--error-800)',
          900: 'var(--error-900)',
          950: 'var(--error-950)'
        },
        success: {
          25: 'var(--success-25)',
          50: 'var(--success-50)',
          100: 'var(--success-100)',
          200: 'var(--success-200)',
          300: 'var(--success-300)',
          400: 'var(--success-400)',
          500: 'var(--success-500)',
          600: 'var(--success-600)',
          700: 'var(--success-700)',
          800: 'var(--success-800)',
          900: 'var(--success-900)',
          950: 'var(--success-950)'
        },
        warning: {
          25: 'var(--warning-25)',
          50: 'var(--warning-50)',
          100: 'var(--warning-100)',
          200: 'var(--warning-200)',
          300: 'var(--warning-300)',
          400: 'var(--warning-400)',
          500: 'var(--warning-500)',
          600: 'var(--warning-600)',
          700: 'var(--warning-700)',
          800: 'var(--warning-800)',
          900: 'var(--warning-900)',
          950: 'var(--warning-950)'
        },
        info: {
          25: 'var(--info-25)',
          50: 'var(--info-50)',
          100: 'var(--info-100)',
          200: 'var(--info-200)',
          300: 'var(--info-300)',
          400: 'var(--info-400)',
          500: 'var(--info-500)',
          600: 'var(--info-600)',
          700: 'var(--info-700)',
          800: 'var(--info-800)',
          900: 'var(--info-900)',
          950: 'var(--info-950)'
        },
        'secondary-1': {
          400: 'var(--secondary1-400)',
          500: 'var(--secondary1-500)',
          600: 'var(--secondary1-600)'
        },
        'secondary-2': {
          400: 'var(--secondary2-400)',
          500: 'var(--secondary2-500)',
          600: 'var(--secondary2-600)'
        },
        'secondary-3': {
          400: 'var(--secondary3-400)',
          500: 'var(--secondary3-500)',
          600: 'var(--secondary3-600)'
        },
        'badges-purple': {
          200: 'var(--badges-purple-200)',
          700: 'var(--badges-purple-700)'
        },
        'badges-indigo': {
          200: 'var(--badges-indigo-200)',
          700: 'var(--badges-indigo-700)'
        },
        'badges-violet': {
          200: 'var(--badges-violet-200)',
          600: 'var(--badges-violet-600)',
          700: 'var(--badges-violet-700)',
          900: 'var(--badges-violet-900)'
        }
      },
      spacing: {
        '0': 'var(--spacing-0)',
        '0-5': 'var(--spacing-0-5)',
        '1': 'var(--spacing-1)',
        '2': 'var(--spacing-2)',
        '3': 'var(--spacing-3)',
        '4': 'var(--spacing-4)',
        '5': 'var(--spacing-5)',
        '6': 'var(--spacing-6)',
        '8': 'var(--spacing-8)',
        '10': 'var(--spacing-10)',
        '12': 'var(--spacing-12)',
        '16': 'var(--spacing-16)',
        '20': 'var(--spacing-20)',
        '24': 'var(--spacing-24)',
        '32': 'var(--spacing-32)',
        '40': 'var(--spacing-40)',
        '48': 'var(--spacing-48)',
        '56': 'var(--spacing-56)',
        '64': 'var(--spacing-64)',
        '80': 'var(--spacing-80)',
        '96': 'var(--spacing-96)',
        '120': 'var(--spacing-120)',
        '140': 'var(--spacing-140)',
        '160': 'var(--spacing-160)',
        '180': 'var(--spacing-180)',
        '192': 'var(--spacing-192)',
        '256': 'var(--spacing-256)',
        '320': 'var(--spacing-320)',
        '360': 'var(--spacing-360)',
        '400': 'var(--spacing-400)',
        '480': 'var(--spacing-480)'
      },
      borderRadius: {
        none: 'var(--radius-none)',
        xxs: 'var(--radius-xxs)',
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        '3xl': 'var(--radius-3xl)',
        '4xl': 'var(--radius-4xl)',
        full: 'var(--radius-full)'
      },
      ringWidth: {
        xs: 'var(--ring-brand-shadow-xs)',
        sm: 'var(--ring-brand-shadow-sm)'
      },
      ringColor: {
        brand: 'var(--ring-brand-color)',
        gray: 'var(--ring-gray-color)',
        'gray-secondary': 'var(--ring-gray-secondary-color)',
        warning: 'var(--ring-warning-color)',
        error: 'var(--ring-error-color)'
      }
    }
  },
  plugins: [animate]
} satisfies Config
