/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // ── Fortune Red 核心色 ──
        'fortune-red': '#D75C70',
        'cinnabar': '#D04E5A',
        'neon-red': '#C44A5E',
        'misty-pink': '#EAAFB7',
        'coral': '#F37969',
        'ember': '#C44A5E',
        'crimson-mist': '#A13D4E',
        // 金色系
        'gold-foil': '#D8BE78',
        'antique-gold': '#B99B5F',
        'pale-gold': '#A58C5A',
        // 功能色
        'jade': '#78AF8C',
        'cool-steel': '#5C8DC9',
        // 数据可视化扩展
        'cinema-violet': '#9B7CC4',
        'cinema-azure': '#5C8DC9',
        // 浅色基底
        'cinema-black': '#FDF8F6',
        'film-reel': '#FCF5F2',
        'dark-slate': '#FEFBFA',
        'charcoal-rose': '#F5F0EC',
        'warm-shadow': '#EDE8E3',

        // ── 兼容旧 brand/ink/surface 命名 ──
        brand: {
          primary: '#D75C70',
          'primary-light': 'rgba(215,92,112,0.10)',
          'primary-mid': 'rgba(215,92,112,0.18)',
          'primary-glow': 'rgba(215,92,112,0.30)',
        },
        ink: {
          primary: 'rgba(53, 20, 26, 0.92)',
          secondary: 'rgba(53, 20, 26, 0.60)',
          tertiary: 'rgba(53, 20, 26, 0.42)',
        },
        surface: {
          card: '#FFFFFF',
          subtle: '#FCF5F2',
          hover: '#FDF4F5',
        },
        border: {
          DEFAULT: 'rgba(53,20,26,0.08)',
          hover: '#D75C70',
        },
      },
      borderRadius: {
        card: '12px',
        tab: '10px',
        badge: '6px',
        input: '10px',
      },
      boxShadow: {
        cinema: '0 2px 8px rgba(0, 0, 0, 0.06)',
        'cinema-hover': '0 4px 16px rgba(0, 0, 0, 0.08)',
        'neon-red': '0 0 8px rgba(215, 92, 112, 0.15)',
        'neon-red-strong': '0 0 12px rgba(215, 92, 112, 0.25)',
        gold: '0 0 8px rgba(216, 190, 120, 0.10)',
      },
      fontFamily: {
        display: ['Montserrat', '-apple-system', 'sans-serif'],
        body: ['Inter', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
