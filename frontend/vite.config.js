import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  // Tailwind v4 is a Vite plugin rather than a PostCSS step, so there is no
  // tailwind.config.js and no content globs to keep in sync. The theme lives
  // in src/ui/theme.css, in an @theme block.
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
  },
});
