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
        // Serves ./data (every zarr store) in dev. The app requests data under
        // `base`, so match that as well as a bare /data/; unmatched requests fall
        // through to Vite, which would serve zarr metadata as JS modules.
        const dataDir = path.join(__dirname, 'data');
        const prefixes = [`${server.config.base}data/`, '/data/'];
        server.middlewares.use((req: any, res: any, next: any) => {
          const urlPath = req.url?.split('?')[0] ?? '';
          const prefix = prefixes.find((p) => urlPath.startsWith(p));
          if (!prefix) { next(); return; }
          let filePath: string;
          try {
            filePath = path.resolve(dataDir, decodeURIComponent(urlPath.slice(prefix.length)));
          } catch { next(); return; } // malformed escape
          if (!filePath.startsWith(dataDir + path.sep)) { next(); return; }
          try {
            const stat = fs.statSync(filePath);
            if (stat.isFile()) {
              // extname is empty for dotfiles such as .zarray; key those by name
              const ext = path.extname(filePath) || path.basename(filePath);
              const mime: Record<string, string> = {
                '.html': 'text/html',
                '.json': 'application/json',
                '.js': 'application/javascript',
                // zarr v2 metadata
                '.zgroup': 'application/json',
                '.zarray': 'application/json',
                '.zattrs': 'application/json',
                '.zmetadata': 'application/json',
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
