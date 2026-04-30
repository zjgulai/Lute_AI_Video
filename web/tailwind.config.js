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
        brand: {
          primary: '#6A2B3A',
          'primary-light': 'rgba(106,43,58,0.08)',
          'primary-mid': 'rgba(106,43,58,0.12)',
          'primary-glow': 'rgba(106,43,58,0.30)',
        },
        ink: {
          primary: '#35353B',
          secondary: '#59585E',
          tertiary: '#9FA0A0',
        },
        surface: {
          card: '#FFF0EF',
          subtle: '#FCE4E2',
          hover: '#EDD3D1',
        },
        border: {
          DEFAULT: '#EDD3D1',
          hover: '#D9A8A3',
        },
      },
      fontFamily: {
        display: ['Montserrat', '-apple-system', 'sans-serif'],
        body: ['Inter', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
