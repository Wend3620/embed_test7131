import path from "path"
import fs from "fs"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  // base: '/',
  base: '/embed_test7131/',
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'serve-data-dir',
      configureServer(server) {
        server.middlewares.use((req: any, res: any, next: any) => {
          if (!req.url?.startsWith('/data/')) { next(); return; }
          const filePath = path.join(__dirname, req.url.split('?')[0]);
          try {
            const stat = fs.statSync(filePath);
            if (stat.isFile()) {
              const ext = path.extname(filePath);
              const mime: Record<string, string> = {
                '.html': 'text/html',
                '.json': 'application/json',
                '.js': 'application/javascript',
              };
              res.setHeader('Content-Type', mime[ext] ?? 'application/octet-stream');
              fs.createReadStream(filePath).pipe(res);
              return;
            }
          } catch { /* file not found, fall through */ }
          next();
        });
      },
    },
  ],
  define: {
    global: 'globalThis',
  },
  optimizeDeps: {
    include: ['plotly.js-dist'],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "plotly.js": "plotly.js-dist",
    },
  },
})
