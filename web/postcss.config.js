const path = require('node:path')
const tailwindcss = require('@tailwindcss/postcss')
const autoprefixer = require('autoprefixer')

function tailwindConfigCompat() {
  return {
    postcssPlugin: 'tailwind4-config-compat',
    Once(root, { postcss }) {
      let firstTailwindDirective = null
      let hasConfigDirective = false
      const tailwindDirectives = []

      root.walkAtRules((rule) => {
        if (rule.name === 'tailwind') {
          firstTailwindDirective ??= rule
          tailwindDirectives.push(rule)
        } else if (rule.name === 'config') {
          hasConfigDirective = true
        }
      })

      if (!firstTailwindDirective) {
        return
      }

      const cssFile = root.source?.input?.file
      const configFile = path.join(__dirname, 'tailwind.config.js')
      const relativeConfig = cssFile
        ? path.relative(path.dirname(cssFile), configFile).split(path.sep).join('/')
        : './tailwind.config.js'
      const configPath = relativeConfig.startsWith('.') ? relativeConfig : `./${relativeConfig}`

      if (!hasConfigDirective) {
        firstTailwindDirective.before(postcss.atRule({ name: 'config', params: `"${configPath}"` }))
      }

      firstTailwindDirective.replaceWith(postcss.atRule({ name: 'import', params: '"tailwindcss"' }))
      for (const directive of tailwindDirectives) {
        if (directive !== firstTailwindDirective) {
          directive.remove()
        }
      }
    },
  }
}

module.exports = {
  plugins: [
    tailwindConfigCompat(),
    tailwindcss({ base: __dirname }),
    autoprefixer(),
  ],
}
