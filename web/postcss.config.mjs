import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/postcss";
import autoprefixer from "autoprefixer";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function tailwindConfigCompat() {
  return {
    postcssPlugin: "tailwind4-config-compat",
    Once(root, { postcss }) {
      let firstTailwindDirective = null;
      let hasConfigDirective = false;
      const tailwindDirectives = [];

      root.walkAtRules((rule) => {
        if (rule.name === "tailwind") {
          firstTailwindDirective ??= rule;
          tailwindDirectives.push(rule);
        } else if (rule.name === "config") {
          hasConfigDirective = true;
        }
      });

      if (!firstTailwindDirective) {
        return;
      }

      const cssFile = root.source?.input?.file;
      const configFile = path.join(__dirname, "tailwind.config.js");
      const relativeConfig = cssFile
        ? path.relative(path.dirname(cssFile), configFile).split(path.sep).join("/")
        : "./tailwind.config.js";
      const configPath = relativeConfig.startsWith(".") ? relativeConfig : `./${relativeConfig}`;

      if (!hasConfigDirective) {
        firstTailwindDirective.before(postcss.atRule({ name: "config", params: `"${configPath}"` }));
      }

      firstTailwindDirective.replaceWith(postcss.atRule({ name: "import", params: "\"tailwindcss\"" }));
      for (const directive of tailwindDirectives) {
        if (directive !== firstTailwindDirective) {
          directive.remove();
        }
      }
    },
  };
}

const config = {
  plugins: [
    tailwindConfigCompat(),
    tailwindcss({ base: __dirname }),
    autoprefixer(),
  ],
};
export default config;
