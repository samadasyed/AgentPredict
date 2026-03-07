import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Brand palette
        pm: {
          DEFAULT: '#3B82F6',  // Polymarket blue
          light: '#93C5FD',
        },
        mma: {
          DEFAULT: '#F97316',  // MMA orange
          light: '#FED7AA',
        },
        confidence: {
          high:   '#22C55E',  // green  (>0.7)
          medium: '#EAB308',  // yellow (0.5–0.7)
          low:    '#6B7280',  // gray   (<0.5, shown as neutral)
        },
      },
    },
  },
  plugins: [],
}

export default config
