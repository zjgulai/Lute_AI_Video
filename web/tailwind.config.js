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
        // ── Fortune Red Cinema 核心色 ──
        'fortune-red': '#D75C70',
        'cinnabar': '#D04E5A',
        'neon-red': '#FF4D6A',
        'misty-pink': '#EAAFB7',
        'coral': '#F37969',
        'ember': '#B44658',
        'crimson-mist': '#8C3C4B',
        // 金色系
        'gold-foil': '#DCBE78',
        'antique-gold': '#B99B5F',
        'pale-gold': '#A58C5A',
        // 功能色
        'jade': '#78AF8C',
        'cool-steel': '#829BAF',
        // 数据可视化扩展
        'cinema-violet': '#9B7CC4',
        'cinema-azure': '#5C8DC9',
        // 深色基底
        'cinema-black': '#100C0D',
        'film-reel': '#1C1415',
        'dark-slate': '#2A1E20',
        'charcoal-rose': '#3A2A2D',
        'warm-shadow': '#4E3A3D',

        // ── 兼容旧 brand/ink/surface 命名 ──
        brand: {
          primary: '#D75C70',
          'primary-light': 'rgba(215,92,112,0.10)',
          'primary-mid': 'rgba(215,92,112,0.18)',
          'primary-glow': 'rgba(255,77,106,0.40)',
        },
        ink: {
          primary: '#FAF0EB',
          secondary: '#D2C3BE',
          tertiary: '#A0918E',
        },
        surface: {
          card: '#1C1415',
          subtle: '#2A1E20',
          hover: '#3A2A2D',
        },
        border: {
          DEFAULT: '#4E3A3D',
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
        cinema: '0 4px 16px rgba(0, 0, 0, 0.4)',
        'cinema-hover': '0 8px 32px rgba(0, 0, 0, 0.5)',
        'neon-red': '0 0 12px rgba(255, 77, 106, 0.25)',
        'neon-red-strong': '0 0 20px rgba(255, 77, 106, 0.4)',
        gold: '0 0 12px rgba(220, 190, 120, 0.2)',
      },
      fontFamily: {
        display: ['Montserrat', '-apple-system', 'sans-serif'],
        body: ['Inter', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
